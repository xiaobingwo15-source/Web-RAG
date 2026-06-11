"""End-to-end RAG readiness and latency check.

This script uses real Web-RAG APIs and intentionally does not delete or archive
documents. By default it uploads a small text fixture and runs fixed QA checks.
Provide WEB_RAG_DOCUMENT_PATH/--document-path or WEB_RAG_DOCUMENT_ID/--document-id
to validate a real PDF/document ingestion path with Qdrant and parser metadata.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
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

FIXTURE_QDRANT_MARKERS = [
    "web-rag readiness verification fixture",
    "cobalt blue",
]

PDF_METADATA_KEYS = {
    "pdf_parser",
    "pdf_parser_requested",
    "pdf_parser_planned",
    "pdf_page_count",
    "pdf_text_page_count",
    "extracted_char_count",
}


@dataclass
class StreamResult:
    answer: str
    sources: list[dict[str, Any]]
    thread_id: str | None
    first_token_ms: int | None
    full_answer_ms: int
    completed: bool


@dataclass
class CaseResult:
    channel: str
    question: str
    thread_id: str | None
    first_token_ms: int | None
    full_answer_ms: int | None
    source_ids: list[str | None]
    passed: bool
    reason: str | None = None


FALLBACK_MARKERS = [
    "no matching content found",
    "no documents matched",
    "didn't find relevant documents",
    "don't have the specific details",
    "searched the web",
]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
    return ordered[idx]


def guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".md", ".markdown"}:
        return "text/markdown"
    if suffix in {".txt", ".text"}:
        return "text/plain"
    if suffix == ".csv":
        return "text/csv"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".xls":
        return "application/vnd.ms-excel"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


async def upload_document_path(
    client: httpx.AsyncClient,
    token: str,
    document_path: str,
    *,
    use_ocr: bool,
    pdf_parser_mode: str,
) -> str:
    path = Path(document_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Document path does not exist or is not a file: {path}")

    files = {
        "file": (
            path.name,
            path.read_bytes(),
            guess_mime_type(path),
        )
    }
    response = await client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        data={
            "use_ocr": str(use_ocr).lower(),
            "pdf_parser_mode": pdf_parser_mode,
        },
    )
    if response.status_code == 409:
        detail = response.json().get("detail", {})
        existing_id = detail.get("existing_document_id")
        if existing_id:
            return existing_id
    response.raise_for_status()
    return response.json()["id"]


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
        if data.get("status") == "not_found":
            raise RuntimeError(f"Document {document_id} was not found")
        if data.get("status") == "processed":
            return data
        if data.get("status") == "failed":
            raise RuntimeError(f"Document processing failed: {data.get('error_message')}")
        await asyncio.sleep(2)
    raise TimeoutError(f"Document {document_id} did not finish processing within 120s")


def parser_metadata_from_qdrant(qdrant: dict[str, Any]) -> dict[str, Any]:
    for sample in qdrant.get("samples") or []:
        metadata = sample.get("metadata") or {}
        if any(key in metadata for key in PDF_METADATA_KEYS):
            return metadata
    return {}


async def check_qdrant(
    client: httpx.AsyncClient,
    token: str,
    document_id: str,
    *,
    expected_markers: list[str] | None = None,
    require_pdf_metadata: bool = False,
) -> dict[str, Any]:
    response = await client.get(
        "/api/documents/check-qdrant",
        params={"document_id": document_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    data = response.json()
    if int(data.get("chunk_count") or 0) <= 0:
        raise AssertionError(f"Qdrant returned no chunks for document {document_id}")
    sample_text = "\n".join(str(sample.get("content") or "") for sample in data.get("samples") or [])
    sample_lower = sample_text.lower()
    if expected_markers and not any(marker.lower() in sample_lower for marker in expected_markers):
        raise AssertionError(f"Qdrant samples did not include expected readiness text for document {document_id}")
    if require_pdf_metadata:
        parser_metadata = parser_metadata_from_qdrant(data)
        if not parser_metadata:
            raise AssertionError(f"Qdrant samples did not include PDF parser metadata for document {document_id}")
        if not parser_metadata.get("pdf_parser"):
            raise AssertionError(f"Qdrant PDF parser metadata did not include pdf_parser for document {document_id}")
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
    completed = False

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
                completed = True
                break

    return StreamResult(
        answer="".join(answer_parts),
        sources=sources,
        thread_id=thread_id,
        first_token_ms=first_token_ms,
        full_answer_ms=int((time.perf_counter() - started) * 1000),
        completed=completed,
    )


def assert_answer(result: StreamResult, expected_fact: str, expected_document_id: str | None) -> None:
    if not result.completed:
        raise AssertionError("Stream ended without a done event")
    if not result.answer.strip():
        raise AssertionError("Stream returned an empty answer")
    answer_lower = result.answer.lower()
    for marker in FALLBACK_MARKERS:
        if marker in answer_lower:
            raise AssertionError(f"Answer contained fallback marker '{marker}'. Answer: {result.answer[:300]}")
    if expected_fact.lower() not in answer_lower:
        raise AssertionError(f"Answer did not include expected fact '{expected_fact}'. Answer: {result.answer[:300]}")
    document_source_ids = [
        source.get("document_id")
        for source in result.sources
        if source.get("document_id") and source.get("document_id") != "web_search"
    ]
    if not document_source_ids:
        raise AssertionError(f"Expected at least one document source, got {[source.get('document_id') for source in result.sources]}")
    if expected_document_id:
        source_ids = [source.get("document_id") for source in result.sources]
        if expected_document_id not in source_ids:
            raise AssertionError(f"Expected document {expected_document_id} in sources, got {source_ids}")


async def create_widget_session(client: httpx.AsyncClient, tenant_slug: str, origin: str) -> str:
    response = await client.post(
        "/api/widget/session",
        headers={"Origin": origin},
        json={"tenant_slug": tenant_slug},
    )
    response.raise_for_status()
    return response.json()["token"]


async def run_case(
    client: httpx.AsyncClient,
    channel: str,
    path: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    question: str,
    expected_fact: str,
    expected_document_id: str | None,
) -> CaseResult:
    try:
        result = await stream_chat(client, path, headers, payload)
        assert_answer(result, expected_fact, expected_document_id)
        return CaseResult(
            channel=channel,
            question=question,
            thread_id=result.thread_id,
            first_token_ms=result.first_token_ms,
            full_answer_ms=result.full_answer_ms,
            source_ids=[source.get("document_id") for source in result.sources],
            passed=True,
        )
    except Exception as exc:
        return CaseResult(
            channel=channel,
            question=question,
            thread_id=None,
            first_token_ms=None,
            full_answer_ms=None,
            source_ids=[],
            passed=False,
            reason=str(exc),
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Web-RAG retrieval correctness and latency.")
    parser.add_argument("--base-url", default=os.getenv("WEB_RAG_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--admin-token", default=os.getenv("WEB_RAG_ADMIN_TOKEN"))
    parser.add_argument("--chat-token", default=os.getenv("WEB_RAG_CHAT_TOKEN"))
    parser.add_argument("--document-id", default=os.getenv("WEB_RAG_DOCUMENT_ID"))
    parser.add_argument("--document-path", default=os.getenv("WEB_RAG_DOCUMENT_PATH"))
    parser.add_argument(
        "--validation-mode",
        choices=["auto", "fixture", "document"],
        default=os.getenv("WEB_RAG_VALIDATION_MODE", "auto"),
        help="auto runs fixture QA only when no document path/id is supplied.",
    )
    parser.add_argument("--use-ocr", action="store_true", default=env_bool("WEB_RAG_USE_OCR"))
    parser.add_argument("--pdf-parser-mode", default=os.getenv("WEB_RAG_PDF_PARSER_MODE", "auto"))
    parser.add_argument("--widget-tenant-slug", default=os.getenv("WEB_RAG_WIDGET_TENANT_SLUG"))
    parser.add_argument("--widget-origin", default=os.getenv("WEB_RAG_WIDGET_ORIGIN", "http://127.0.0.1:4173"))
    parser.add_argument("--skip-widget", action="store_true", help="Explicitly skip widget chat readiness checks.")
    parser.add_argument("--skip-chat", action="store_true", default=env_bool("WEB_RAG_SKIP_CHAT"), help="Skip authenticated and widget QA checks.")
    parser.add_argument("--first-token-ms", type=int, default=int(os.getenv("WEB_RAG_FIRST_TOKEN_MS", "3000")))
    parser.add_argument("--full-answer-ms", type=int, default=int(os.getenv("WEB_RAG_FULL_ANSWER_MS", "15000")))
    args = parser.parse_args()

    if not args.admin_token:
        print("WEB_RAG_ADMIN_TOKEN or --admin-token is required.", file=sys.stderr)
        return 2

    if args.document_path and args.document_id:
        print("Use either --document-path or --document-id, not both.", file=sys.stderr)
        return 2

    supplied_document = bool(args.document_path or args.document_id)
    if args.validation_mode == "document":
        validate_real_document = True
    elif args.validation_mode == "fixture":
        validate_real_document = False
    else:
        validate_real_document = supplied_document

    if args.document_path and not validate_real_document:
        print("--document-path requires document validation mode.", file=sys.stderr)
        return 2

    run_chat_checks = not args.skip_chat and not validate_real_document
    if run_chat_checks and not args.chat_token:
        print("WEB_RAG_CHAT_TOKEN or --chat-token is required.", file=sys.stderr)
        return 2
    if run_chat_checks and not args.skip_widget and not args.widget_tenant_slug:
        print("WEB_RAG_WIDGET_TENANT_SLUG or --widget-tenant-slug is required unless --skip-widget is set.", file=sys.stderr)
        return 2

    async with httpx.AsyncClient(base_url=args.base_url, timeout=180) as client:
        if args.document_path:
            document_id = await upload_document_path(
                client,
                args.admin_token,
                args.document_path,
                use_ocr=args.use_ocr,
                pdf_parser_mode=args.pdf_parser_mode,
            )
        else:
            document_id = args.document_id or await upload_fixture(client, args.admin_token)

        await wait_for_document(client, args.admin_token, document_id)
        qdrant = await check_qdrant(
            client,
            args.admin_token,
            document_id,
            expected_markers=None if validate_real_document else FIXTURE_QDRANT_MARKERS,
            require_pdf_metadata=validate_real_document,
        )
        parser_metadata = parser_metadata_from_qdrant(qdrant)

        case_results: list[CaseResult] = []
        if run_chat_checks:
            for question, expected_fact in QUESTIONS:
                case_results.append(
                    await run_case(
                        client,
                        "authenticated",
                        "/api/chat/stream",
                        {"Authorization": f"Bearer {args.chat_token}"},
                        {
                            "message": question,
                            "thread_id": None,
                            "use_documents": True,
                            "retrieval_mode": "hybrid",
                            "enable_web_search": False,
                            "enable_sql": False,
                        },
                        question,
                        expected_fact,
                        document_id,
                    )
                )

            if not args.skip_widget:
                widget_token = await create_widget_session(client, args.widget_tenant_slug, args.widget_origin)
                for question, expected_fact in QUESTIONS:
                    case_results.append(
                        await run_case(
                            client,
                            "widget",
                            "/api/widget/chat/stream",
                            {
                                "Authorization": f"Bearer {widget_token}",
                                "Origin": args.widget_origin,
                            },
                            {"message": question, "thread_id": None},
                            question,
                            expected_fact,
                            document_id,
                        )
                    )

        first_token_values = [r.first_token_ms for r in case_results if r.first_token_ms is not None]
        full_answer_values = [r.full_answer_ms for r in case_results if r.full_answer_ms is not None]
        first_token_p95 = percentile(first_token_values, 0.95)
        full_answer_p95 = percentile(full_answer_values, 0.95)
        failed_cases = [case for case in case_results if not case.passed]

        summary = {
            "validation_mode": "document" if validate_real_document else "fixture",
            "document_id": document_id,
            "document_path": args.document_path,
            "qdrant_chunk_count": qdrant.get("chunk_count"),
            "parser_metadata": parser_metadata,
            "authenticated_cases": sum(1 for case in case_results if case.channel == "authenticated"),
            "widget_cases": sum(1 for case in case_results if case.channel == "widget"),
            "case_results": [case.__dict__ for case in case_results],
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

        if failed_cases:
            raise AssertionError(f"{len(failed_cases)} readiness case(s) failed")
        if first_token_p95 is not None and first_token_p95 > args.first_token_ms:
            raise AssertionError(f"First-token p95 {first_token_p95}ms exceeds {args.first_token_ms}ms")
        if full_answer_p95 is not None and full_answer_p95 > args.full_answer_ms:
            raise AssertionError(f"Full-answer p95 {full_answer_p95}ms exceeds {args.full_answer_ms}ms")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
