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

from nox.automation.routines import RoutineStore
from nox.brain.llm import LlmClient, LlmError, UnconfiguredLlm, build_llm
from nox.brain.messages import Conversation
from nox.brain.prompt import system_prompt
from nox.config import Config
from nox.integrations.github import GitHub
from nox.memory.extract import extract_facts
from nox.memory.store import Fact, MemoryStore, resolve_memory_path
from nox.paths import install_dir
from nox.safety.approvals import ApprovalBroker
from nox.safety.sandbox import Sandbox
from nox.skills import load_skills, skill_index
from nox.tools.base import ToolRegistry
from nox.tools.browser import build_browser_tools
from nox.tools.files import build_file_tools
from nox.tools.github import build_github_tools
from nox.tools.mcp import build_mcp_tools
from nox.tools.notes import build_notes_tools
from nox.tools.routines import build_routine_tools
from nox.tools.shell import build_shell_tools
from nox.tools.skills import build_skill_tools
from nox.tools.subagent import SpawnAgentTool
from nox.tools.web import build_web_tools

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
_RECALL_HINTS = (
    "o que sabes sobre mim",
    "o que sabes de mim",
    "o que te lembras",
    "que sabes sobre mim",
)


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
    memory: MemoryStore | None = None
    session: str = "local"
    history_turns: int = 12
    tools: ToolRegistry | None = None
    max_steps: int = 4
    # Texto extra para o system prompt (índice de skills, por exemplo).
    extra_system: str = ""
    conversation: Conversation = field(init=False)
    _stop: Event = field(default_factory=Event, repr=False, init=False)
    _base_system: str = field(default="", repr=False, init=False)

    def __post_init__(self) -> None:
        self._base_system = system_prompt(voice=self.voice) + self.extra_system
        self.conversation = Conversation(self._base_system)
        if self.memory is not None:
            for role, text in self.memory.recent_turns(self.session, self.history_turns):
                if role == "user":
                    self.conversation.add_user(text)
                elif role == "assistant":
                    self.conversation.add_assistant(text)

    def reply(self, text: str) -> str:
        """Responde a uma frase do utilizador. Levanta LlmError se o modelo falhar."""
        text = text.strip()
        if not text:
            return ""

        self.conversation.add_user(text)
        self._remember("user", text)
        self._learn(text)

        local = self.local_answer(text)
        if local is not None:
            self.conversation.add_assistant(local)
            self._remember("assistant", local)
            return local

        self.conversation.system = self._base_system + self._memory_block(text)
        try:
            answer = self._reply_with_tools() if self.tools is not None else self._reply_plain()
        except LlmError:
            self.conversation.undo_last()
            raise

        self.conversation.add_assistant(answer)
        self._remember("assistant", answer)
        return answer

    def _reply_plain(self) -> str:
        system, messages = self.conversation.request()
        answer = self.llm.complete(messages, system=system).strip()
        if not answer:
            raise LlmError("o modelo devolveu uma resposta vazia")
        return answer

    def _reply_with_tools(self) -> str:
        """Deixa o modelo pedir ferramentas até ter resposta.

        Cada pedido é executado dentro do sandbox, registado na auditoria, e o
        resultado volta ao modelo como `tool_result`. O ciclo para quando o
        modelo responde em texto ou quando esgota `max_steps`.
        """
        assert self.tools is not None
        definitions = self.tools.definitions()

        for _ in range(self.max_steps):
            system, messages = self.conversation.request()
            reply = self.llm.complete_with_tools(messages, system=system, tools=definitions)
            if not reply.tool_calls:
                answer = reply.text.strip()
                if not answer:
                    raise LlmError("o modelo devolveu uma resposta vazia")
                return answer

            self.conversation.add_raw("assistant", reply.raw)
            results = []
            for call in reply.tool_calls:
                outcome = self.tools.run(call.name, call.arguments)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": outcome.content,
                        "is_error": not outcome.ok,
                    }
                )
            self.conversation.add_raw("user", results)

        return "Não consegui resolver isso: dei voltas a mais com as ferramentas."

    def local_answer(self, text: str) -> str | None:
        """Resposta sem modelo, ou None para deixar seguir para o LLM."""
        memory_reply = self._memory_command(text)
        if memory_reply is not None:
            return memory_reply

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

    def _memory_command(self, text: str) -> str | None:
        """Comandos de memória: ver, esquecer. Não passam pelo modelo."""
        if self.memory is None:
            return None

        normalized = normalize(text)
        if any(hint in normalized for hint in _RECALL_HINTS):
            facts = self.memory.facts(limit=20)
            if not facts:
                return "Ainda não sei nada sobre ti."
            listed = "; ".join(fact.text.rstrip(".") for fact in facts)
            return f"Sei isto: {listed}."

        if normalized.startswith("esquece tudo"):
            removed = self.memory.clear_facts()
            if not removed:
                return "Não tinha nada guardado."
            return "Esqueci uma coisa." if removed == 1 else f"Esqueci {removed} coisas."

        match = re.match(r"(?i)^\s*esquece(?:-te de)?\s+(?P<what>.+)", text)
        if match:
            what = match.group("what").strip().rstrip(" .!?")
            if not what:
                return None
            removed = self.memory.forget(what)
            if removed:
                return f"Esqueci o que sabia sobre {what}."
            return f"Não tinha nada guardado sobre {what}."
        return None

    def _memory_block(self, text: str) -> str:
        """Factos relevantes para esta frase, para o modelo ter contexto."""
        if self.memory is None:
            return ""
        chosen: list[Fact] = []
        seen: set[int] = set()
        for fact in [*self.memory.facts(limit=6), *self.memory.search(text, limit=4)]:
            if fact.id in seen:
                continue
            seen.add(fact.id)
            chosen.append(fact)
            if len(chosen) >= 8:
                break
        if not chosen:
            return ""
        lines = "\n".join(f"- {fact.text}" for fact in chosen)
        return f"\nO que sabes do utilizador (usa só se for útil):\n{lines}\n"

    def _remember(self, role: str, text: str) -> None:
        if self.memory is not None:
            self.memory.add_turn(self.session, role, text)

    def _learn(self, text: str) -> None:
        if self.memory is None:
            return
        for kind, fact in extract_facts(text):
            self.memory.add_fact(kind, fact)

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


