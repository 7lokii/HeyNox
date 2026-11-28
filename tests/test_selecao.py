"""A selecao de ferramentas que corta os 429 do plano gratuito."""

from __future__ import annotations

from nox.tools.selecao import LIMITE, escolher

TODAS = [
    "notes",
    "web_search",
    "fetch_url",
    "browser",
    "read_file",
    "list_dir",
    "write_file",
    "edit_file",
    "run_command",
    "github_repo",
    "github_branch",
    "github_commit",
    "github_pr",
    "github_issue",
    "desktop",
    "routine",
    "skill",
    "spawn_agent",
]


def test_a_frase_de_conversa_leva_o_nucleo() -> None:
    escolhidas = escolher("bom dia, como estás?", TODAS)

    assert "notes" in escolhidas
    assert "web_search" in escolhidas
    assert len(escolhidas) < len(TODAS)


def test_pedido_de_comando_traz_o_terminal() -> None:
    assert "run_command" in escolher("corre o comando git status", TODAS)


def test_procura_traz_a_pesquisa() -> None:
    assert "web_search" in escolher("procura na internet o preço do ouro", TODAS)


def test_github_vem_em_bloco() -> None:
    escolhidas = escolher("abre um pull request para o repo", TODAS)

    assert "github_pr" in escolhidas
    assert "github_commit" in escolhidas


def test_nunca_passa_do_limite() -> None:
    escolhidas = escolher("corre o comando, le o ficheiro, procura na internet e clica no ecra", TODAS)

    assert len(escolhidas) <= LIMITE


def test_mcp_fica_sempre() -> None:
    escolhidas = escolher("bom dia", TODAS + ["mcp_homelab"])

    assert "mcp_homelab" in escolhidas


def test_acentos_nao_enganam() -> None:
    assert "desktop" in escolher("faz uma captura do ecrã", TODAS)


def test_ferramenta_inexistente_e_ignorada() -> None:
    escolhidas = escolher("corre o comando", ["run_command"])

    assert escolhidas == ["run_command", "notes"][: len(escolhidas)]
    assert "inventada" not in escolhidas
