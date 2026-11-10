import threading
import time

from nox.safety.approvals import ApprovalBroker


def _wait_for_pending(broker: ApprovalBroker) -> list[dict]:
    for _ in range(200):
        pending = broker.pending()
        if pending:
            return pending
        time.sleep(0.01)
    raise AssertionError("o pedido não apareceu")


def test_approval_waits_for_a_yes() -> None:
    broker = ApprovalBroker(timeout=2.0)
    result: dict[str, bool] = {}

    thread = threading.Thread(
        target=lambda: result.setdefault("ok", broker.request("write_file", "Criar x", "+ x"))
    )
    thread.start()
    pending = _wait_for_pending(broker)
    assert pending[0]["summary"] == "Criar x"
    assert pending[0]["detail"] == "+ x"

    assert broker.decide(pending[0]["id"], True) is True
    thread.join(timeout=2)
    assert result["ok"] is True
    assert broker.pending() == []


def test_approval_waits_for_a_no() -> None:
    broker = ApprovalBroker(timeout=2.0)
    result: dict[str, bool] = {}

    thread = threading.Thread(target=lambda: result.setdefault("ok", broker.request("x", "y")))
    thread.start()
    pending = _wait_for_pending(broker)
    broker.decide(pending[0]["id"], False)
    thread.join(timeout=2)

    assert result["ok"] is False


def test_silence_is_a_no() -> None:
    broker = ApprovalBroker(timeout=0.05)
    assert broker.request("write_file", "Criar x") is False


def test_unknown_approval_is_rejected() -> None:
    assert ApprovalBroker().decide("nao-existe", True) is False


def test_cancel_all_refuses_what_is_pending() -> None:
    broker = ApprovalBroker(timeout=2.0)
    result: dict[str, bool] = {}

    thread = threading.Thread(target=lambda: result.setdefault("ok", broker.request("x", "y")))
    thread.start()
    _wait_for_pending(broker)

    broker.cancel_all()
    thread.join(timeout=2)

    assert result["ok"] is False
    assert broker.pending() == []


def test_full_access_approves_at_once_and_records_it(monkeypatch) -> None:
    records: list = []

    class FakeAudit:
        def record(self, entry) -> None:
            records.append(entry)

    monkeypatch.setattr("nox.safety.approvals.AuditLog", FakeAudit)
    broker = ApprovalBroker(timeout=0.01, full_access=True)

    start = time.monotonic()
    allowed = broker.request("shell", "correr comando", "rm -rf /tmp/x")
    elapsed = time.monotonic() - start

    assert allowed is True
    assert elapsed < 0.5
    assert broker.pending() == []
    assert records and records[0].tool == "aprovação:auto:shell"
    assert records[0].detail == "acesso total"


def test_full_access_can_be_switched_off_without_restarting(monkeypatch) -> None:
    class FakeAudit:
        def record(self, entry) -> None:
            return

    monkeypatch.setattr("nox.safety.approvals.AuditLog", FakeAudit)
    broker = ApprovalBroker(timeout=0.05, full_access=True)

    broker.set_full_access(False)

    assert broker.full_access is False
    assert broker.request("shell", "sem ninguém para decidir") is False


def test_agent_with_full_access_runs_a_command_nobody_approved(monkeypatch, tmp_path) -> None:
    """Sem interface, correr um comando fora da lista era recusado por falta de quem decidisse."""
    from nox.brain.agent import build_agent
    from nox.config import Config

    class FakeAudit:
        def __init__(self, *args, **kwargs) -> None:
            self.entries: list = []

        def record(self, entry) -> None:
            self.entries.append(entry)

    monkeypatch.setattr("nox.safety.approvals.AuditLog", FakeAudit)
    config = Config.model_validate(
        {
            "tools": {"full_access": True},
            "memory": {"enabled": False, "sqlite_path": str(tmp_path / "x.db")},
        }
    )

    agent = build_agent(config)
    assert agent.tools is not None

    result = agent.tools.run("run_command", {"command": "echo acesso-total"})

    assert result.ok is True, result.content
    assert "acesso-total" in result.content


def test_without_full_access_the_same_command_is_refused(monkeypatch, tmp_path) -> None:
    from nox.brain.agent import build_agent
    from nox.config import Config

    class FakeAudit:
        def record(self, entry) -> None:
            return

    monkeypatch.setattr("nox.safety.approvals.AuditLog", FakeAudit)
    config = Config.model_validate(
        {
            "tools": {"full_access": False},
            "memory": {"enabled": False, "sqlite_path": str(tmp_path / "y.db")},
        }
    )

    agent = build_agent(config)
    assert agent.tools is not None

    result = agent.tools.run("run_command", {"command": "echo sem-aprovacao"})

    assert result.ok is False
    assert "aprov" in result.content.lower()
