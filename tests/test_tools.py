from pathlib import Path

import pytest

from nox.config import Config
from nox.safety.audit import AuditEntry, AuditLog
from nox.safety.sandbox import Sandbox, SandboxError
from nox.tools.base import ToolRegistry
from nox.tools.files import build_file_tools
from nox.tools.shell import build_shell_tools


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    config = Config.model_validate(
        {
            "security": {
                "allowed_paths": [str(tmp_path)],
                "blocked_paths": [".env", ".git"],
                "allowed_commands": ["echo", "git status"],
            }
        }
    )
    return Sandbox(config, root=tmp_path)


def test_allowed_path_resolves(sandbox: Sandbox, tmp_path: Path) -> None:
    target = tmp_path / "nota.txt"
    target.write_text("olá", encoding="utf-8")
    assert sandbox.resolve("nota.txt") == target


def test_path_outside_the_sandbox_is_refused(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError, match="fora das pastas"):
        sandbox.resolve("C:/Windows/System32/drivers/etc/hosts")


def test_blocked_names_are_refused(sandbox: Sandbox, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SEGREDO=1", encoding="utf-8")
    with pytest.raises(SandboxError, match="bloqueada"):
        sandbox.resolve(".env")


def test_allowed_command_passes(sandbox: Sandbox) -> None:
    assert sandbox.check_command("echo  ola   mundo") == ["echo", "ola", "mundo"]


def test_command_outside_the_list_is_refused(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError, match="não está na lista"):
        sandbox.check_command("rm -rf /")


def test_shell_chaining_is_refused(sandbox: Sandbox) -> None:
    for command in ("echo ola && rm -rf /", "git status; del tudo", "echo `whoami`"):
        with pytest.raises(SandboxError, match="caracteres de shell"):
            sandbox.check_command(command)


def test_read_file_returns_content(sandbox: Sandbox, tmp_path: Path) -> None:
    (tmp_path / "nota.txt").write_text("linha 1\nlinha 2", encoding="utf-8")
    tools = ToolRegistry(build_file_tools(sandbox), audit=AuditLog(tmp_path / "audit.jsonl"))

    result = tools.run("read_file", {"path": "nota.txt"})

    assert result.ok is True
    assert "linha 2" in result.content


def test_read_file_outside_the_sandbox_is_denied(sandbox: Sandbox, tmp_path: Path) -> None:
    tools = ToolRegistry(build_file_tools(sandbox), audit=AuditLog(tmp_path / "audit.jsonl"))

    result = tools.run("read_file", {"path": "C:/Windows/win.ini"})

    assert result.ok is False
    assert "fora das pastas" in result.content


def test_run_command_executes_and_reports(sandbox: Sandbox, tmp_path: Path) -> None:
    tools = ToolRegistry(build_shell_tools(sandbox), audit=AuditLog(tmp_path / "audit.jsonl"))

    result = tools.run("run_command", {"command": "echo ola"})

    assert result.ok is True
    assert "ola" in result.content


def test_run_command_refuses_unknown_commands(sandbox: Sandbox, tmp_path: Path) -> None:
    tools = ToolRegistry(build_shell_tools(sandbox), audit=AuditLog(tmp_path / "audit.jsonl"))

    result = tools.run("run_command", {"command": "curl http://exemplo.pt"})

    assert result.ok is False
    assert "não está na lista" in result.content


def test_unknown_tool_is_reported(sandbox: Sandbox, tmp_path: Path) -> None:
    tools = ToolRegistry(build_file_tools(sandbox), audit=AuditLog(tmp_path / "audit.jsonl"))
    assert tools.run("apagar_tudo", {}).ok is False


def test_audit_records_every_call(sandbox: Sandbox, tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    tools = ToolRegistry(build_file_tools(sandbox), audit=AuditLog(path))
    (tmp_path / "nota.txt").write_text("olá", encoding="utf-8")

    tools.run("read_file", {"path": "nota.txt"})
    tools.run("read_file", {"path": ".env"})

    entries = AuditLog(path).entries()
    assert len(entries) == 2
    assert entries[0]["tool"] == "read_file"
    assert entries[0]["ok"] is True
    assert entries[1]["ok"] is False


def test_audit_survives_an_unwritable_path(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "pasta" / "audit.jsonl")
    log.record(AuditEntry(tool="x", arguments={}, ok=True, duration_ms=1))
    assert log.entries()
