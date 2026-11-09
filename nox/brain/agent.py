"""Orquestrador: decide entre resposta local imediata e LLM.

Perguntas triviais (horas, data) não passam pelo modelo. Ganham latência zero,
funcionam sem rede e não custam nada — o que num assistente por voz é a
diferença entre parecer instantâneo e parecer lento.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from threading import Event

from nox.brain.llm import LlmClient, LlmError, UnconfiguredLlm, build_llm
from nox.brain.messages import Conversation
from nox.brain.prompt import system_prompt
from nox.config import Config

WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
MONTHS = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

# Um enunciado curto é quase sempre um comando direto. A partir de seis palavras
# já pode ser "a que horas é o jantar?", que não deve receber a hora atual.
LOCAL_ANSWER_MAX_WORDS = 5

_HOURS_HINTS = ("que horas", "horas sao", "diz as horas", "dizme as horas")
_DATE_HINTS = (
    "que dia e hoje",
    "que dia estamos",
    "que data e hoje",
    "data de hoje",
    "que dia e",
)
_THANKS_HINTS = ("obrigado", "obrigada")


def normalize(text: str) -> str:
    """Minúsculas, sem acentos e sem pontuação — para comparar comandos."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    # O hífen cola palavras em pt-PT ("diz-me" -> "dizme"); os outros sinais separam.
    stripped = re.sub(r"[-–—]", "", stripped)
    return re.sub(r"[^a-z0-9 ]+", " ", stripped).strip()


@dataclass
class Agent:
    """Mantém a conversa e responde. Uma instância por sessão."""

    llm: LlmClient
    voice: bool = False
    clock: Callable[[], datetime] = datetime.now
    conversation: Conversation = field(init=False)
    _stop: Event = field(default_factory=Event, repr=False, init=False)

    def __post_init__(self) -> None:
        self.conversation = Conversation(system_prompt(voice=self.voice))

    def reply(self, text: str) -> str:
        """Responde a uma frase do utilizador. Levanta LlmError se o modelo falhar."""
        text = text.strip()
        if not text:
            return ""

        self.conversation.add_user(text)
        local = self.local_answer(text)
        if local is not None:
            self.conversation.add_assistant(local)
            return local

        system, messages = self.conversation.request()
        try:
            answer = self.llm.complete(messages, system=system).strip()
        except LlmError:
            self.conversation.undo_last()
            raise
        if not answer:
            self.conversation.undo_last()
            raise LlmError("o modelo devolveu uma resposta vazia")

        self.conversation.add_assistant(answer)
        return answer

    def local_answer(self, text: str) -> str | None:
        """Resposta sem modelo, ou None para deixar seguir para o LLM."""
        normalized = normalize(text)
        if len(normalized.split()) > LOCAL_ANSWER_MAX_WORDS:
            return None

        now = self.clock()
        if any(hint in normalized for hint in _HOURS_HINTS):
            verb = "É" if now.hour in (0, 1) else "São"
            return f"{verb} {now.hour}h{now.minute:02d}."
        if any(hint in normalized for hint in _DATE_HINTS):
            day = WEEKDAYS[now.weekday()]
            return f"Hoje é {day}, {now.day} de {MONTHS[now.month - 1]} de {now.year}."
        if any(hint in normalized for hint in _THANKS_HINTS):
            return "De nada."
        return None

    def reset(self) -> None:
        self.conversation.clear()

    def stop(self) -> None:
        """Sinaliza ao pipeline de voz que pare de falar e de ouvir."""
        self._stop.set()

    def resume(self) -> None:
        self._stop.clear()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()


def build_agent(config: Config, *, voice: bool = False) -> Agent:
    """Agente a partir da config. Sem chave, degrada para respostas locais."""
    try:
        llm = build_llm(config)
    except LlmError as exc:
        llm = UnconfiguredLlm(str(exc))
    return Agent(llm, voice=voice)
