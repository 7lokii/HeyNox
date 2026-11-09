from pathlib import Path

import pytest

from nox.config import Config
from nox.safety.approvals import ApprovalBroker
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


def test_path_outside_the_sandbox_is_refused(sandbox: Sandbox, tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match="fora das pastas"):
        sandbox.resolve(str(tmp_path.parent / "fora.txt"))


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

    result = tools.run("read_file", {"path": str(tmp_path.parent / "fora.txt")})

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


class FakeApprovals(ApprovalBroker):
    """Aprova ou recusa sem interface, e guarda o que lhe foi pedido."""

    def __init__(self, answer: bool = True) -> None:
        super().__init__(timeout=1.0)
        self.answer = answer
        self.requests: list[tuple[str, str, str]] = []

    def request(self, action: str, summary: str, detail: str = "") -> bool:
        self.requests.append((action, summary, detail))
        return self.answer


def _write_tools(sandbox: Sandbox, tmp_path: Path, *, answer: bool = True):
    approvals = FakeApprovals(answer)
    tools = ToolRegistry(
        build_file_tools(sandbox, approvals=approvals, confirm_writes=True),
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )
    return tools, approvals


def test_write_file_creates_after_approval(sandbox: Sandbox, tmp_path: Path) -> None:
    tools, approvals = _write_tools(sandbox, tmp_path)

    result = tools.run("write_file", {"path": "nota.txt", "content": "olá\n"})

    assert result.ok is True
    assert (tmp_path / "nota.txt").read_text(encoding="utf-8") == "olá\n"
    action, summary, detail = approvals.requests[0]
    assert action == "write_file"
    assert "Criar nota.txt" in summary
    assert "+olá" in detail


def test_write_file_denied_leaves_the_file_alone(sandbox: Sandbox, tmp_path: Path) -> None:
    target = tmp_path / "nota.txt"
    target.write_text("antigo", encoding="utf-8")
    tools, _ = _write_tools(sandbox, tmp_path, answer=False)

    result = tools.run("write_file", {"path": "nota.txt", "content": "novo"})

    assert result.ok is False
    assert "não aprovado" in result.content
    assert target.read_text(encoding="utf-8") == "antigo"


def test_write_file_without_an_interface_is_refused(sandbox: Sandbox, tmp_path: Path) -> None:
    tools = ToolRegistry(
        build_file_tools(sandbox, confirm_writes=True),
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )

    result = tools.run("write_file", {"path": "nota.txt", "content": "olá"})

    assert result.ok is False
    assert not (tmp_path / "nota.txt").exists()


def test_write_file_refuses_blocked_names(sandbox: Sandbox, tmp_path: Path) -> None:
    tools, _ = _write_tools(sandbox, tmp_path)

    result = tools.run("write_file", {"path": ".env", "content": "SEGREDO=1"})

    assert result.ok is False
    assert "bloqueada" in result.content


def test_write_file_outside_the_sandbox_is_refused(sandbox: Sandbox, tmp_path: Path) -> None:
    tools, _ = _write_tools(sandbox, tmp_path)

    result = tools.run("write_file", {"path": str(tmp_path.parent / "fora.txt"), "content": "x"})

    assert result.ok is False
    assert "fora das pastas" in result.content


def test_write_file_with_the_same_content_does_not_ask(sandbox: Sandbox, tmp_path: Path) -> None:
    (tmp_path / "nota.txt").write_text("igual", encoding="utf-8")
    tools, approvals = _write_tools(sandbox, tmp_path, answer=False)

    result = tools.run("write_file", {"path": "nota.txt", "content": "igual"})

    assert result.ok is True
    assert approvals.requests == []


def test_edit_file_replaces_one_occurrence(sandbox: Sandbox, tmp_path: Path) -> None:
    (tmp_path / "nota.txt").write_text("a\nb\nc\n", encoding="utf-8")
    tools, approvals = _write_tools(sandbox, tmp_path)

    result = tools.run("edit_file", {"path": "nota.txt", "old": "b", "new": "B"})

    assert result.ok is True
    assert (tmp_path / "nota.txt").read_text(encoding="utf-8") == "a\nB\nc\n"
    assert approvals.requests[0][0] == "edit_file"
    assert "-b" in approvals.requests[0][2]
    assert "+B" in approvals.requests[0][2]


def test_edit_file_needs_a_unique_match(sandbox: Sandbox, tmp_path: Path) -> None:
    (tmp_path / "nota.txt").write_text("x\ny\nx\n", encoding="utf-8")
    tools, _ = _write_tools(sandbox, tmp_path)

    result = tools.run("edit_file", {"path": "nota.txt", "old": "x", "new": "z"})

    assert result.ok is False
    assert "aparece 2 vezes" in result.content


def test_edit_file_reports_missing_text(sandbox: Sandbox, tmp_path: Path) -> None:
    (tmp_path / "nota.txt").write_text("a\n", encoding="utf-8")
    tools, _ = _write_tools(sandbox, tmp_path)

    result = tools.run("edit_file", {"path": "nota.txt", "old": "nada", "new": "x"})

    assert result.ok is False
    assert "não encontrei" in result.content


def test_approved_command_outside_the_list_runs(sandbox: Sandbox, tmp_path: Path) -> None:
    approvals = FakeApprovals(True)
    tools = ToolRegistry(
        build_shell_tools(sandbox, approvals=approvals),
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )

    result = tools.run("run_command", {"command": "git --version"})

    assert result.ok is True
    assert approvals.requests[0][0] == "run_command"
    assert "git --version" in approvals.requests[0][1]


def test_denied_command_does_not_run(sandbox: Sandbox, tmp_path: Path) -> None:
    approvals = FakeApprovals(False)
    tools = ToolRegistry(
        build_shell_tools(sandbox, approvals=approvals),
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )

    result = tools.run("run_command", {"command": "git --version"})

    assert result.ok is False
    assert "não aprovado" in result.content


def test_destructive_command_is_blocked_even_with_approval(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    approvals = FakeApprovals(True)
    tools = ToolRegistry(
        build_shell_tools(sandbox, approvals=approvals),
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )

    result = tools.run("run_command", {"command": "rm -rf /"})

    assert result.ok is False
    assert "bloqueado" in result.content
    assert approvals.requests == []


def test_command_without_an_interface_explains_itself(sandbox: Sandbox, tmp_path: Path) -> None:
    tools = ToolRegistry(
        build_shell_tools(sandbox),
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )

    result = tools.run("run_command", {"command": "git --version"})

    assert result.ok is False
    assert "não está na lista" in result.content
    assert "interface" in result.content
