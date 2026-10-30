"""LLM and embedding providers (application layer).

The core package defines the provider interfaces; this module implements them
for the Anthropic API and for any OpenAI-compatible embeddings endpoint. Vendor
SDKs are imported lazily so the service still starts without them installed.
"""

from __future__ import annotations

import json
from typing import Any

from scholarmind.generation.provider import (
    EmbeddingRequest,
    EmbeddingResponse,
    GenerationRequest,
    GenerationResponse,
    Usage,
    estimated_cost_usd,
    messages_to_dicts,
)

# Prices are kept here (not in the core) so the cost report can be reproduced
# even if a provider changes its published pricing. Specific families come
# before the "gpt" catch-all because the lookup is a substring match.
DEFAULT_PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
    "gpt": (0.50, 1.50),
    "claude": (3.0, 15.0),
    "text-embedding": (0.02, 0.0),
}


class AnthropicProvider:
    """Text generation through the Anthropic Messages API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
        price_per_mtok: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.prices = price_per_mtok or DEFAULT_PRICES

    def _client(self) -> Any:
        import anthropic

        return anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout_seconds)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Call the Messages API and return a normalised response."""
        import time

        client = self._client()
        system = "\n".join(m.content for m in request.messages if m.role == "system")
        conversation = [m for m in request.messages if m.role != "system"]

        started = time.perf_counter()
        response = client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=system or None,
            messages=messages_to_dicts(conversation),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        usage = Usage(
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
        )
        return GenerationResponse(
            text=text,
            model=response.model,
            usage=usage,
            cost_usd=estimated_cost_usd(response.model, usage, price_per_mtok=self.prices),
            latency_ms=latency_ms,
            raw={"id": getattr(response, "id", None), "stop_reason": getattr(response, "stop_reason", None)},
        )


class OpenAIProvider:
    """Text generation through any OpenAI-compatible ``/chat/completions`` endpoint.

    Uses plain HTTP instead of the vendor SDK so the service still starts
    without it installed, mirroring the embedding provider.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 60,
        price_per_mtok: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.prices = price_per_mtok or DEFAULT_PRICES

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Call chat completions and return a normalised response."""
        import time

        import httpx

        payload = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages_to_dicts(request.messages),
        }
        if request.response_format:
            payload["response_format"] = request.response_format

        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        latency_ms = int((time.perf_counter() - started) * 1000)

        choices = body.get("choices") or []
        text = "".join(
            str(choice.get("message", {}).get("content") or "") for choice in choices
        )
        usage_payload = body.get("usage") or {}
        usage = Usage(
            input_tokens=usage_payload.get("prompt_tokens", 0),
            output_tokens=usage_payload.get("completion_tokens", 0),
        )
        return GenerationResponse(
            text=text,
            model=body.get("model", request.model),
            usage=usage,
            cost_usd=estimated_cost_usd(request.model, usage, price_per_mtok=self.prices),
            latency_ms=latency_ms,
            raw={"id": body.get("id", None), "finish_reason": choices[0].get("finish_reason") if choices else None},
        )


def build_generation_provider(settings: Any) -> Any:
    """Bind the configured generation provider, or None when unset.

    ``LLM_PROVIDER`` selects the wire protocol: ``openai`` (default for a fresh
    deployment) speaks ``/chat/completions`` against ``LLM_BASE_URL``, and
    ``anthropic`` speaks the Messages API. The model, key and base URL come
    from the same settings, so a key slotting in needs no code change.
    """
    if not settings.llm_api_key:
        return None
    if settings.llm_provider == "openai":
        return OpenAIProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )
    return AnthropicProvider(api_key=settings.llm_api_key, model=settings.llm_model)




class OpenAICompatibleEmbeddingProvider:
    """Embeddings from any OpenAI-compatible ``/embeddings`` endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 30,
        price_per_mtok: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.prices = price_per_mtok or DEFAULT_PRICES

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed texts and return vectors in input order."""
        import time

        import httpx

        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": request.model, "input": request.texts},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        latency_ms = int((time.perf_counter() - started) * 1000)

        vectors = [item["embedding"] for item in payload.get("data", [])]
        total_tokens = payload.get("usage", {}).get("total_tokens", 0)
        usage = Usage(input_tokens=total_tokens, output_tokens=0)
        return EmbeddingResponse(
            vectors=vectors,
            model=payload.get("model", request.model),
            cost_usd=estimated_cost_usd(request.model, usage, price_per_mtok=self.prices),
            latency_ms=latency_ms,
        )


def parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from a model response.

    Models sometimes wrap JSON in prose or a code fence; this extracts the
    outermost object and returns ``None`` when nothing parseable is present, so
    the caller can abstain rather than guess.
    """
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
