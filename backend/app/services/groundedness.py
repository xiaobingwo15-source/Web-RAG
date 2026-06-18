import asyncio
import json
import logging
import re

logger = logging.getLogger(__name__)

GROUNDEDNESS_THRESHOLD = 0.5
GROUNDEDNESS_LLM_HIGH = 0.0   # Always run LLM check — token overlap alone is unreliable
GROUNDEDNESS_LLM_LOW = 0.25   # Below this: call LLM to confirm

GROUNDEDNESS_CHECK_PROMPT = (
    "You are a fact-checker. Compare the ANSWER against the REFERENCE CONTEXT. "
    "Does the answer contain any major claims that are NOT directly supported by the reference context? "
    "Minor rewording and paraphrasing are acceptable. "
    "Reply with ONLY 'yes' (contains ungrounded claims) or 'no' (fully grounded)."
)

GROUNDEDNESS_CHECK_PROMPT_WEB = (
    "You are a fact-checker. The REFERENCE CONTEXT below contains TWO types of sources:\n"
    "1. INTERNAL DOCUMENTS (marked as [Document]) — the user's own knowledge base\n"
    "2. WEB SEARCH RESULTS (marked as [Web]) — supplementary information from the web\n\n"
    "Verify that each major claim in the ANSWER is supported by the INTERNAL DOCUMENTS specifically. "
    "Claims supported only by [Web] sources should be flagged as not grounded in the user's documents. "
    "Minor rewording and paraphrasing are acceptable. "
    "Reply with ONLY 'yes' (contains ungrounded claims) or 'no' (fully grounded in internal documents)."
)


def check_groundedness(answer: str, context_chunks: list[str]) -> float:
    """Return the fraction of meaningful answer tokens found in retrieved context."""
    if not context_chunks or not answer:
        return 0.0

    context_text = " ".join(context_chunks).lower()
    answer_lower = answer.lower()

    context_tokens = {token for token in context_text.split() if len(token) > 3}
    answer_tokens = {token for token in answer_lower.split() if len(token) > 3}

    if not answer_tokens:
        return 0.0

    return len(answer_tokens & context_tokens) / len(answer_tokens)


async def check_groundedness_with_llm(
    answer: str,
    context_chunks: list[str],
    client,
    model: str,
    web_mode: bool = False,
    use_claim_verification: bool = False,
) -> tuple[float, bool]:
    """Two-stage groundedness check: token-overlap pre-check + LLM verification.

    Args:
        answer: The generated answer text.
        context_chunks: Retrieved context chunks.
        client: LLM client for the verification call.
        model: Model name to use.
        web_mode: If True, use the web-aware prompt that verifies claims against
                  DOCUMENT chunks specifically, not web-sourced content.
        use_claim_verification: If True, decompose the answer into atomic claims and
                                verify each claim against context instead of using
                                token-overlap. Returns the claim-level groundedness
                                score as the primary score.

    Returns:
        (score, is_grounded) — score is the groundedness ratio, is_grounded is the final verdict.
    """
    # Claim-level verification path
    if use_claim_verification:
        try:
            claims = await decompose_into_claims(answer, client, model)
            if claims:
                claim_result = await verify_claims_against_context(claims, context_chunks, client, model)
                claim_score = claim_result["groundedness_score"]
                is_grounded = claim_score >= GROUNDEDNESS_THRESHOLD
                unsupported = claim_result["unsupported_claims"]
                logger.info(
                    f"Claim-level groundedness: score={claim_score:.3f}, "
                    f"supported={claim_result['supported_claims']}/{claim_result['total_claims']}, "
                    f"unsupported={unsupported}"
                )
                return claim_score, is_grounded
            else:
                logger.warning("Claim decomposition returned 0 claims, falling back to token-overlap")
        except Exception as e:
            logger.warning(f"Claim-level verification failed, falling back to token-overlap: {e}")

    score = check_groundedness(answer, context_chunks)

    # Fast path: clearly grounded (disabled at 0.0 — LLM check always runs)
    if score >= GROUNDEDNESS_LLM_HIGH:
        return score, True

    # Clearly ungrounded by token overlap — still verify with LLM to handle paraphrasing
    # Borderline zone (0.25-0.5) — use LLM to decide
    system_prompt = GROUNDEDNESS_CHECK_PROMPT_WEB if web_mode else GROUNDEDNESS_CHECK_PROMPT
    prompt_label = "web-aware" if web_mode else "standard"
    try:
        context_preview = "\n\n".join(c[:1500] for c in context_chunks[:5])
        user_msg = (
            f"REFERENCE CONTEXT:\n{context_preview}\n\n"
            f"ANSWER:\n{answer}\n\n"
            f"Is the answer grounded in the context? Reply ONLY 'yes' or 'no'."
        )
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=5,
                temperature=0,
            ),
            timeout=5.0,
        )
        raw = (response.choices[0].message.content or "").strip().lower()
        is_grounded = raw.startswith("no")  # "no" = no ungrounded claims = grounded
        logger.info(f"LLM groundedness check ({prompt_label}): score={score:.3f}, llm_raw='{raw}', is_grounded={is_grounded}")
        return score, is_grounded
    except Exception as e:
        logger.warning(f"LLM groundedness check failed, falling back to token-overlap: {e}")
        return score, score >= GROUNDEDNESS_THRESHOLD


