"""Provider selection and the OpenAI wire format.

The deployment target is an OpenAI key, so ``LLM_PROVIDER=openai`` must speak
``/chat/completions`` correctly and ``build_generation_provider`` must bind it
without any code change when the key slots in. HTTP is faked here; nothing in
these tests touches the network.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.llm import build_generation_provider
from scholarmind.generation.provider import GenerationRequest, Message


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture()
def captured_post(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeResponse:  # noqa: A002
        calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(
            {
                "id": "chatcmpl-123",
                "model": json["model"],
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "[]"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 8},
            }
        )

    monkeypatch.setattr("httpx.post", _post)
    return calls


def test_openai_provider_speaks_chat_completions(captured_post: list[dict[str, Any]]) -> None:
    """The request body, auth header and response mapping match the wire format."""
    from app.core.llm import OpenAIProvider

    provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")
    response = provider.generate(
        GenerationRequest(
            messages=[Message(role="system", content="sys"), Message(role="user", content="hello")],
            model="gpt-4o-mini",
            max_tokens=256,
        )
    )

    call = captured_post[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    body = call["json"]
    assert body["model"] == "gpt-4o-mini"
    assert body["max_tokens"] == 256
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert response.text == "[]"
    assert response.usage.input_tokens == 120
    assert response.usage.output_tokens == 8
    assert response.model == "gpt-4o-mini"


def test_openai_cost_estimate_uses_the_mini_tier(captured_post: list[dict[str, Any]]) -> None:
    from app.core.llm import OpenAIProvider

    provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")
    response = provider.generate(
        GenerationRequest(messages=[Message(role="user", content="q")], model="gpt-4o-mini")
    )
    # 120 input + 8 output tokens at $0.15/$0.60 per million -> far below a cent.
    assert 0 < response.cost_usd < 0.01


def test_build_generation_provider_binds_by_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key -> None (assistant abstains, drafting refuses). Key -> right class."""
    settings = Settings(llm_api_key="", llm_provider="openai")
    assert build_generation_provider(settings) is None

    settings = Settings(llm_api_key="sk-test", llm_provider="openai", llm_model="gpt-4o-mini")
    provider = build_generation_provider(settings)
    assert type(provider).__name__ == "OpenAIProvider"
    assert provider.model == "gpt-4o-mini"

    settings = Settings(llm_api_key="sk-test", llm_provider="anthropic")
    provider = build_generation_provider(settings)
    assert type(provider).__name__ == "AnthropicProvider"

    with pytest.raises(ValidationError):
        Settings(llm_provider="cohere")

