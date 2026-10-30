"""Schemas for the evidence-grounded assistant."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ClaimStatus = Literal["confirmed", "uncertain", "needs_verification"]


class AssistantAskRequest(BaseModel):
    """A question to the research assistant."""

    question: str = Field(min_length=3, max_length=2000)
    scholarship_id: str | None = None
    cycle_id: str | None = None
    top_k: int = Field(default=20, ge=1, le=50)
    mode: Literal["hybrid", "lexical", "dense"] = "hybrid"
    include_aggregators: bool = False


class ClaimResponse(BaseModel):
    """One claim in an answer, with its evidence and verification status."""

    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: ClaimStatus = "uncertain"
    verification: dict[str, Any] = Field(default_factory=dict)
    unverified_reason: str | None = None


class ConflictResponse(BaseModel):
    """A disagreement between two official sources."""

    field_name: str | None = None
    value_a: Any = None
    value_b: Any = None
    source_a: str | None = None
    source_b: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class AssistantAnswerResponse(BaseModel):
    """The assistant's answer to one question."""

    id: str | None = None
    created_at: str | None = None
    answer: str = ""
    claims: list[ClaimResponse] = Field(default_factory=list)
    abstained: bool = False
    abstention_reason: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    conflicts: list[ConflictResponse] = Field(default_factory=list)
    freshness_warnings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    model_id: str | None = None
    prompt_version: str | None = None
    citation_precision: float | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    answer_audit_id: str | None = None
