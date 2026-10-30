"""The evidence-grounded assistant endpoint.

Flow
----
1. Retrieve candidate evidence chunks (hybrid search over the corpus).
2. Build the prompt with the evidence wrapped in an untrusted-content block.
3. Ask the model for structured claims with evidence ids.
4. Validate: every cited id must exist in the retrieved context, the referenced
   excerpt must support the claim, and dates/amounts are reconciled against the
   structured records.
5. Verify the claims with the claim-level verifier.
6. Persist an audit row so the answer can be replayed and measured later.

If the evidence does not support an answer, the endpoint returns an abstention
with what is missing - never a guess.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import parse_json_response
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.schemas.assistant import AssistantAnswerResponse, AssistantAskRequest, ClaimResponse, ConflictResponse
from services.api.app.services.retrieval import RetrievedChunk, retrieve

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _build_prompt(question: str, chunks: list[RetrievedChunk]) -> list[dict[str, str]]:
    from scholarmind.generation.prompts import EvidenceBlock, build_assistant_messages

    blocks = [
        EvidenceBlock(
            evidence_id=chunk.chunk_id,
            content=chunk.content,
            source_url=chunk.source_url,
            source_title=chunk.source_title,
            checked_at=chunk.checked_at,
            trust_tier=chunk.trust_tier,
            cycle_label=chunk.cycle_label,
        )
        for chunk in chunks
    ]
    return build_assistant_messages(question=question, blocks=blocks)


def _provider() -> Any:
    settings = get_settings()
    from app.core.llm import build_generation_provider

    return build_generation_provider(settings)


def _embedding_provider() -> Any:
    settings = get_settings()
    if not settings.embedding_api_key:
        return None
    from app.core.llm import OpenAICompatibleEmbeddingProvider

    return OpenAICompatibleEmbeddingProvider(
        api_key=settings.embedding_api_key, model=settings.embedding_model
    )


def _freshness_warnings(chunks: list[RetrievedChunk]) -> list[str]:
    warnings: list[str] = []
    stale = [chunk for chunk in chunks if chunk.freshness_state == "stale"]
    if stale:
        warnings.append(
            "Some cited pages have not been verified recently; their content may be out of date."
        )
    unreachable = [chunk for chunk in chunks if chunk.freshness_state == "failed"]
    if unreachable:
        warnings.append(
            "Some cited pages could not be re-checked on the last attempt; "
            "the text shown is from an earlier capture."
        )
    aggregator = [chunk for chunk in chunks if chunk.trust_tier == "aggregator"]
    if aggregator:
        warnings.append(
            "Some evidence comes from a listing site rather than an official source."
        )
    return warnings


@router.post(
    "/ask",
    response_model=AssistantAnswerResponse,
    dependencies=[
        Depends(rate_limit("assistant_minute", setting="rate_limit_assistant_per_min")),
        Depends(rate_limit("assistant_day", setting="rate_limit_assistant_per_day", window_seconds=86400)),
    ],
)
async def ask(
    payload: AssistantAskRequest,
    session: Session = Depends(get_db),
) -> AssistantAnswerResponse:
    """Answer a scholarship question from official evidence, or abstain."""
    settings = get_settings()

    embedding_provider = _embedding_provider()
    embedding: list[float] = []
    if embedding_provider is not None:
        from services.api.app.services.retrieval import embed_query

        embedding = embed_query(payload.question, embedding_provider, settings.embedding_model)

    retrieval = retrieve(
        session,
        payload.question,
        embedding=embedding,
        mode=payload.mode,
        top_k=payload.top_k,
        candidates=settings.retrieval_candidates,
        rrf_k=settings.retrieval_rrf_k,
        include_aggregators=payload.include_aggregators,
    )

    if not retrieval.chunks:
        return AssistantAnswerResponse(
            abstained=True,
            abstention_reason=(
                "No official source material was retrieved for this question, so I cannot "
                "answer it from evidence yet."
            ),
            missing_information=["a source page covering this scholarship"],
            retrieval={
                "mode": retrieval.mode,
                "mode_used": retrieval.mode_used,
                "degraded_reason": retrieval.degraded_reason,
                "embedding_available": retrieval.embedding_available,
                "top_k": retrieval.top_k,
                "lexical_hits": retrieval.lexical_count,
                "dense_hits": retrieval.dense_count,
                "returned": 0,
            },
            prompt_version="assistant-v1.0.0",
        )

    provider = _provider()
    if provider is None:
        return AssistantAnswerResponse(
            abstained=True,
            abstention_reason=(
                "The assistant is not configured with a language model in this "
                "environment, so it will not answer from memory."
            ),
            evidence=[chunk.to_excerpt() for chunk in retrieval.chunks],
            retrieval={"mode": retrieval.mode, "returned": len(retrieval.chunks)},
            prompt_version="assistant-v1.0.0",
        )

    from scholarmind.generation.provider import GenerationRequest, Message

    messages = _build_prompt(payload.question, retrieval.chunks)
    response = provider.generate(
        GenerationRequest(
            messages=[Message(role=message["role"], content=message["content"]) for message in messages],
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )
    )

    payload_json = parse_json_response(response.text)
    if payload_json is None:
        return AssistantAnswerResponse(
            abstained=True,
            abstention_reason="The assistant could not produce a structured answer from the evidence.",
            evidence=[chunk.to_excerpt() for chunk in retrieval.chunks],
            retrieval={"mode": retrieval.mode, "returned": len(retrieval.chunks)},
            model_id=response.model,
            latency_ms=response.latency_ms,
            cost_usd=response.cost_usd,
            prompt_version="assistant-v1.0.0",
        )

    excerpts = retrieval.as_excerpts()
    from scholarmind.generation.validation import Claim, validate_answer

    raw_claims = payload_json.get("claims") or []
    claims = [
        Claim(
            text=str(item.get("text", "")).strip(),
            evidence_ids=[str(i) for i in (item.get("evidence_ids") or [])],
            status=str(item.get("status") or "confirmed"),
            fact_ref=item.get("fact_ref"),
        )
        for item in raw_claims
        if isinstance(item, dict)
    ]

    validated = validate_answer(claims=claims, retrieved_chunks=excerpts)

    from scholarmind.generation.verifier import ClaimVerifier, LexicalEntailmentVerifier

    verifier = ClaimVerifier(LexicalEntailmentVerifier())
    report = verifier.verify(validated.claims, excerpts)

    supported = report.supported_claims
    unsupported = report.unsupported_claims

    answer_text = _compose_answer(supported, unsupported, payload_json)
    abstained = bool(payload_json.get("abstained")) or not supported

    conflicts = [
        ConflictResponse(
            field_name=item.get("field_name"),
            value_a=item.get("value_a"),
            value_b=item.get("value_b"),
            source_a=item.get("source_a"),
            source_b=item.get("source_b"),
            evidence_ids=[str(i) for i in (item.get("evidence_ids") or [])],
        )
        for item in (payload_json.get("conflicts") or [])
        if isinstance(item, dict)
    ]

    result = AssistantAnswerResponse(
        answer=answer_text,
        claims=[ClaimResponse(**item.to_dict()) for item in report.claims],
        abstained=abstained,
        abstention_reason=payload_json.get("abstention_reason"),
        missing_information=[str(i) for i in (payload_json.get("missing_information") or [])],
        conflicts=conflicts,
        freshness_warnings=_freshness_warnings(retrieval.chunks),
        warnings=[str(i) for i in (payload_json.get("warnings") or [])],
        follow_up_questions=[str(i) for i in (payload_json.get("follow_up_questions") or [])],
        evidence=[chunk.to_excerpt() for chunk in retrieval.chunks],
        retrieval={
            "mode": retrieval.mode,
            "mode_used": retrieval.mode_used,
            "degraded_reason": retrieval.degraded_reason,
            "embedding_available": retrieval.embedding_available,
            "top_k": retrieval.top_k,
            "rrf_k": retrieval.rrf_k,
            "lexical_hits": retrieval.lexical_count,
            "dense_hits": retrieval.dense_count,
            "returned": len(retrieval.chunks),
        },
        model_id=response.model,
        prompt_version="assistant-v1.0.0",
        citation_precision=report.citation_precision,
        latency_ms=response.latency_ms,
        cost_usd=response.cost_usd,
    )

    _persist_audit(session, payload, result, retrieval, response)
    return result


def _compose_answer(supported: list[Any], unsupported: list[Any], payload_json: dict[str, Any]) -> str:
    """Assemble the user-facing answer from verified claims."""
    if not supported:
        reason = payload_json.get("abstention_reason")
        return reason or "The official material reviewed does not establish an answer to this question."
    parts = [claim.claim.text for claim in supported]
    text = "\n".join(f"- {part}" for part in parts)
    if unsupported:
        text += (
            f"\n\n_{len(unsupported)} statement(s) could not be verified against the cited "
            "evidence and have been withheld._"
        )
    return text


def _persist_audit(
    session: Session,
    request: AssistantAskRequest,
    result: AssistantAnswerResponse,
    retrieval: Any,
    response: Any,
) -> None:
    """Store the audit row that makes the answer reproducible."""
    from sqlalchemy import text

    try:
        inserted = session.execute(
            text(
                """
                INSERT INTO answer_audits
                    (id, question, question_type, retrieved_chunk_ids, retrieval_config,
                     answer_claims, citation_map, validation_result, abstained, model_id,
                     prompt_version, embedding_model, latency_ms, cost_usd)
                VALUES (gen_random_uuid(), :question, :question_type, CAST(:chunk_ids AS jsonb),
                        CAST(:config AS jsonb), CAST(:claims AS jsonb), CAST(:citations AS jsonb),
                        CAST(:validation AS jsonb), :abstained, :model_id, :prompt_version,
                        :embedding_model, :latency_ms, :cost_usd)
                RETURNING id::text, created_at
                """
            ),
            {
                "question": request.question,
                "question_type": "assistant",
                "chunk_ids": json.dumps([chunk.chunk_id for chunk in retrieval.chunks]),
                "config": json.dumps({"mode": retrieval.mode, "top_k": retrieval.top_k, "rrf_k": retrieval.rrf_k}),
                "claims": json.dumps([claim.model_dump() for claim in result.claims]),
                "citations": json.dumps({str(index): claim.evidence_ids for index, claim in enumerate(result.claims)}),
                "validation": json.dumps({"citation_precision": result.citation_precision}),
                "abstained": result.abstained,
                "model_id": result.model_id,
                "prompt_version": result.prompt_version,
                "embedding_model": get_settings().embedding_model,
                "latency_ms": result.latency_ms,
                "cost_usd": result.cost_usd,
            },
        )
        audit = inserted.fetchone()
        if audit is not None:
            result.id = audit[0]
            result.answer_audit_id = audit[0]
            result.created_at = audit[1].isoformat() if audit[1] else None
        session.commit()
    except Exception:  # auditing must never break the answer
        session.rollback()
