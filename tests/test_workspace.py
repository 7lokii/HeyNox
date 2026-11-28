"""Fase 3.2: ler a workspace do dono por SSH, com lista branca."""

from __future__ import annotations

from typing import Any

import pytest

from nox.tools import workspace


@pytest.mark.parametrize(
    "caminho",
    [
        "E:\\Workspace\\Projects\\NoxSec\\AGENTS.md",
        "e:/workspace/ai-resources/projects.manifest.yaml",
        "E:/Workspace/Workspace-Vault/02 Projetos/NoxSec/NoxSec.md",
        "E:/Workspace/AGENTS.md",
    ],
)
def test_caminhos_da_lista_branca_passam(caminho: str) -> None:
    assert workspace.permitido(caminho)


@pytest.mark.parametrize(
    "caminho",
    [
        "E:\\Workspace\\Dev\\secrets\\bitwarden.env",
        "E:/Workspace/Dev/secrets/search-providers.env",
        "E:/Workspace/Projects/NoxSec/.env",
        "E:/Workspace/Projects/NoxSec/.git/config",
        "C:/Windows/System32/config/SAM",
        "E:/Workspace/Projects/../../Dev/secrets/x.env",
        "E:/Workspace/Projects/NoxSec/node_modules/pkg/index.js",
        "E:/Workspace/Projects/NoxSec/ssh/desktop_ed25519",
        "E:/Workspace/Projects/NoxSec/certs/server.pem",
        "E:/Workspace/Projects/NoxSec/bitwarden.kdbx",
    ],
)
def test_segredos_e_caminhos_de_fora_sao_recusados(caminho: str) -> None:
    assert not workspace.permitido(caminho)


def test_a_ferramenta_recusa_antes_de_sair_da_maquina() -> None:
    chamado: list[str] = []

    def falso(caminho: str) -> str:
        chamado.append(caminho)
        return "conteudo"

    original = workspace.ler_remoto
    workspace.ler_remoto = falso
    try:
        resultado = workspace.WorkspaceReadTool().run(
            {"path": "E:/Workspace/Dev/secrets/bitwarden.env"}
        )
    finally:
        workspace.ler_remoto = original

    assert resultado.ok is False
    assert "segredos" in resultado.content
    assert chamado == []


def test_leitura_devolve_texto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace, "ler_remoto", lambda caminho, linhas=400: "linha 1\nlinha 2")

    resultado = workspace.WorkspaceReadTool().run(
        {"path": "E:/Workspace/Projects/NoxSec/AGENTS.md", "max_lines": 5}
    )

    assert resultado.ok is True
    assert "linha 1" in resultado.content


def test_listagem_marca_pastas(monkeypatch: pytest.MonkeyPatch) -> None:
    itens: list[dict[str, Any]] = [
        {"Name": "NoxSec", "Pasta": True, "Length": None},
        {"Name": "README.md", "Pasta": False, "Length": 120},
    ]
    monkeypatch.setattr(workspace, "listar_remoto", lambda caminho: itens)

    resultado = workspace.WorkspaceListTool().run({"path": "E:/Workspace/Projects"})

    assert resultado.ok is True
    assert "NoxSec/" in resultado.content
    assert "README.md  120 B" in resultado.content


def test_ficheiro_vazio_e_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace, "ler_remoto", lambda caminho, linhas=400: "")

    resultado = workspace.WorkspaceReadTool().run({"path": "E:/Workspace/AGENTS.md"})

    assert resultado.ok is False
