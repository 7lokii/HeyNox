"""Ferramentas de GitHub para o agente.

Cada ferramenta é uma ação com nome; o modelo escolhe. A lógica e as regras
estão em `nox/integrations/github.py` — aqui só se valida a forma dos argumentos
e se formata a resposta.
"""

from __future__ import annotations

from typing import Any

from nox.integrations.github import GitHub, GitHubError
from nox.tools.base import ToolResult

MAX_ITEMS = 10


def _items(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(nenhum)"
    lines = []
    for row in rows[:MAX_ITEMS]:
        author = row.get("author") or {}
        who = author.get("login", "") if isinstance(author, dict) else str(author)
        lines.append(
            f"#{row.get('number')} [{row.get('state', '?')}] {row.get('title', '')}"
            + (f" — {who}" if who else "")
            + (f"\n   {row.get('url')}" if row.get("url") else "")
        )
    return "\n".join(lines)


class RepoTool:
    name = "github_repo"
    description = (
        "Repositórios GitHub. 'clone' copia owner/nome para uma pasta do projeto; "
        "'pull' atualiza; 'status' mostra alterações e branch."
    )
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["clone", "pull", "status"]},
            "repo": {"type": "string", "description": "owner/nome (só no clone)"},
            "dest": {"type": "string", "description": "Pasta de destino (só no clone)"},
            "path": {"type": "string", "description": "Repositório local"},
        },
        "required": ["action"],
    }

    def __init__(self, github: GitHub) -> None:
        self._github = github

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        try:
            if action == "clone":
                repo = str(arguments.get("repo") or "").strip()
                dest = str(arguments.get("dest") or "").strip()
                path = self._github.clone(repo, dest)
                return ToolResult(True, f"clonado para {path}")
            if action == "pull":
                return ToolResult(True, self._github.pull(str(arguments.get("path") or ".")))
            if action == "status":
                return ToolResult(True, self._github.status(str(arguments.get("path") or ".")))
        except GitHubError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(False, f"ação desconhecida: {action or '(vazia)'}")


class BranchTool:
    name = "github_branch"
    description = "Branches: 'list', 'create' (a partir da atual) e 'checkout'."
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "create", "checkout"]},
            "path": {"type": "string", "description": "Repositório local"},
            "name": {"type": "string", "description": "Nome da branch"},
        },
        "required": ["action"],
    }

    def __init__(self, github: GitHub) -> None:
        self._github = github

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        path = str(arguments.get("path") or ".")
        name = str(arguments.get("name") or "").strip()
        try:
            if action == "list":
                return ToolResult(True, self._github.branches(path))
            if action == "create":
                return ToolResult(True, self._github.create_branch(path, name))
            if action == "checkout":
                return ToolResult(True, self._github.checkout(path, name))
        except GitHubError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(False, f"ação desconhecida: {action or '(vazia)'}")


class CommitTool:
    name = "github_commit"
    description = (
        "Commits e push. 'commit' prepara os ficheiros e grava; 'push' envia a "
        "branch (corre os testes antes, se github.require_tests). Nunca faz "
        "force-push."
    )
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["commit", "push"]},
            "path": {"type": "string", "description": "Repositório local"},
            "message": {"type": "string", "description": "Mensagem do commit"},
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ficheiros a preparar (omissão: todos)",
            },
            "branch": {"type": "string", "description": "Branch a enviar (omissão: a atual)"},
        },
        "required": ["action"],
    }

    def __init__(self, github: GitHub) -> None:
        self._github = github

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        path = str(arguments.get("path") or ".")
        try:
            if action == "commit":
                files = arguments.get("files")
                paths = [str(item) for item in files] if isinstance(files, list) else None
                return ToolResult(
                    True,
                    self._github.commit(path, str(arguments.get("message") or ""), paths),
                )
            if action == "push":
                branch = str(arguments.get("branch") or "").strip() or None
                return ToolResult(True, self._github.push(path, branch))
        except GitHubError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(False, f"ação desconhecida: {action or '(vazia)'}")


class PullRequestTool:
    name = "github_pr"
    description = (
        "Pull requests: 'create', 'list', 'view' e 'comment'. O PR é a revisão "
        "humana; não faças merge sem o utilizador pedir."
    )
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "list", "view", "comment"]},
            "path": {"type": "string", "description": "Repositório local"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "base": {"type": "string", "description": "Branch de destino"},
            "head": {"type": "string", "description": "Branch de origem"},
            "number": {"type": "integer", "description": "Número do PR"},
            "limit": {"type": "integer", "description": "Máximo de resultados"},
        },
        "required": ["action"],
    }

    def __init__(self, github: GitHub) -> None:
        self._github = github

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        path = str(arguments.get("path") or ".")
        number = int(arguments.get("number") or 0)
        try:
            if action == "create":
                url = self._github.pr_create(
                    path,
                    str(arguments.get("title") or ""),
                    str(arguments.get("body") or ""),
                    base=str(arguments.get("base") or "").strip() or None,
                    head=str(arguments.get("head") or "").strip() or None,
                )
                return ToolResult(True, url)
            if action == "list":
                return ToolResult(True, _items(self._github.pr_list(path, _limit(arguments))))
            if action == "view":
                if number <= 0:
                    return ToolResult(False, "falta o número do PR")
                data = self._github.pr_view(path, number)
                return ToolResult(True, _view(data))
            if action == "comment":
                if number <= 0:
                    return ToolResult(False, "falta o número do PR")
                return ToolResult(
                    True, self._github.pr_comment(path, number, str(arguments.get("body") or ""))
                )
        except GitHubError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(False, f"ação desconhecida: {action or '(vazia)'}")


class IssueTool:
    name = "github_issue"
    description = "Issues: 'list', 'create' e 'comment'."
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "create", "comment"]},
            "path": {"type": "string", "description": "Repositório local"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "number": {"type": "integer", "description": "Número da issue"},
            "limit": {"type": "integer", "description": "Máximo de resultados"},
        },
        "required": ["action"],
    }

    def __init__(self, github: GitHub) -> None:
        self._github = github

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        path = str(arguments.get("path") or ".")
        number = int(arguments.get("number") or 0)
        try:
            if action == "list":
                return ToolResult(True, _items(self._github.issue_list(path, _limit(arguments))))
            if action == "create":
                return ToolResult(
                    True,
                    self._github.issue_create(
                        path,
                        str(arguments.get("title") or ""),
                        str(arguments.get("body") or ""),
                    ),
                )
            if action == "comment":
                if number <= 0:
                    return ToolResult(False, "falta o número da issue")
                return ToolResult(
                    True,
                    self._github.issue_comment(path, number, str(arguments.get("body") or "")),
                )
        except GitHubError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(False, f"ação desconhecida: {action or '(vazia)'}")


def _limit(arguments: dict[str, Any]) -> int:
    try:
        return int(arguments.get("limit") or 10)
    except (TypeError, ValueError):
        return 10


def _view(data: dict[str, Any]) -> str:
    if not data:
        return "(sem dados)"
    author = data.get("author") or {}
    who = author.get("login", "") if isinstance(author, dict) else str(author)
    body = str(data.get("body") or "").strip()
    header = f"#{data.get('number')} [{data.get('state', '?')}] {data.get('title', '')}"
    if who:
        header += f" — {who}"
    parts = [header]
    if data.get("url"):
        parts.append(str(data["url"]))
    if body:
        parts.append(body[:2000])
    return "\n".join(parts)


def build_github_tools(github: GitHub) -> list[Any]:
    return [
        RepoTool(github),
        BranchTool(github),
        CommitTool(github),
        PullRequestTool(github),
        IssueTool(github),
    ]
