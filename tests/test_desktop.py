from pathlib import Path

import pytest

from nox.config import Config
from nox.desktop.guard import EMERGENCY, DesktopError
from nox.safety.approvals import ApprovalBroker
from nox.safety.sandbox import Sandbox
from nox.tools.desktop import DesktopTool


class FakeApprovals(ApprovalBroker):
    def __init__(self, answer: bool = True) -> None:
        super().__init__(timeout=1.0)
        self.answer = answer
        self.requests: list[tuple[str, str, str]] = []

    def request(self, action: str, summary: str, detail: str = "") -> bool:
        self.requests.append((action, summary, detail))
        return self.answer


@pytest.fixture(autouse=True)
def _clear_emergency():
    EMERGENCY.clear()
    yield
    EMERGENCY.clear()


def build(
    tmp_path: Path,
    *,
    enabled: bool = True,
    approvals: FakeApprovals | None = None,
    confirm: bool = True,
    apps: tuple[str, ...] = ("notepad.exe",),
) -> DesktopTool:
    config = Config.model_validate(
        {
            "desktop": {
                "enabled": enabled,
                "confirm_actions": confirm,
                "allowed_apps": list(apps),
            },
            "security": {"allowed_paths": [str(tmp_path)]},
        }
    )
    sandbox = Sandbox(config, root=tmp_path)
    return DesktopTool(config.desktop, sandbox, approvals=approvals)


def test_disabled_by_default(tmp_path: Path) -> None:
    tool = build(tmp_path, enabled=False)
    result = tool.run({"action": "windows"})
    assert result.ok is False
    assert "desligado" in result.content


def test_windows_are_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nox.tools.desktop.windows.list_windows",
        lambda: [
            {"title": "Bloco de Notas", "width": 800, "height": 600, "active": True},
            {"title": "Explorador", "width": 1024, "height": 768, "active": False},
        ],
    )
    result = build(tmp_path).run({"action": "windows"})

    assert result.ok is True
    assert "Bloco de Notas *" in result.content
    assert "Explorador" in result.content


def test_screenshot_saves_a_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[Path] = []

    def fake_shot(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        saved.append(path)
        return path

    monkeypatch.setattr("nox.tools.desktop.screen.screenshot", fake_shot)
    result = build(tmp_path).run({"action": "screenshot"})

    assert result.ok is True
    assert saved and saved[0].suffix == ".png"
    assert saved[0].parent == tmp_path / "data" / "screenshots"


def test_ocr_reads_an_existing_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "ecra.png"
    image.write_bytes(b"png")
    monkeypatch.setattr("nox.tools.desktop.screen.ocr", lambda path: "texto do ecrã")

    result = build(tmp_path).run({"action": "ocr", "path": "ecra.png"})

    assert result.ok is True
    assert result.content == "texto do ecrã"


def test_ocr_rejects_missing_files(tmp_path: Path) -> None:
    result = build(tmp_path).run({"action": "ocr", "path": "nao-existe.png"})
    assert result.ok is False
    assert "não é um ficheiro" in result.content


def test_focus_needs_approval(tmp_path: Path) -> None:
    result = build(tmp_path, approvals=FakeApprovals(answer=False)).run(
        {"action": "focus", "window": "Notas"}
    )

    assert result.ok is False
    assert "não aprovado" in result.content


def test_focus_calls_the_window_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        "nox.tools.desktop.windows.focus", lambda title: called.append(title) or "Bloco de Notas"
    )
    approvals = FakeApprovals()

    result = build(tmp_path, approvals=approvals).run({"action": "focus", "window": "Notas"})

    assert result.ok is True
    assert called == ["Notas"]
    assert approvals.requests[0][0] == "desktop:focus"


def test_click_needs_coordinates(tmp_path: Path) -> None:
    result = build(tmp_path, approvals=FakeApprovals()).run({"action": "click", "x": 10})
    assert result.ok is False
    assert "coordenadas" in result.content


def test_click_needs_approval(tmp_path: Path) -> None:
    result = build(tmp_path, approvals=FakeApprovals(answer=False)).run(
        {"action": "click", "x": 10, "y": 20}
    )
    assert result.ok is False
    assert "não aprovado" in result.content


def test_click_is_forwarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int, str, int]] = []
    monkeypatch.setattr(
        "nox.tools.desktop.keyboard.click",
        lambda x, y, button="left", clicks=1: calls.append((x, y, button, clicks)) or "feito",
    )
    approvals = FakeApprovals()

    result = build(tmp_path, approvals=approvals).run(
        {"action": "click", "x": 10, "y": 20, "button": "right", "clicks": 2}
    )

    assert result.ok is True
    assert calls == [(10, 20, "right", 2)]
    assert "Clicar em (10, 20)" in approvals.requests[0][1]


def test_type_is_forwarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    typed: list[str] = []
    monkeypatch.setattr(
        "nox.tools.desktop.keyboard.type_text", lambda text: typed.append(text) or "escrito"
    )

    result = build(tmp_path, approvals=FakeApprovals()).run({"action": "type", "text": "olá mundo"})

    assert result.ok is True
    assert typed == ["olá mundo"]


def test_invalid_keys_are_refused() -> None:
    from nox.desktop import input as keyboard

    with pytest.raises(DesktopError, match="não permitida"):
        keyboard.press("ctrl+rm -rf")


def test_open_only_allowed_apps(tmp_path: Path) -> None:
    result = build(tmp_path, approvals=FakeApprovals()).run(
        {"action": "open", "app": "powershell.exe"}
    )
    assert result.ok is False
    assert "não está na lista" in result.content


def test_open_runs_an_allowed_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[list[str]] = []
    monkeypatch.setattr(
        "nox.tools.desktop.subprocess.Popen", lambda args, shell=False: started.append(args)
    )

    result = build(tmp_path, approvals=FakeApprovals()).run(
        {"action": "open", "app": "notepad.exe"}
    )

    assert result.ok is True
    assert started == [["notepad.exe"]]


def test_emergency_stops_everything(tmp_path: Path) -> None:
    EMERGENCY.trigger()

    result = build(tmp_path, approvals=FakeApprovals()).run({"action": "windows"})

    assert result.ok is False
    assert "emergência" in result.content


def test_stop_action_works_even_when_disabled(tmp_path: Path) -> None:
    result = build(tmp_path, enabled=False).run({"action": "stop"})

    assert result.ok is True
    assert EMERGENCY.active is True


def test_read_only_actions_need_no_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nox.tools.desktop.windows.list_windows", lambda: [])
    tool = build(tmp_path, approvals=None, confirm=True)

    assert tool.run({"action": "windows"}).ok is True


def test_actions_without_an_interface_are_refused(tmp_path: Path) -> None:
    result = build(tmp_path, approvals=None, confirm=True).run({"action": "click", "x": 1, "y": 2})

    assert result.ok is False
    assert "aprovação" in result.content
