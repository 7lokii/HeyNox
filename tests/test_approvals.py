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
