"""End-to-end RAG readiness and latency check.

This script uses real Web-RAG APIs and intentionally does not delete or archive
documents. Provide an existing WEB_RAG_DOCUMENT_ID to avoid uploading a new
fixture document on every run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx


FIXTURE_TEXT = """Web-RAG readiness verification fixture.

The canonical support color is cobalt blue.
The emergency escalation code is VECTOR-77.
The standard retrieval mode for public answers is hybrid.
The approved response target for first token latency is under three seconds.
The Qdrant verification phrase is chunk-back-check.
"""

QUESTIONS = [
    ("What is the canonical support color?", "cobalt blue"),
    ("What is the emergency escalation code?", "VECTOR-77"),
    ("Which retrieval mode is standard for public answers?", "hybrid"),
    ("What is the first token latency target?", "three seconds"),
    ("What is the Qdrant verification phrase?", "chunk-back-check"),
]


@dataclass
class StreamResult:
    answer: str
    sources: list[dict[str, Any]]
    thread_id: str | None
    first_token_ms: int | None
    full_answer_ms: int


def percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
    return ordered[idx]


async def upload_fixture(client: httpx.AsyncClient, token: str) -> str:
    files = {
        "file": (
            f"web-rag-readiness-{int(time.time())}.txt",
            FIXTURE_TEXT.encode("utf-8"),
            "text/plain",
        )
    }
    response = await client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    if response.status_code == 409:
        detail = response.json().get("detail", {})
        existing_id = detail.get("existing_document_id")
        if existing_id:
            return existing_id
    response.raise_for_status()
    return response.json()["id"]


async def wait_for_document(client: httpx.AsyncClient, token: str, document_id: str) -> dict[str, Any]:
    for _ in range(60):
        response = await client.get(
            f"/api/documents/status/{document_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "processed":
            return data
        if data.get("status") == "failed":
            raise RuntimeError(f"Document processing failed: {data.get('error_message')}")
        await asyncio.sleep(2)
    raise TimeoutError(f"Document {document_id} did not finish processing within 120s")


async def check_qdrant(client: httpx.AsyncClient, token: str, document_id: str) -> dict[str, Any]:
    response = await client.get(
        "/api/documents/check-qdrant",
        params={"document_id": document_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    data = response.json()
    if int(data.get("chunk_count") or 0) <= 0:
        raise AssertionError(f"Qdrant returned no chunks for document {document_id}")
    return data


def parse_sse_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data: "):
        return None
    payload = line[6:].strip()
    if not payload:
        return None
    return json.loads(payload)


async def stream_chat(
    client: httpx.AsyncClient,
    path: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> StreamResult:
    started = time.perf_counter()
    first_token_ms: int | None = None
    answer_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    thread_id: str | None = None

    async with client.stream("POST", path, headers=headers, json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            event = parse_sse_line(line)
            if not event:
                continue
            thread_id = event.get("thread_id") or thread_id
            if event.get("type") == "sources":
                sources = event.get("sources") or sources
            if event.get("type") in {"token", None} and event.get("content"):
                if first_token_ms is None:
                    first_token_ms = int((time.perf_counter() - started) * 1000)
                answer_parts.append(event["content"])
            if event.get("type") == "error":
                raise RuntimeError(f"Stream error: {event.get('content')}")
            if event.get("done") or event.get("type") == "done":
                break

    return StreamResult(
        answer="".join(answer_parts),
        sources=sources,
        thread_id=thread_id,
        first_token_ms=first_token_ms,
        full_answer_ms=int((time.perf_counter() - started) * 1000),
    )


def assert_answer(result: StreamResult, expected_fact: str, expected_document_id: str | None) -> None:
    answer_lower = result.answer.lower()
    if expected_fact.lower() not in answer_lower:
        raise AssertionError(f"Answer did not include expected fact '{expected_fact}'. Answer: {result.answer[:300]}")
    if expected_document_id:
        source_ids = [source.get("document_id") for source in result.sources[:3]]
        if expected_document_id not in source_ids:
            raise AssertionError(f"Expected document {expected_document_id} in top sources, got {source_ids}")


async def create_widget_session(client: httpx.AsyncClient, tenant_slug: str, origin: str) -> str:
    response = await client.post(
        "/api/widget/session",
        headers={"Origin": origin},
        json={"tenant_slug": tenant_slug},
    )
    response.raise_for_status()
    return response.json()["token"]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Web-RAG retrieval correctness and latency.")
    parser.add_argument("--base-url", default=os.getenv("WEB_RAG_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--admin-token", default=os.getenv("WEB_RAG_ADMIN_TOKEN"))
    parser.add_argument("--document-id", default=os.getenv("WEB_RAG_DOCUMENT_ID"))
    parser.add_argument("--widget-tenant-slug", default=os.getenv("WEB_RAG_WIDGET_TENANT_SLUG"))
    parser.add_argument("--widget-origin", default=os.getenv("WEB_RAG_WIDGET_ORIGIN", "http://127.0.0.1:4173"))
    parser.add_argument("--first-token-ms", type=int, default=int(os.getenv("WEB_RAG_FIRST_TOKEN_MS", "3000")))
    parser.add_argument("--full-answer-ms", type=int, default=int(os.getenv("WEB_RAG_FULL_ANSWER_MS", "15000")))
    args = parser.parse_args()

    if not args.admin_token:
        print("WEB_RAG_ADMIN_TOKEN or --admin-token is required.", file=sys.stderr)
        return 2

    async with httpx.AsyncClient(base_url=args.base_url, timeout=180) as client:
        document_id = args.document_id or await upload_fixture(client, args.admin_token)
        await wait_for_document(client, args.admin_token, document_id)
        qdrant = await check_qdrant(client, args.admin_token, document_id)

        auth_results: list[StreamResult] = []
        for question, expected_fact in QUESTIONS:
            result = await stream_chat(
                client,
                "/api/chat/stream",
                {"Authorization": f"Bearer {args.admin_token}"},
                {
                    "message": question,
                    "thread_id": None,
                    "use_documents": True,
                    "retrieval_mode": "hybrid",
                    "enable_web_search": False,
                    "enable_sql": False,
                },
            )
            assert_answer(result, expected_fact, document_id)
            auth_results.append(result)

        widget_results: list[StreamResult] = []
        if args.widget_tenant_slug:
            widget_token = await create_widget_session(client, args.widget_tenant_slug, args.widget_origin)
            for question, expected_fact in QUESTIONS:
                result = await stream_chat(
                    client,
                    "/api/widget/chat/stream",
                    {
                        "Authorization": f"Bearer {widget_token}",
                        "Origin": args.widget_origin,
                    },
                    {"message": question, "thread_id": None},
                )
                assert_answer(result, expected_fact, document_id)
                widget_results.append(result)

        all_results = auth_results + widget_results
        first_token_values = [r.first_token_ms for r in all_results if r.first_token_ms is not None]
        full_answer_values = [r.full_answer_ms for r in all_results]
        first_token_p95 = percentile(first_token_values, 0.95)
        full_answer_p95 = percentile(full_answer_values, 0.95)

        summary = {
            "document_id": document_id,
            "qdrant_chunk_count": qdrant.get("chunk_count"),
            "authenticated_cases": len(auth_results),
            "widget_cases": len(widget_results),
            "first_token_ms": {
                "p50": int(statistics.median(first_token_values)) if first_token_values else None,
                "p95": first_token_p95,
            },
            "full_answer_ms": {
                "p50": int(statistics.median(full_answer_values)) if full_answer_values else None,
                "p95": full_answer_p95,
            },
        }
        print(json.dumps(summary, indent=2))

        if first_token_p95 is not None and first_token_p95 > args.first_token_ms:
            raise AssertionError(f"First-token p95 {first_token_p95}ms exceeds {args.first_token_ms}ms")
        if full_answer_p95 is not None and full_answer_p95 > args.full_answer_ms:
            raise AssertionError(f"Full-answer p95 {full_answer_p95}ms exceeds {args.full_answer_ms}ms")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
