from pathlib import Path

import pytest

from nox.config import Config
from nox.safety.sandbox import Sandbox
from nox.tools.notes import NotesTool


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    config = Config.model_validate({"security": {"allowed_paths": [str(tmp_path)]}})
    return Sandbox(config, root=tmp_path)


def test_add_and_list_notes(sandbox: Sandbox, tmp_path: Path) -> None:
    tool = NotesTool(sandbox)

    assert tool.run({"action": "add", "text": "reunião às 10"}).ok is True
    path = tmp_path / "data" / "notes.md"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# Notas do Nox")
    assert "reunião às 10" in content

    listed = tool.run({"action": "list"})
    assert listed.ok is True
    assert "reunião às 10" in listed.content


def test_list_without_notes(sandbox: Sandbox) -> None:
    result = NotesTool(sandbox).run({"action": "list"})
    assert result.ok is True
    assert result.content == "ainda não há notas"


def test_empty_note_is_refused(sandbox: Sandbox) -> None:
    result = NotesTool(sandbox).run({"action": "add", "text": "   "})
    assert result.ok is False
    assert "falta o texto" in result.content


def test_unknown_action_is_reported(sandbox: Sandbox) -> None:
    result = NotesTool(sandbox).run({"action": "apagar"})
    assert result.ok is False
    assert "ação desconhecida" in result.content
