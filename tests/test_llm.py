import io
from typing import Any

import pytest

from nox import __version__
from nox.brain.llm import (
    AnthropicLlm,
    LlmError,
    OpenAiLlm,
    UnconfiguredLlm,
    _post_json,
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


def test_post_json_identifies_heynox(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class Resposta:
        def __enter__(self) -> io.BytesIO:
            return io.BytesIO(b'{"ok": true}')

        def __exit__(self, *args: object) -> bool:
            return False

    def fake_urlopen(request, timeout):
        captured["user_agent"] = request.get_header("User-agent")
        captured["timeout"] = timeout
        return Resposta()

    monkeypatch.setattr("nox.brain.llm.urllib.request.urlopen", fake_urlopen)
    data = _post_json("https://exemplo.test/v1", {"x": 1}, {}, 5.0)

    assert data == {"ok": True}
    assert captured["user_agent"] == f"HeyNox/{__version__}"


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


def test_openai_client_sends_tools_in_its_dialect(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(payload=payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "list_dir",
                                    "arguments": '{"path": "E:/projetos"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }

    monkeypatch.setattr("nox.brain.llm._post_json", fake_post)
    client = OpenAiLlm("https://exemplo.test/v1", "chave", "modelo-teste")
    tools = [
        {
            "name": "list_dir",
            "description": "lista uma pasta",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        }
    ]
    reply = client.complete_with_tools([Message("user", "lista")], tools=tools)

    payload = captured["payload"]
    assert payload["tool_choice"] == "auto"
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["function"]["name"] == "list_dir"
    assert payload["tools"][0]["function"]["parameters"]["type"] == "object"
    assert reply.text == ""
    assert reply.tool_calls[0].name == "list_dir"
    assert reply.tool_calls[0].arguments == {"path": "E:/projetos"}
    assert reply.raw == [
        {"type": "tool_use", "id": "call_1", "name": "list_dir", "input": {"path": "E:/projetos"}}
    ]


def test_openai_client_replays_tool_history(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(payload=payload)
        return {"choices": [{"message": {"content": "Pronto."}}]}

    monkeypatch.setattr("nox.brain.llm._post_json", fake_post)
    client = OpenAiLlm("https://exemplo.test/v1", "chave", "modelo-teste")
    messages = [
        Message("user", "lista a pasta"),
        Message(
            "assistant",
            [{"type": "tool_use", "id": "call_1", "name": "list_dir", "input": {"path": "E:/"}}],
        ),
        Message(
            "user",
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_1",
                    "content": "a.txt",
                    "is_error": False,
                }
            ],
        ),
    ]
    answer = client.complete_with_tools(messages)

    chat = captured["payload"]["messages"]
    assert answer.text == "Pronto."
    assert chat[1]["role"] == "assistant"
    assert chat[1]["tool_calls"][0]["function"]["name"] == "list_dir"
    assert chat[1]["tool_calls"][0]["function"]["arguments"] == '{"path": "E:/"}'
    assert chat[2] == {"role": "tool", "tool_call_id": "call_1", "content": "a.txt"}


def test_post_json_retries_a_short_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    tentativas: list[int] = []
    esperas: list[float] = []

    class Resposta:
        def __enter__(self) -> io.BytesIO:
            return io.BytesIO(b'{"ok": true}')

        def __exit__(self, *args: object) -> bool:
            return False

    def fake_urlopen(request, timeout):
        tentativas.append(1)
        if len(tentativas) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                None,
                io.BytesIO(b'{"message": "Please try again in 3.5s"}'),
            )
        return Resposta()

    monkeypatch.setattr("nox.brain.llm.urllib.request.urlopen", fake_urlopen)
    data = _post_json("https://exemplo.test/v1", {"x": 1}, {}, 5.0, sleep=esperas.append)

    assert data == {"ok": True}
    assert len(tentativas) == 2
    assert esperas == [3.5]


def test_post_json_gives_up_on_a_long_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            None,
            io.BytesIO(b'{"message": "Please try again in 21.2s"}'),
        )

    monkeypatch.setattr("nox.brain.llm.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(LlmError, match="429"):
        _post_json("https://exemplo.test/v1", {"x": 1}, {}, 5.0, sleep=lambda _: None)