CLAIM_DECOMPOSITION_PROMPT = (
    "You are a claim extractor. Break the following answer into atomic factual claims. "
    "Each claim should be a single, self-contained factual statement that can be independently verified. "
    "Return ONLY valid JSON in this exact format: {\"claims\": [\"claim1\", \"claim2\", ...]}. "
    "Do not include any other text."
)

CLAIM_VERIFICATION_PROMPT = (
    "You are a fact-checker. Determine whether the following claim is supported by the provided context. "
    "Reply with ONLY 'yes' if the claim is directly supported or 'no' if it is not. "
    "After your yes/no, you may add a brief reasoning separated by a colon (e.g., 'yes: the context states...')."
)

SENTENCE_ATTRIBUTION_PROMPT = (
    "You are a source attribution assistant. Given a sentence and a numbered list of context chunks, "
    "determine which chunk best supports the sentence. "
    "Reply with ONLY a JSON object: {\"source_index\": <0-based index>, \"support_score\": <0.0 to 1.0>}. "
    "If no chunk supports the sentence, set source_index to -1 and support_score to 0.0. "
    "Do not include any other text."
)


async def decompose_into_claims(answer: str, client, model: str) -> list[str]:
    """Decompose an answer into atomic factual claims using LLM.

    Args:
        answer: The generated answer text.
        client: LLM client for the decomposition call.
        model: Model name to use.

    Returns:
        List of atomic claim strings. Falls back to sentence splitting on parse failure.
    """
    if not answer or not answer.strip():
        logger.info("Claim decomposition: empty answer, returning 0 claims")
        return []

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": CLAIM_DECOMPOSITION_PROMPT},
                    {"role": "user", "content": f"ANSWER:\n{answer}"},
                ],
                max_tokens=1024,
                temperature=0,
            ),
            timeout=10.0,
        )
        raw = (response.choices[0].message.content or "").strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "claims" in parsed:
            claims = [c.strip() for c in parsed["claims"] if isinstance(c, str) and c.strip()]
            logger.info(f"Claim decomposition: extracted {len(claims)} claims via LLM")
            if claims:
                return claims

        logger.warning("Claim decomposition: LLM returned valid JSON but no usable claims, falling back to sentence split")
    except json.JSONDecodeError:
        logger.warning("Claim decomposition: failed to parse LLM JSON response, falling back to sentence split")
    except asyncio.TimeoutError:
        logger.warning("Claim decomposition: LLM call timed out, falling back to sentence split")
    except Exception as e:
        logger.warning(f"Claim decomposition: LLM call failed ({e}), falling back to sentence split")

    # Fallback: split on sentence-ending punctuation
    claims = [s.strip() for s in re.split(r'(?<=[.!?])\s+', answer) if s.strip()]
    logger.info(f"Claim decomposition: fallback sentence split produced {len(claims)} claims")
    return claims


async def verify_claims_against_context(
    claims: list[str],
    context_chunks: list[str],
    client,
    model: str,
) -> dict:
    """Verify each claim against context chunks using parallel LLM calls.

    Args:
        claims: List of atomic claim strings to verify.
        context_chunks: Retrieved context chunks for verification.
        client: LLM client for verification calls.
        model: Model name to use.

    Returns:
        Dict with keys: total_claims, supported_claims, unsupported_claims,
        groundedness_score, claim_details.
    """
    if not claims:
        logger.info("Claim verification: no claims to verify")
        return {
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
            "groundedness_score": 1.0,
            "claim_details": [],
        }

    if not context_chunks:
        logger.warning("Claim verification: no context chunks provided")
        return {
            "total_claims": len(claims),
            "supported_claims": 0,
            "unsupported_claims": list(claims),
            "groundedness_score": 0.0,
            "claim_details": [
                {"claim": c, "supported": False, "reasoning": "no context available"}
                for c in claims
            ],
        }

    context_preview = "\n\n".join(c[:1500] for c in context_chunks[:5])

    async def _verify_single(claim: str) -> dict:
        """Verify a single claim against the context."""
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": CLAIM_VERIFICATION_PROMPT},
                        {"role": "user", "content": f"CONTEXT:\n{context_preview}\n\nCLAIM:\n{claim}"},
                    ],
                    max_tokens=50,
                    temperature=0,
                ),
                timeout=8.0,
            )
            raw = (response.choices[0].message.content or "").strip().lower()
            # Parse verdict: look for "yes" or "no" at the start
            if raw.startswith("yes"):
                supported = True
                reasoning = raw.split(":", 1)[1].strip() if ":" in raw else "supported by context"
            elif raw.startswith("no"):
                supported = False
                reasoning = raw.split(":", 1)[1].strip() if ":" in raw else "not found in context"
            else:
                # Ambiguous — default to unsupported for safety
                supported = False
                reasoning = f"ambiguous response: {raw[:100]}"
            return {"claim": claim, "supported": supported, "reasoning": reasoning}
        except asyncio.TimeoutError:
            logger.warning(f"Claim verification timed out for: {claim[:80]}...")
            return {"claim": claim, "supported": False, "reasoning": "verification timed out"}
        except Exception as e:
            logger.warning(f"Claim verification failed for: {claim[:80]}... — {e}")
            return {"claim": claim, "supported": False, "reasoning": f"verification error: {e}"}

    # Run all claim verifications in parallel
    results = await asyncio.gather(*[_verify_single(claim) for claim in claims])
    claim_details = list(results)

    supported_count = sum(1 for d in claim_details if d["supported"])
    unsupported = [d["claim"] for d in claim_details if not d["supported"]]
    score = supported_count / len(claims) if claims else 1.0

    logger.info(
        f"Claim verification complete: {supported_count}/{len(claims)} supported, "
        f"score={score:.3f}, unsupported={unsupported}"
    )

    return {
        "total_claims": len(claims),
        "supported_claims": supported_count,
        "unsupported_claims": unsupported,
        "groundedness_score": score,
        "claim_details": claim_details,
    }


