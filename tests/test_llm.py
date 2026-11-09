from typing import Any

import pytest

from nox.brain.llm import (
    AnthropicLlm,
    LlmError,
    OpenAiLlm,
    UnconfiguredLlm,
    build_llm,
)
from nox.brain.messages import Message
from nox.config import Config


def config_with(**llm: object) -> Config:
    base = {"base_url": "https://exemplo.test/v1", "model": "modelo-teste"}
    return Config.model_validate({"llm": {**base, **llm}})


def test_build_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOX_LLM_API_KEY", raising=False)
    with pytest.raises(LlmError, match="NOX_LLM_API_KEY"):
        build_llm(config_with())


def test_build_llm_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOX_LLM_API_KEY", "chave")
    with pytest.raises(LlmError, match="base_url"):
        build_llm(Config.model_validate({"llm": {"model": "m"}}))


def test_build_llm_picks_anthropic_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOX_LLM_API_KEY", "chave")
    assert isinstance(build_llm(config_with(api_format="anthropic")), AnthropicLlm)


def test_build_llm_picks_openai_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOX_LLM_API_KEY", "chave")
    assert isinstance(build_llm(config_with(api_format="openai")), OpenAiLlm)


def test_anthropic_client_parses_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(url=url, payload=payload, headers=headers)
        return {"content": [{"type": "text", "text": "Olá."}]}

    monkeypatch.setattr("nox.brain.llm._post_json", fake_post)
    client = AnthropicLlm("https://exemplo.test/v1", "chave", "modelo-teste")
    answer = client.complete([Message("user", "oi")], system="sistema")

    assert answer == "Olá."
    assert str(captured["url"]).endswith("/messages")
    assert captured["payload"]["system"] == "sistema"
    assert captured["headers"]["x-api-key"] == "chave"


def test_openai_client_sends_system_message(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(url=url, payload=payload, headers=headers)
        return {"choices": [{"message": {"content": "Olá."}}]}

    monkeypatch.setattr("nox.brain.llm._post_json", fake_post)
    client = OpenAiLlm("https://exemplo.test/v1", "chave", "modelo-teste")
    answer = client.complete([Message("user", "oi")], system="sistema")

    assert answer == "Olá."
    assert str(captured["url"]).endswith("/chat/completions")
    messages = captured["payload"]["messages"]
    assert messages[0] == {"role": "system", "content": "sistema"}


def test_empty_answer_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nox.brain.llm._post_json", lambda *args, **kwargs: {"content": []})
    client = AnthropicLlm("https://exemplo.test/v1", "chave", "modelo-teste")
    with pytest.raises(LlmError, match="vazia"):
        client.complete([Message("user", "oi")])


def test_unconfigured_client_explains_itself() -> None:
    client = UnconfiguredLlm("falta a chave")
    with pytest.raises(LlmError, match="falta a chave"):
        client.complete([Message("user", "oi")])
