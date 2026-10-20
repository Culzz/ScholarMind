"""Provider interface for generation and embeddings.

The core package defines the interface; the application layer provides the
concrete implementation. This keeps the domain logic free of vendor SDKs, so
the model can be swapped (or the whole provider mocked) without touching
retrieval, validation or evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable


@dataclass
class Message:
    """One chat message."""

    role: str  # system | user | assistant
    content: str


@dataclass
class GenerationRequest:
    """A request to a text-generation provider."""

    messages: list[Message]
    model: str
    max_tokens: int = 2048
    temperature: float = 0.0
    response_format: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    """Token usage for one call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class GenerationResponse:
    """A provider's response."""

    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingRequest:
    """A request to an embedding provider."""

    texts: list[str]
    model: str


@dataclass
class EmbeddingResponse:
    """Embeddings for the requested texts."""

    vectors: list[list[float]]
    model: str
    cost_usd: float = 0.0
    latency_ms: int = 0


@runtime_checkable
class GenerationProvider(Protocol):
    """A text-generation provider."""

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Produce a completion for the given request."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """An embedding provider."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed the given texts."""
        ...


class NullGenerationProvider:
    """A provider that always abstains.

    Used when no API key is configured, so the assistant degrades to "evidence
    insufficient" rather than failing the request or inventing an answer.
    """

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            text="",
            model="null-provider",
            latency_ms=0,
            raw={"abstained": True, "reason": "no_generation_provider_configured"},
        )


class NullEmbeddingProvider:
    """A provider that returns empty vectors (retrieval falls back to lexical)."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(vectors=[[] for _ in request.texts], model="null-provider")


def estimated_cost_usd(model: str, usage: Usage, *, price_per_mtok: dict[str, tuple[float, float]] | None = None) -> float:
    """Estimate the cost of a call from token usage.

    ``price_per_mtok`` maps a model family to (input price, output price) per
    million tokens. Unknown models cost zero rather than guessing.
    """
    if not price_per_mtok:
        return 0.0
    key = model.lower()
    for family, (input_price, output_price) in price_per_mtok.items():
        if family.lower() in key:
            return (
                usage.input_tokens / 1_000_000 * input_price
                + usage.output_tokens / 1_000_000 * output_price
            )
    return 0.0


def messages_to_dicts(messages: Sequence[Message]) -> list[dict[str, str]]:
    """Convert messages to the wire format providers expect."""
    return [{"role": message.role, "content": message.content} for message in messages]
