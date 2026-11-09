"""GitHub através do `gh` e do `git`.

Porquê o `gh` e não a API REST: a autenticação já está resolvida (keyring), não
há tokens a passar por argumentos nem a guardar em ficheiros, e o `gh` cobre
clone, PRs, issues e comentários sem reimplementar paginação e erros.

Regras que não dependem do modelo:

- o repositório tem de estar dentro da sandbox;
- nunca há `--force` (force-push não existe como opção);
- push para a branch por omissão só se `github.allow_push_to_main`;
- com `github.require_tests`, os testes correm antes do push e falham o push.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nox.config import Config, NoxError
from nox.safety.sandbox import Sandbox

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")


class GitHubError(NoxError):
    """Operação GitHub recusada ou falhada."""


@dataclass
class CommandResult:
    args: list[str]
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def text(self) -> str:
        return (self.out or self.err).strip()


Runner = Callable[[Sequence[str], Path], CommandResult]


def _default_runner(args: Sequence[str], cwd: Path) -> CommandResult:
    try:
        completed = subprocess.run(  # noqa: S603 — lista fixa, sem shell
            list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitHubError(f"'{args[0]}' não está instalado ou não está no PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitHubError(f"'{args[0]}' demorou demasiado e foi parado") from exc
    return CommandResult(list(args), completed.returncode, completed.stdout, completed.stderr)


def _clean(text: str, limit: int = 3000) -> str:
    text = text.strip()
    return text[:limit] + "\n… (truncado)" if len(text) > limit else text


class GitHub:
    def __init__(
        self,
        config: Config,
        sandbox: Sandbox,
        *,
        runner: Runner | None = None,
    ) -> None:
        self.config = config.github
        self._sandbox = sandbox
        self._runner = runner or _default_runner
        self._auth: bool | None = None

    # --- infraestrutura --------------------------------------------------

    def _run(self, args: Sequence[str], cwd: Path) -> CommandResult:
        return self._runner(args, cwd)

    def _check_tools(self) -> None:
        for tool in ("gh", "git"):
            if shutil.which(tool) is None:
                raise GitHubError(f"'{tool}' não está instalado ou não está no PATH")

    def check_auth(self) -> None:
        if self._auth:
            return
        self._check_tools()
        result = self._run(["gh", "auth", "status"], self._sandbox.root)
        if not result.ok:
            raise GitHubError("o gh não está autenticado; corre 'gh auth login'")
        self._auth = True

    def _repo(self, path: str) -> Path:
        target = self._sandbox.resolve(path)
        if not (target / ".git").exists():
            raise GitHubError(f"{path} não é um repositório git")
        return target

    def _current_branch(self, repo: Path) -> str:
        result = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
        if not result.ok:
            raise GitHubError(f"não consegui ler a branch atual: {result.text}")
        return result.out.strip()

    @staticmethod
    def _branch(name: str) -> str:
        name = name.strip()
        if (
            not BRANCH_PATTERN.match(name)
            or ".." in name
            or name.endswith("/")
            or name.endswith(".lock")
        ):
            raise GitHubError(f"nome de branch inválido: {name}")
        return name

    # --- repositório -----------------------------------------------------

    def clone(self, repo: str, dest: str) -> str:
        repo = repo.strip()
        if not REPO_PATTERN.match(repo):
            raise GitHubError("o repositório tem de ser owner/nome")
        self.check_auth()
        target = self._sandbox.resolve(dest or repo.split("/")[1])
        if (target / ".git").exists():
            raise GitHubError(f"{dest} já é um repositório git")
        if target.exists() and any(target.iterdir()):
            raise GitHubError(f"{dest} já existe e não está vazio")
        result = self._run(["gh", "repo", "clone", repo, str(target)], self._sandbox.root)
        if not result.ok:
            raise GitHubError(f"o clone falhou: {_clean(result.text, 600)}")
        return str(target)

    def pull(self, path: str) -> str:
        repo = self._repo(path)
        result = self._run(["git", "pull", "--ff-only"], repo)
        if not result.ok:
            raise GitHubError(f"o pull falhou: {_clean(result.text, 600)}")
        return _clean(result.text) or "já estava atualizado"

    def status(self, path: str) -> str:
        repo = self._repo(path)
        result = self._run(["git", "status", "--short", "--branch"], repo)
        if not result.ok:
            raise GitHubError(f"não consegui ler o estado: {result.text}")
        return _clean(result.text) or "(sem alterações)"

    # --- branches --------------------------------------------------------

    def branches(self, path: str) -> str:
        repo = self._repo(path)
        result = self._run(
            ["git", "branch", "--format=%(refname:short)\t%(upstream:short)\t%(HEAD)"], repo
        )
        if not result.ok:
            raise GitHubError(f"não consegui listar as branches: {result.text}")
        return _clean(result.text) or "(sem branches)"

    def create_branch(self, path: str, name: str) -> str:
        repo = self._repo(path)
        branch = self._branch(name)
        if branch == self.config.default_branch:
            raise GitHubError("não crio uma branch com o nome da branch principal")
        exists = self._run(["git", "rev-parse", "--verify", "--quiet", branch], repo)
        if exists.ok:
            raise GitHubError(f"a branch {branch} já existe")
        result = self._run(["git", "checkout", "-b", branch], repo)
        if not result.ok:
            raise GitHubError(f"não consegui criar a branch: {_clean(result.text, 600)}")
        return f"branch {branch} criada e ativa"

    def checkout(self, path: str, name: str) -> str:
        repo = self._repo(path)
        branch = self._branch(name)
        result = self._run(["git", "checkout", branch], repo)
        if not result.ok:
            raise GitHubError(f"não consegui mudar de branch: {_clean(result.text, 600)}")
        return f"agora em {branch}"

    # --- commits e push --------------------------------------------------

    def commit(self, path: str, message: str, paths: Sequence[str] | None = None) -> str:
        repo = self._repo(path)
        message = message.strip()
        if not message:
            raise GitHubError("falta a mensagem do commit")
        if len(message) > 500:
            raise GitHubError("a mensagem do commit é grande demais")
        if paths:
            added = self._run(["git", "add", "--", *paths], repo)
        else:
            added = self._run(["git", "add", "-A"], repo)
        if not added.ok:
            raise GitHubError(f"não consegui preparar os ficheiros: {_clean(added.text, 600)}")
        result = self._run(["git", "commit", "-m", message], repo)
        if not result.ok:
            if "nothing to commit" in (result.out + result.err).lower():
                return "nada para commit; a árvore já estava limpa"
            raise GitHubError(f"o commit falhou: {_clean(result.text, 800)}")
        return _clean(result.text)

    def run_tests(self, repo: Path) -> tuple[bool, str]:
        """Corre pytest se o repositório parecer um projeto Python."""
        looks_python = any(
            (repo / name).exists() for name in ("pyproject.toml", "pytest.ini", "tests")
        )
        if not looks_python:
            return True, "sem testes para correr"
        result = self._run([sys.executable, "-m", "pytest", "-q"], repo)
        output = _clean(result.out + result.err, 1200)
        return result.ok, output or ("testes ok" if result.ok else "testes falharam")

    def push(self, path: str, branch: str | None = None) -> str:
        repo = self._repo(path)
        name = self._branch(branch or self._current_branch(repo))
        if name == self.config.default_branch and not self.config.allow_push_to_main:
            raise GitHubError(
                "push para a branch principal está desligado (github.allow_push_to_main)"
            )
        if self.config.require_tests:
            passed, summary = self.run_tests(repo)
            if not passed:
                raise GitHubError(f"os testes falharam; não fiz push:\n{summary}")
        result = self._run(["git", "push", "-u", "origin", name], repo)
        if not result.ok:
            raise GitHubError(f"o push falhou: {_clean(result.text, 800)}")
        return _clean(result.text) or f"{name} enviada para origin"

    # --- pull requests ---------------------------------------------------

    def pr_create(
        self,
        path: str,
        title: str,
        body: str = "",
        *,
        base: str | None = None,
        head: str | None = None,
    ) -> str:
        repo = self._repo(path)
        self.check_auth()
        title = title.strip()
        if not title:
            raise GitHubError("falta o título do PR")
        target = self._branch(base or self.config.default_branch)
        source = self._branch(head or self._current_branch(repo))
        if source == target:
            raise GitHubError("a branch de origem é a de destino; cria uma branch antes do PR")
        result = self._run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                target,
                "--head",
                source,
                "--title",
                title,
                "--body",
                body.strip() or title,
            ],
            repo,
        )
        if not result.ok:
            raise GitHubError(f"não consegui abrir o PR: {_clean(result.text, 800)}")
        return _clean(result.text) or "PR criado"

    def pr_list(self, path: str, limit: int = 10) -> list[dict[str, Any]]:
        repo = self._repo(path)
        self.check_auth()
        result = self._run(
            [
                "gh",
                "pr",
                "list",
                "--json",
                "number,title,state,author,url",
                "--limit",
                str(max(1, min(30, limit))),
            ],
            repo,
        )
        if not result.ok:
            raise GitHubError(f"não consegui listar os PRs: {_clean(result.text, 600)}")
        return _json_list(result.out)

    def pr_view(self, path: str, number: int) -> dict[str, Any]:
        repo = self._repo(path)
        self.check_auth()
        result = self._run(
            ["gh", "pr", "view", str(number), "--json", "number,title,state,body,url,author"],
            repo,
        )
        if not result.ok:
            raise GitHubError(f"não consegui ler o PR: {_clean(result.text, 600)}")
        return _json_object(result.out)

    def pr_comment(self, path: str, number: int, body: str) -> str:
        repo = self._repo(path)
        self.check_auth()
        body = body.strip()
        if not body:
            raise GitHubError("falta o comentário")
        result = self._run(["gh", "pr", "comment", str(number), "--body", body], repo)
        if not result.ok:
            raise GitHubError(f"não consegui comentar: {_clean(result.text, 600)}")
        return _clean(result.text) or "comentário publicado"

    # --- issues ----------------------------------------------------------

    def issue_list(self, path: str, limit: int = 10) -> list[dict[str, Any]]:
        repo = self._repo(path)
        self.check_auth()
        result = self._run(
            [
                "gh",
                "issue",
                "list",
                "--json",
                "number,title,state,author,url",
                "--limit",
                str(max(1, min(30, limit))),
            ],
            repo,
        )
        if not result.ok:
            raise GitHubError(f"não consegui listar as issues: {_clean(result.text, 600)}")
        return _json_list(result.out)

    def issue_create(self, path: str, title: str, body: str = "") -> str:
        repo = self._repo(path)
        self.check_auth()
        title = title.strip()
        if not title:
            raise GitHubError("falta o título da issue")
        result = self._run(
            ["gh", "issue", "create", "--title", title, "--body", body.strip() or title],
            repo,
        )
        if not result.ok:
            raise GitHubError(f"não consegui criar a issue: {_clean(result.text, 600)}")
        return _clean(result.text) or "issue criada"

    def issue_comment(self, path: str, number: int, body: str) -> str:
        repo = self._repo(path)
        self.check_auth()
        body = body.strip()
        if not body:
            raise GitHubError("falta o comentário")
        result = self._run(["gh", "issue", "comment", str(number), "--body", body], repo)
        if not result.ok:
            raise GitHubError(f"não consegui comentar a issue: {_clean(result.text, 600)}")
        return _clean(result.text) or "comentário publicado"


def _json_list(raw: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise GitHubError("o gh devolveu JSON inválido") from exc
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _json_object(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise GitHubError("o gh devolveu JSON inválido") from exc
    return data if isinstance(data, dict) else {}