async def sentence_level_attribution(
    answer: str,
    context_chunks: list[str],
    client,
    model: str,
) -> list[dict]:
    """Attribute each sentence in the answer to its best supporting context chunk.

    Args:
        answer: The generated answer text.
        context_chunks: Retrieved context chunks for attribution.
        client: LLM client for attribution calls.
        model: Model name to use.

    Returns:
        List of dicts with keys: sentence, source_index, support_score, grounded.
        A sentence is grounded if support_score >= 0.5.
    """
    if not answer or not answer.strip():
        logger.info("Sentence attribution: empty answer, returning empty list")
        return []

    # Split into sentences: split on . ! ? followed by space or newline
    raw_sentences = re.split(r'(?<=[.!?])[\s]+', answer.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    if not sentences:
        logger.info("Sentence attribution: no valid sentences after splitting")
        return []

    if not context_chunks:
        logger.warning("Sentence attribution: no context chunks provided")
        return [
            {
                "sentence": s,
                "source_index": -1,
                "support_score": 0.0,
                "grounded": False,
            }
            for s in sentences
        ]

    # Build numbered context for the prompt
    numbered_chunks = "\n\n".join(
        f"[{i}] {chunk[:1500]}" for i, chunk in enumerate(context_chunks[:5])
    )

    async def _attribute_single(sentence: str) -> dict:
        """Find the best supporting chunk for a single sentence."""
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SENTENCE_ATTRIBUTION_PROMPT},
                        {
                            "role": "user",
                            "content": f"CONTEXT CHUNKS:\n{numbered_chunks}\n\nSENTENCE:\n{sentence}",
                        },
                    ],
                    max_tokens=50,
                    temperature=0,
                ),
                timeout=8.0,
            )
            raw = (response.choices[0].message.content or "").strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                source_index = parsed.get("source_index", -1)
                support_score = parsed.get("support_score", 0.0)

                # Validate source_index
                if not isinstance(source_index, int) or source_index < 0 or source_index >= len(context_chunks):
                    source_index = -1
                    support_score = 0.0

                if not isinstance(support_score, (int, float)):
                    support_score = 0.0

                support_score = max(0.0, min(1.0, float(support_score)))

                return {
                    "sentence": sentence,
                    "source_index": source_index,
                    "support_score": support_score,
                    "grounded": support_score >= 0.5,
                }
            else:
                logger.warning(f"Sentence attribution: unexpected JSON type for: {sentence[:60]}...")
                return {
                    "sentence": sentence,
                    "source_index": -1,
                    "support_score": 0.0,
                    "grounded": False,
                }

        except json.JSONDecodeError:
            logger.warning(f"Sentence attribution: failed to parse JSON for: {sentence[:60]}...")
            return {
                "sentence": sentence,
                "source_index": -1,
                "support_score": 0.0,
                "grounded": False,
            }
        except asyncio.TimeoutError:
            logger.warning(f"Sentence attribution: timed out for: {sentence[:60]}...")
            return {
                "sentence": sentence,
                "source_index": -1,
                "support_score": 0.0,
                "grounded": False,
            }
        except Exception as e:
            logger.warning(f"Sentence attribution: failed for: {sentence[:60]}... — {e}")
            return {
                "sentence": sentence,
                "source_index": -1,
                "support_score": 0.0,
                "grounded": False,
            }

    # Run all attributions in parallel
    results = await asyncio.gather(*[_attribute_single(s) for s in sentences])
    attributions = list(results)

    grounded_count = sum(1 for a in attributions if a["grounded"])
    logger.info(
        f"Sentence attribution complete: {grounded_count}/{len(attributions)} sentences grounded"
    )
    return attributions
