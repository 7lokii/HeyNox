"""Mensagens e histórico de conversa.

O histórico é limitado de propósito: uma conversa por voz não precisa de
contexto infinito e cada mensagem extra custa latência e dinheiro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass
class Conversation:
    """System prompt fixo e as últimas mensagens trocadas."""

    system: str
    limit: int = 12
    _messages: list[Message] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        self._messages.append(Message("user", text))
        self._trim()

    def add_assistant(self, text: str) -> None:
        self._messages.append(Message("assistant", text))
        self._trim()

    def undo_last(self) -> None:
        """Remove a última mensagem (usado quando o LLM falha a meio de um turno)."""
        if self._messages:
            self._messages.pop()

    def clear(self) -> None:
        self._messages.clear()

    @property
    def messages(self) -> tuple[Message, ...]:
        return tuple(self._messages)

    def request(self) -> tuple[str, tuple[Message, ...]]:
        """Devolve o system prompt e as mensagens prontas a enviar ao modelo."""
        return self.system, tuple(self._messages)

    def _trim(self) -> None:
        if len(self._messages) > self.limit:
            del self._messages[: len(self._messages) - self.limit]
        # Um turno nunca pode começar por uma resposta órfã.
        while self._messages and self._messages[0].role == "assistant":
            self._messages.pop(0)
