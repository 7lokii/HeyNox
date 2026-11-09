import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from nox.brain.agent import Agent
from nox.brain.llm import EchoLlm
from nox.config import Config
from nox.memory.store import MemoryStore
from nox.ui.server import NoxApp, build_server
from nox.ui.state import NoxState


@pytest.fixture
def server(tmp_path):
    store = MemoryStore(tmp_path / "nox.db")
    # Sem voz nos testes: sintetizar chamaria a rede e atrasaria a suite.
    config = Config.model_validate({"nox": {"voice_enabled": False}})
    app = NoxApp(config, agent=Agent(EchoLlm(), memory=store))
    httpd, port = build_server(app, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", app
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        store.close()
        store.close()


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def test_state_records_turns_and_status() -> None:
    state = NoxState()
    state.add_turn("user", "olá")
    state.add_turn("assistant", "olá!")
    state.set_status("a ouvir")

    snapshot = state.snapshot()

    assert [turn["role"] for turn in snapshot["turns"]] == ["user", "assistant"]
    assert snapshot["status"] == "a ouvir"
    assert snapshot["voice"] is False


def test_state_ignores_empty_text() -> None:
    state = NoxState()
    state.add_turn("assistant", "   ")
    assert state.snapshot()["turns"] == []


def test_state_stops_being_voice_when_stopped() -> None:
    state = NoxState()
    state.set_voice(True)
    assert state.snapshot()["status"] == "a arrancar"

    state.set_status("a falar")
    state.set_voice(False)
    assert state.snapshot()["status"] == "parado"


def test_index_page_is_served(server) -> None:
    base, _ = server
    with urllib.request.urlopen(base + "/", timeout=5) as response:  # noqa: S310
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "<title>Nox</title>" in body


def test_say_returns_the_answer_and_records_it(server) -> None:
    base, app = server

    answer = post_json(base + "/api/say", {"text": "olá"})["answer"]

    assert answer == "(eco) olá"
    assert [turn["text"] for turn in app.state.snapshot()["turns"]] == ["olá", "(eco) olá"]


def test_say_rejects_empty_text(server) -> None:
    base, _ = server
    request = urllib.request.Request(  # noqa: S310
        base + "/api/say",
        data=json.dumps({"text": "  "}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)  # noqa: S310
    assert exc.value.code == 400


def test_state_endpoint_reflects_the_conversation(server) -> None:
    base, _ = server
    post_json(base + "/api/say", {"text": "olá"})

    state = get_json(base + "/api/state")

    assert len(state["turns"]) == 2
    assert state["voice"] is False


def test_memory_endpoint_lists_and_forgets(server) -> None:
    base, app = server
    assert app.agent.memory is not None
    app.agent.memory.add_fact("nome", "O utilizador chama-se Rui.")

    facts = get_json(base + "/api/memory")["facts"]
    assert [fact["text"] for fact in facts] == ["O utilizador chama-se Rui."]

    removed = post_json(base + "/api/memory/forget", {"pattern": "Rui"})["removed"]
    assert removed == 1
    assert get_json(base + "/api/memory")["facts"] == []


def test_state_reports_who_is_speaking() -> None:
    state = NoxState()
    assert state.snapshot()["source"] == "none"

    state.set_input_levels([0.4] + [0.0] * 47)
    assert state.snapshot()["source"] == "user"

    state.set_levels([0.6] + [0.0] * 47)
    assert state.snapshot()["source"] == "nox"


def test_state_endpoint_has_no_pending_approvals(server) -> None:
    base, _ = server
    assert get_json(base + "/api/state")["approvals"] == []


def test_approval_round_trip_through_the_api(server) -> None:
    base, app = server
    outcome: dict[str, bool] = {}
    thread = threading.Thread(
        target=lambda: outcome.setdefault(
            "ok", app.approvals.request("write_file", "Criar nota.txt", "+ olá")
        )
    )
    thread.start()

    pending: list[dict] = []
    for _ in range(200):
        pending = get_json(base + "/api/state")["approvals"]
        if pending:
            break
        time.sleep(0.01)
    assert pending[0]["summary"] == "Criar nota.txt"

    decided = post_json(base + "/api/approvals", {"id": pending[0]["id"], "approved": True})
    thread.join(timeout=2)

    assert decided["decided"] is True
    assert outcome["ok"] is True
    assert get_json(base + "/api/state")["approvals"] == []


def test_unknown_approval_id_is_reported(server) -> None:
    base, _ = server
    assert post_json(base + "/api/approvals", {"id": "nao-existe", "approved": True}) == {
        "decided": False
    }