def build_agent(
    config: Config,
    *,
    voice: bool = False,
    approvals: ApprovalBroker | None = None,
) -> Agent:
    """Agente a partir da config. Sem chave, degrada para respostas locais."""
    try:
        llm = build_llm(config)
    except LlmError as exc:
        llm = UnconfiguredLlm(str(exc))
    memory = MemoryStore(resolve_memory_path(config)) if config.memory.enabled else None
    skills = load_skills()

    tools = None
    if config.tools.enabled:
        sandbox = Sandbox(config, root=install_dir())
        base_tools = [
            *build_file_tools(
                sandbox,
                approvals=approvals,
                confirm_writes=config.tools.confirm_writes,
            ),
            *build_shell_tools(
                sandbox,
                timeout=config.tools.command_timeout,
                approvals=approvals,
            ),
            *build_web_tools(),
            *build_browser_tools(sandbox, approvals=approvals),
            *build_notes_tools(sandbox),
            *build_github_tools(GitHub(config, sandbox)),
            *build_routine_tools(RoutineStore()),
            *build_skill_tools(skills),
            *build_mcp_tools(config),
        ]
        # O sub-agente vê as mesmas ferramentas, menos `spawn_agent`: sem isto
        # podia abrir sub-agentes em cadeia até esgotar a máquina.
        sub_tools = ToolRegistry(base_tools)

        def sub_agent() -> Agent:
            return Agent(
                llm,
                voice=False,
                memory=None,
                tools=sub_tools,
                max_steps=config.tools.max_steps,
                extra_system=skill_index(skills),
            )

        tools = ToolRegistry([*base_tools, SpawnAgentTool(sub_agent)])

    return Agent(
        llm,
        voice=voice,
        memory=memory,
        history_turns=config.memory.history_turns,
        tools=tools,
        max_steps=config.tools.max_steps,
        extra_system=skill_index(skills),
    )
