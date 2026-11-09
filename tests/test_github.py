from pathlib import Path

import pytest

from nox.config import Config
from nox.integrations.github import CommandResult, GitHub, GitHubError
from nox.safety.sandbox import Sandbox, SandboxError


class FakeRunner:
    """Responde por prefixo de comando e guarda o que foi chamado."""

    def __init__(self, responses: dict[str, CommandResult] | None = None) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self.responses = responses or {}

    def __call__(self, args, cwd: Path) -> CommandResult:
        argv = list(args)
        self.calls.append((argv, cwd))
        joined = " ".join(argv)
        for prefix, result in self.responses.items():
            if joined.startswith(prefix):
                return result
        return CommandResult(argv, 0, "", "")

    def called(self, prefix: str) -> bool:
        return any(" ".join(argv).startswith(prefix) for argv, _ in self.calls)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "projects" / "demo"
    (path / ".git").mkdir(parents=True)
    return path


def build(tmp_path: Path, runner: FakeRunner, **github: object) -> GitHub:
    config = Config.model_validate(
        {
            "github": {"allow_push_to_main": False, "require_tests": False, **github},
            "security": {"allowed_paths": [str(tmp_path)]},
        }
    )
    sandbox = Sandbox(config, root=tmp_path)
    return GitHub(config, sandbox, runner=runner)


def test_clone_builds_the_gh_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    github = build(tmp_path, runner)

    path = github.clone("7lokii/HeyNox", "projects/heynox")

    assert path == str(tmp_path / "projects" / "heynox")
    assert runner.called("gh repo clone 7lokii/HeyNox")


def test_clone_needs_owner_and_name(tmp_path: Path) -> None:
    github = build(tmp_path, FakeRunner())
    with pytest.raises(GitHubError, match="owner/nome"):
        github.clone("HeyNox", "projects/x")


def test_clone_outside_the_sandbox_is_refused(tmp_path: Path) -> None:
    github = build(tmp_path, FakeRunner())
    with pytest.raises(SandboxError):
        github.clone("7lokii/HeyNox", "../fora")


def test_push_to_main_is_refused_when_disabled(tmp_path: Path, repo: Path) -> None:
    runner = FakeRunner({"git rev-parse --abbrev-ref HEAD": CommandResult([], 0, "main\n", "")})
    github = build(tmp_path, runner, allow_push_to_main=False)

    with pytest.raises(GitHubError, match="desligado"):
        github.push("projects/demo")

    assert not runner.called("git push")


def test_push_to_main_is_allowed_when_configured(tmp_path: Path, repo: Path) -> None:
    runner = FakeRunner({"git rev-parse --abbrev-ref HEAD": CommandResult([], 0, "main\n", "")})
    github = build(tmp_path, runner, allow_push_to_main=True)

    assert "main" in github.push("projects/demo")
    assert runner.called("git push -u origin main")


def test_push_runs_tests_first_and_stops_on_failure(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FakeRunner({"git rev-parse --abbrev-ref HEAD": CommandResult([], 0, "feature\n", "")})
    github = build(tmp_path, runner, require_tests=True)
    monkeypatch.setattr(github, "run_tests", lambda path: (False, "1 failed"))

    with pytest.raises(GitHubError, match="testes falharam"):
        github.push("projects/demo")

    assert not runner.called("git push")


def test_push_skips_tests_when_there_is_nothing_to_run(tmp_path: Path, repo: Path) -> None:
    runner = FakeRunner({"git rev-parse --abbrev-ref HEAD": CommandResult([], 0, "feature\n", "")})
    github = build(tmp_path, runner, require_tests=True)

    github.push("projects/demo")

    assert runner.called("git push -u origin feature")


@pytest.mark.parametrize("name", ["main", "--force", "a..b", "com espaço", "x.lock"])
def test_invalid_branch_names_are_refused(tmp_path: Path, repo: Path, name: str) -> None:
    github = build(tmp_path, FakeRunner())
    with pytest.raises(GitHubError):
        github.create_branch("projects/demo", name)


def test_commit_stages_everything(tmp_path: Path, repo: Path) -> None:
    runner = FakeRunner()
    github = build(tmp_path, runner)

    github.commit("projects/demo", "feat: coisa")

    assert runner.called("git add -A")
    assert runner.called("git commit -m feat: coisa")


def test_commit_can_stage_selected_files(tmp_path: Path, repo: Path) -> None:
    runner = FakeRunner()
    github = build(tmp_path, runner)

    github.commit("projects/demo", "fix: x", ["a.py", "b.py"])

    assert runner.called("git add -- a.py b.py")


def test_commit_needs_a_message(tmp_path: Path, repo: Path) -> None:
    github = build(tmp_path, FakeRunner())
    with pytest.raises(GitHubError, match="mensagem"):
        github.commit("projects/demo", "  ")


def test_pr_refuses_when_head_is_the_base(tmp_path: Path, repo: Path) -> None:
    runner = FakeRunner({"git rev-parse --abbrev-ref HEAD": CommandResult([], 0, "main\n", "")})
    github = build(tmp_path, runner)

    with pytest.raises(GitHubError, match="origem é a de destino"):
        github.pr_create("projects/demo", "Título")


def test_pr_list_parses_json(tmp_path: Path, repo: Path) -> None:
    payload = '[{"number": 3, "title": "Corrige X", "state": "OPEN", "url": "u"}]'
    runner = FakeRunner({"gh pr list": CommandResult([], 0, payload, "")})
    github = build(tmp_path, runner)

    rows = github.pr_list("projects/demo")

    assert rows[0]["number"] == 3
    assert rows[0]["title"] == "Corrige X"


def test_gh_missing_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nox.integrations.github.shutil.which", lambda name: None)
    github = build(tmp_path, FakeRunner())

    with pytest.raises(GitHubError, match="não está instalado"):
        github.check_auth()


def test_status_outside_a_repo_is_refused(tmp_path: Path) -> None:
    github = build(tmp_path, FakeRunner())
    (tmp_path / "projetos").mkdir()

    with pytest.raises(GitHubError, match="não é um repositório"):
        github.status("projetos")
