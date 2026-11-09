from datetime import datetime

import pytest

from nox.brain.agent import Agent, normalize
from nox.brain.llm import EchoLlm, LlmError
from nox.brain.messages import Conversation


def fixed_clock() -> datetime:
    return datetime(2026, 11, 9, 14, 32)


class FailingLlm:
    name = "failing"

    def complete(self, messages, *, system: str = "") -> str:
        raise LlmError("o modelo caiu")

    def complete_with_tools(self, messages, *, system: str = "", tools=()):
        raise LlmError("o modelo caiu")


def test_normalize_removes_accents_and_punctuation() -> None:
    assert normalize("Que horas são?!") == "que horas sao"


def test_local_answer_for_time() -> None:
    agent = Agent(EchoLlm(), clock=fixed_clock)
    assert agent.reply("Que horas são?") == "São 14h32."


def test_local_answer_for_time_uses_singular_verb() -> None:
    agent = Agent(EchoLlm(), clock=lambda: datetime(2026, 11, 9, 1, 5))
    assert agent.reply("diz-me as horas") == "É 1h05."


def test_local_answer_for_date() -> None:
    agent = Agent(EchoLlm(), clock=fixed_clock)
    assert agent.reply("que dia é hoje?") == "Hoje é segunda-feira, 9 de novembro de 2026."


def test_local_answer_for_thanks() -> None:
    agent = Agent(EchoLlm(), clock=fixed_clock)
    assert agent.reply("obrigado") == "De nada."


def test_long_question_goes_to_the_model() -> None:
    agent = Agent(EchoLlm(), clock=fixed_clock)
    answer = agent.reply("a que horas é o jantar de hoje?")
    assert answer.startswith("(eco)")


def test_empty_input_returns_empty_string() -> None:
    agent = Agent(EchoLlm(), clock=fixed_clock)
    assert agent.reply("   ") == ""
    assert agent.conversation.messages == ()


def test_turn_is_recorded_in_history() -> None:
    agent = Agent(EchoLlm(), clock=fixed_clock)
    agent.reply("olá")
    roles = [message.role for message in agent.conversation.messages]
    assert roles == ["user", "assistant"]


def test_history_is_trimmed_and_never_starts_with_assistant() -> None:
    conversation = Conversation("sistema", limit=4)
    for index in range(6):
        conversation.add_user(f"pergunta {index}")
        conversation.add_assistant(f"resposta {index}")

    assert len(conversation.messages) == 4
    assert conversation.messages[0].role == "user"


def test_model_failure_rolls_back_the_question() -> None:
    agent = Agent(FailingLlm(), clock=fixed_clock)
    with pytest.raises(LlmError):
        agent.reply("fala-me de Lisboa")
    assert agent.conversation.messages == ()


def test_reset_clears_history() -> None:
    agent = Agent(EchoLlm(), clock=fixed_clock)
    agent.reply("olá")
    agent.reset()
    assert agent.conversation.messages == ()


def test_stop_and_resume() -> None:
    agent = Agent(EchoLlm(), clock=fixed_clock)
    assert agent.stopped is False
    agent.stop()
    assert agent.stopped is True
    agent.resume()
    assert agent.stopped is False
