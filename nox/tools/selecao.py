"""Escolher as ferramentas que vao em cada pedido.

Com as 17 ferramentas sempre no pedido, cada turno custava ~3 600 tokens e o
plano gratuito da Groq tem 8 000 por minuto: dois turnos e o terceiro levava
`429 Too Many Requests`. A frase diz quase sempre o que vai precisar; mandar so
isso corta o custo sem tirar capacidade, porque o nucleo cobre o que e comum.

Nao e um classificador: e uma tabela de palavras. Se falhar, o nucleo responde
por quase tudo, e o modelo pode pedir o resto por `tool_search` quando existir.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

# Palavras que pedem cada ferramenta. Comparadas sem acentos e em minusculas.
REGRAS: dict[str, tuple[str, ...]] = {
    "web_search": ("procura", "pesquisa", "noticia", "internet", "googla", "atual", "preco"),
    "fetch_url": ("link", "site", "pagina", "url", "http", "abre o endereco"),
    "browser": ("navega", "javascript", "preenche o formulario", "clica no site"),
    "read_file": ("ler", "le o", "ficheiro", "conteudo do", "abre o ficheiro"),
    "list_dir": ("lista", "pasta", "diretorio", "que ficheiros", "o que esta em"),
    "write_file": ("cria o ficheiro", "escreve o ficheiro", "guarda em"),
    "edit_file": ("edita", "altera", "substitui", "corrige o ficheiro", "muda o"),
    "run_command": ("corre", "comando", "terminal", "instala", "shell", "bash", "pip"),
    "github_repo": ("repo", "repositorio", "clona"),
    "github_branch": ("branch", "ramo"),
    "github_commit": ("commit",),
    "github_pr": ("pull request", " merge", "pr "),
    "github_issue": ("issue",),
    "desktop": ("ecra", "janela", "clica", "rato", "teclado", "ocr", "captura"),
    "notes": ("nota", "aponta", "apontamento", "lembra-te", "lembra me"),
    "workspace_list": ("workspace", "projetos", "pasta do projeto", "que ficheiros tem o"),
    "workspace_read": ("le o ficheiro do projeto", "workspace", "agents.md", "nota do projeto",
                       "vault", "estado do projeto"),
    "routine": ("todos os dias", "todas as", "a cada", "rotina", "agenda", "lembra-me todos"),
    "skill": ("skill", "competencia"),
    "spawn_agent": ("delega", "subagente", "em paralelo"),
}

# O que vai sempre. `notes` e barato e cobre "lembra-te"; `web_search` e o que
# mais se pede sem palavra obvia.
NUCLEO: tuple[str, ...] = ("notes", "web_search")

# Quando nada casa, o que costuma resolver trabalho de ficheiros e comandos.
FALLBACK: tuple[str, ...] = ("read_file", "list_dir", "run_command", "notes")

LIMITE = 8


def normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def escolher(texto: str, nomes: Iterable[str], *, limite: int = LIMITE) -> list[str]:
    """Nomes de ferramentas a enviar neste pedido, por ordem de relevancia."""
    disponiveis = list(nomes)
    pedido = " " + normalizar(texto) + " "

    escolhidas: list[str] = []
    for nome in disponiveis:
        if nome.startswith("mcp_"):
            # Servidores MCP do dono: poucos e todos uteis, ficam sempre.
            escolhidas.append(nome)
    for nome in NUCLEO:
        if nome in disponiveis and nome not in escolhidas:
            escolhidas.append(nome)

    casadas = []
    for nome, palavras in REGRAS.items():
        if nome not in disponiveis:
            continue
        if any(normalizar(p) in pedido for p in palavras):
            casadas.append(nome)
    if not casadas:
        casadas = [n for n in FALLBACK if n in disponiveis]

    for nome in casadas:
        if nome not in escolhidas:
            escolhidas.append(nome)

    # O GitHub anda em blocos: pedir um pede os vizinhos.
    if any(n.startswith("github_") for n in escolhidas):
        for nome in disponiveis:
            if nome.startswith("github_") and nome not in escolhidas:
                escolhidas.append(nome)

    return escolhidas[:limite]
