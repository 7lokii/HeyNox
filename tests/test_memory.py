import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from nox.brain.agent import Agent
from nox.brain.llm import EchoLlm
from nox.brain.messages import Message
from nox.memory.extract import extract_facts
from nox.memory.store import MemoryError, MemoryStore


@pytest.fixture
def store(tmp_path: Path):
    memory = MemoryStore(tmp_path / "nox.db")
    yield memory
    memory.close()


class RecordingLlm:
    name = "recording"

    def __init__(self) -> None:
        self.systems: list[str] = []

    def complete(self, messages: Sequence[Message], *, system: str = "") -> str:
        self.systems.append(system)
        return "certo"


def test_fact_is_stored_once(store: MemoryStore) -> None:
    assert store.add_fact("nome", "O utilizador chama-se Rui.") is True
    assert store.add_fact("nome", "O utilizador chama-se Rui.") is False
    assert [fact.text for fact in store.facts()] == ["O utilizador chama-se Rui."]


def test_search_finds_by_word_and_ignores_accents(store: MemoryStore) -> None:
    store.add_fact("nota", "O projeto HeyNox é local-first.")
    store.add_fact("gosto", "O utilizador gosta de café.")

    assert [fact.text for fact in store.search("projeto")] == ["O projeto HeyNox é local-first."]
    assert [fact.text for fact in store.search("cafe")] == ["O utilizador gosta de café."]


def test_search_without_useful_words_returns_nothing(store: MemoryStore) -> None:
    store.add_fact("nota", "Alguma coisa.")
    assert store.search("a e o") == []


def test_forget_removes_matching_facts(store: MemoryStore) -> None:
    store.add_fact("nome", "O utilizador chama-se Rui.")
    store.add_fact("gosto", "O utilizador gosta de café.")

    assert store.forget("Rui") == 1
    assert [fact.text for fact in store.facts()] == ["O utilizador gosta de café."]


def test_clear_facts_keeps_the_conversation(store: MemoryStore) -> None:
    store.add_fact("nome", "O utilizador chama-se Rui.")
    store.add_turn("local", "user", "olá")

    assert store.clear_facts() == 1
    assert store.facts() == []
    assert store.count_turns() == 1


def test_turns_are_returned_in_order(store: MemoryStore) -> None:
    store.add_turn("local", "user", "um")
    store.add_turn("local", "assistant", "dois")
    store.add_turn("outra", "user", "ignorado")

    assert store.recent_turns("local") == [("user", "um"), ("assistant", "dois")]


def test_export_and_import_round_trip(tmp_path: Path) -> None:
    source = MemoryStore(tmp_path / "a.db")
    source.add_fact("nome", "O utilizador chama-se Rui.")
    source.add_turn("local", "user", "olá")
    path = source.save_to(tmp_path / "memoria.json")
    source.close()

    target = MemoryStore(tmp_path / "b.db")
    turns, facts = target.load_from(path)
    assert (turns, facts) == (1, 1)
    assert [fact.text for fact in target.facts()] == ["O utilizador chama-se Rui."]
    target.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1


def test_import_of_invalid_file_is_reported(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "c.db")
    bad = tmp_path / "mau.json"
    bad.write_text("não é json", encoding="utf-8")
    with pytest.raises(MemoryError, match="não consegui ler"):
        memory.load_from(bad)
    memory.close()


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("Chamo-me Rui e prefiro respostas curtas.", 2),
        ("Não gosto de ruído de fundo.", 1),
        ("lembra-te que o projeto é local-first", 1),
        ("bom dia", 0),
    ],
)
def test_extraction_counts(phrase: str, expected: int) -> None:
    assert len(extract_facts(phrase)) == expected


def test_agent_learns_and_recalls(store: MemoryStore) -> None:
    agent = Agent(EchoLlm(), memory=store)

    agent.reply("chamo-me Rui")
    assert [fact.text for fact in store.facts()] == ["O utilizador chama-se Rui."]

    assert agent.reply("o que sabes sobre mim?") == "Sei isto: O utilizador chama-se Rui."


def test_agent_forgets(store: MemoryStore) -> None:
    agent = Agent(EchoLlm(), memory=store)
    agent.reply("chamo-me Rui")

    assert agent.reply("esquece Rui") == "Esqueci o que sabia sobre Rui."
    assert store.facts() == []


def test_agent_forgets_everything(store: MemoryStore) -> None:
    agent = Agent(EchoLlm(), memory=store)
    agent.reply("chamo-me Rui")

    assert agent.reply("esquece tudo") == "Esqueci uma coisa."
    assert agent.reply("esquece tudo") == "Não tinha nada guardado."


def test_agent_resumes_the_conversation(store: MemoryStore) -> None:
    store.add_turn("local", "user", "falamos de Lisboa")
    store.add_turn("local", "assistant", "sim")

    agent = Agent(EchoLlm(), memory=store)

    contents = [message.content for message in agent.conversation.messages]
    assert contents == ["falamos de Lisboa", "sim"]


def test_memory_reaches_the_system_prompt(store: MemoryStore) -> None:
    store.add_fact("nome", "O utilizador chama-se Rui.")
    llm = RecordingLlm()
    agent = Agent(llm, memory=store)

    agent.reply("fala-me de ti")

    assert "O utilizador chama-se Rui." in llm.systems[-1]


def test_turns_are_recorded(store: MemoryStore) -> None:
    agent = Agent(EchoLlm(), memory=store)
    agent.reply("olá")

    assert store.recent_turns("local") == [("user", "olá"), ("assistant", "(eco) olá")]
