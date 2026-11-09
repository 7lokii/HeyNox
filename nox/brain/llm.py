"""Clientes LLM.

Só biblioteca padrão: o núcleo não ganha dependências por falar com um modelo.
Cada cliente expõe `complete(messages, system=...)` e devolve texto simples.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any, Protocol

from nox.brain.messages import Message
from nox.config import Config, NoxError

ANTHROPIC_VERSION = "2023-06-01"


class LlmError(NoxError):
    """O modelo não está configurado, não respondeu ou devolveu lixo."""


class LlmClient(Protocol):
    name: str

    def complete(self, messages: Sequence[Message], *, system: str = "") -> str:
        """Devolve a resposta do modelo em texto simples."""
        ...


class EchoLlm:
    """Cliente determinístico para testes e para correr sem rede."""

    name = "echo"

    def complete(self, messages: Sequence[Message], *, system: str = "") -> str:
        last = next((m for m in reversed(messages) if m.role == "user"), None)
        return f"(eco) {last.content}" if last else ""


class UnconfiguredLlm:
    """Sem chave configurada: as respostas locais continuam a funcionar.

    O erro só aparece quando o modelo é mesmo necessário, em vez de impedir o
    Nox de arrancar por falta de uma chave.
    """

    name = "unconfigured"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def complete(self, messages: Sequence[Message], *, system: str = "") -> str:
        raise LlmError(self._reason)


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 — só http(s), definido no config
        url, data=body, headers={**headers, "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()[:300]
        raise LlmError(f"o modelo respondeu {exc.code} {exc.reason}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LlmError(f"sem ligação a {url}: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise LlmError(f"{url} não respondeu em {timeout:.0f}s") from exc
    if not isinstance(data, dict):
        raise LlmError("resposta do modelo em formato inesperado")
    return data


def _anthropic_text(data: dict[str, Any]) -> str:
    blocks = data.get("content") or []
    text = "".join(
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    if not text:
        raise LlmError("o modelo devolveu uma resposta vazia")
    return text


def _openai_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise LlmError("o modelo devolveu uma resposta vazia")
    message = choices[0].get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        raise LlmError("o modelo devolveu uma resposta vazia")
    return text


class AnthropicLlm:
    """Endpoint no formato Anthropic Messages (`POST /messages`)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.4,
        timeout: float = 30.0,
    ) -> None:
        self.name = f"anthropic:{model}"
        self._url = base_url.rstrip("/") + "/messages"
        self._key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout

    def complete(self, messages: Sequence[Message], *, system: str = "") -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages if m.role != "system"
            ],
        }
        if system:
            payload["system"] = system
        if self._temperature:
            payload["temperature"] = self._temperature
        data = _post_json(
            self._url,
            payload,
            {"x-api-key": self._key, "anthropic-version": ANTHROPIC_VERSION},
            self._timeout,
        )
        return _anthropic_text(data)


class OpenAiLlm:
    """Endpoint compatível com OpenAI (`POST /chat/completions`)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.4,
        timeout: float = 30.0,
    ) -> None:
        self.name = f"openai:{model}"
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout

    def complete(self, messages: Sequence[Message], *, system: str = "") -> str:
        chat: list[dict[str, str]] = []
        if system:
            chat.append({"role": "system", "content": system})
        chat.extend({"role": m.role, "content": m.content} for m in messages)
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": chat,
        }
        data = _post_json(
            self._url, payload, {"Authorization": f"Bearer {self._key}"}, self._timeout
        )
        return _openai_text(data)


def build_llm(config: Config) -> LlmClient:
    """Constrói o cliente a partir da config, com erros que dizem o que falta."""
    settings = config.llm
    if not settings.base_url.strip():
        raise LlmError("llm.base_url não está definido no config.yaml")
    if not settings.model.strip():
        raise LlmError("llm.model não está definido no config.yaml")

    api_key = os.environ.get(settings.api_key_env, "").strip()
    if not api_key:
        raise LlmError(
            f"falta a chave do modelo: define {settings.api_key_env} no .env "
            "(ou usa o modo local, sem LLM)"
        )

    options = {
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
        "timeout": settings.timeout,
    }
    if settings.api_format == "anthropic":
        return AnthropicLlm(settings.base_url, api_key, settings.model, **options)
    return OpenAiLlm(settings.base_url, api_key, settings.model, **options)
