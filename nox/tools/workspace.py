"""Leitura da workspace do dono, a pedido, por SSH ao desktop.

O Nox corre no homelab; a workspace esta no desktop. Estas duas ferramentas leem
`E:\\Workspace` com uma lista branca de pastas e recusam tudo o que possa conter
segredos. So leitura: escrever na workspace nao esta aqui.
"""

from __future__ import annotations

import base64
import json
import subprocess
from typing import Any

from nox.tools.base import ToolResult

CHAVE = "/var/lib/heynox/ssh/desktop_ed25519"
DESTINO = "lokii@192.168.236.1"
PRAZO = 25

# So estes ramos. Qualquer outro caminho e recusado antes de sair daqui.
PERMITIDOS = (
    "e:/workspace/projects/",
    "e:/workspace/ai-resources/",
    "e:/workspace/workspace-vault/",
)
FICHEIROS_SOLTOS = ("e:/workspace/agents.md",)

# Mesmo dentro dos ramos permitidos: nada disto se le.
BLOQUEADOS = (
    "/dev/secrets/",
    "/secrets/",
    "bitwarden.env",
    "/.env",
    ".env.",
    "/.git/",
    "/node_modules/",
    "/venv/",
    "/.venv/",
)

# Nomes de chave privada. A publica (`*.pub`) pode ler-se; a privada nunca.
EXTENSOES_PROIBIDAS = (".pem", ".key", ".pfx", ".p12", ".kdbx", ".jks", ".ovpn")
NOMES_PROIBIDOS = ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "credentials")

# O plano gratuito do Groq da 8000 tokens por minuto. Uma leitura grande
# gasta o minuto inteiro num pedido, por isso o teto e baixo.
MAX_LINHAS = 150
MAX_CARACTERES = 12_000


def normalizar(caminho: str) -> str:
    return caminho.strip().replace("\\", "/").lower()


def permitido(caminho: str) -> bool:
    """True so para caminhos da lista branca e sem partes bloqueadas."""
    limpo = normalizar(caminho)
    if not limpo:
        return False
    if any(parte in limpo for parte in BLOQUEADOS):
        return False
    if limpo.endswith(EXTENSOES_PROIBIDAS):
        return False
    nome = limpo.rsplit("/", 1)[-1]
    if nome in NOMES_PROIBIDOS or (nome.endswith("_ed25519") and not nome.endswith(".pub")):
        return False
    if limpo.startswith("../") or "/../" in limpo:
        return False
    if limpo in FICHEIROS_SOLTOS:
        return True
    if limpo.startswith(PERMITIDOS):
        return True
    # A propria pasta de topo ("E:/Workspace/Projects") tambem e listavel.
    return limpo + "/" in PERMITIDOS


def _powershell(script: str, *, prazo: int = PRAZO) -> tuple[int, str]:
    codificado = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        saida = subprocess.run(
            [
                "ssh",
                "-i",
                CHAVE,
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                DESTINO,
                "powershell -NoProfile -EncodedCommand " + codificado,
            ],
            capture_output=True,
            timeout=prazo,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"sem ligacao ao desktop: {exc}"
    texto = saida.stdout.decode("utf-8", errors="replace")
    return saida.returncode, texto


def listar_remoto(caminho: str) -> list[dict[str, Any]]:
    """Nomes, tipos e tamanhos de uma pasta da workspace."""
    script = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        f"Get-ChildItem -LiteralPath '{caminho}' -Force | "
        "Select-Object Name,Length,@{n='Pasta';e={$_.PSIsContainer}} | "
        "ConvertTo-Json -Compress"
    )
    codigo, saida = _powershell(script)
    if codigo != 0 or not saida.strip():
        return []
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError:
        return []
    if isinstance(dados, dict):
        dados = [dados]
    return [d for d in dados if isinstance(d, dict)]


def ler_remoto(caminho: str, *, linhas: int = MAX_LINHAS) -> str:
    script = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        f"Get-Content -LiteralPath '{caminho}' -Encoding UTF8 -TotalCount {linhas}"
    )
    codigo, saida = _powershell(script)
    return saida if codigo == 0 else ""


class WorkspaceListTool:
    name = "workspace_list"
    description = (
        "Lista uma pasta da workspace do dono (E:\\Workspace\\Projects, "
        "AI-Resources ou Workspace-Vault). So leitura."
    )
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho da pasta a listar"},
        },
        "required": ["path"],
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        caminho = str(arguments.get("path", "")).strip()
        if not caminho:
            return ToolResult(False, "falta o caminho")
        if not permitido(caminho):
            return ToolResult(
                False,
                "fora da lista branca. Posso ler Projects, AI-Resources e "
                "Workspace-Vault; segredos nunca.",
            )
        itens = listar_remoto(caminho)
        if not itens:
            return ToolResult(False, f"nada em {caminho} (ou o desktop nao respondeu)")
        linhas = []
        for item in itens[:60]:
            nome = str(item.get("Name") or "")
            if str(item.get("Pasta")).lower() == "true":
                linhas.append(f"{nome}/")
            else:
                tamanho = int(item.get("Length") or 0)
                linhas.append(f"{nome}  {tamanho} B")
        return ToolResult(True, "\n".join(linhas))


class WorkspaceReadTool:
    name = "workspace_read"
    description = (
        "Le um ficheiro de texto da workspace do dono, ate 400 linhas. "
        "Nao le segredos, .env nem .git."
    )
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho do ficheiro"},
            "max_lines": {"type": "integer", "description": "Maximo de linhas"},
        },
        "required": ["path"],
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        caminho = str(arguments.get("path", "")).strip()
        if not caminho:
            return ToolResult(False, "falta o caminho")
        if not permitido(caminho):
            return ToolResult(
                False,
                "fora da lista branca. Posso ler Projects, AI-Resources e "
                "Workspace-Vault; segredos nunca.",
            )
        limite = max(1, min(int(arguments.get("max_lines") or MAX_LINHAS), MAX_LINHAS))
        texto = ler_remoto(caminho, linhas=limite)
        if not texto.strip():
            return ToolResult(False, f"nada para ler em {caminho}")
        if len(texto) > MAX_CARACTERES:
            texto = texto[:MAX_CARACTERES] + "\n… (cortado)"
        return ToolResult(True, texto)


def build_workspace_tools() -> list[Any]:
    return [WorkspaceListTool(), WorkspaceReadTool()]
