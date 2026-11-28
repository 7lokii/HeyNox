"""Resumir conversa antiga em factos duraveis.

A conversa so guarda as ultimas `memory.history_turns` voltas; o resto era
apagado sem deixar nada. Isto le os turnos que ja sairam da janela, pede ao
modelo os factos que valem a pena guardar (preferencias, decisoes, nomes,
planos) e grava-os na memoria com a data. Os turnos resumidos saem da tabela.

Se o modelo falhar, nao se inventa nada: os turnos ficam onde estao e tenta-se
noutra altura.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from nox.brain.llm import LlmClient, LlmError
from nox.brain.messages import Message

# Quantos turnos ficam sem resumo (a janela visivel da conversa).
MANTER_RECENTES = 20
# So vale a pena resumir quando ha bastante conversa acumulada.
MINIMO_PARA_RESUMIR = 40
# Um resumo por lote: 288 turnos de uma vez nao cabem no contexto.
LOTE = 30
MAX_CARACTERES = 2500
MAX_FACTOS = 5

PROMPT = """\
Vais ler um trecho de conversa entre o Diogo e o Nox. Extrai so o que continua
verdade amanha: preferencias, decisoes, nomes, planos, problemas em aberto e
factos sobre a vida ou o trabalho dele.

Regras:
- Uma linha por facto, sem bullets, sem numeracao, sem introducao.
- Maximo {maximo} linhas. Cada linha ate 20 palavras.
- Nada de perguntas, nada de respostas do Nox, nada que seja so conversa.
- Se nao houver nada duravel, responde apenas: NADA.

Exemplo de saida (so o formato):
O Diogo trabalha no NoxSec.
O Diogo quer acabar a app Android.

Conversa:
{conversa}
"""


def turnos_a_resumir(
    turnos: Sequence[tuple[int, str, str]], *, manter: int = MANTER_RECENTES
) -> list[tuple[int, str, str]]:
    """Os turnos mais antigos, deixando os `manter` ultimos de fora."""
    if len(turnos) <= manter:
        return []
    return list(turnos[: len(turnos) - manter])


def em_lote(turnos: Sequence[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
    """Limita cada resumo a `LOTE` turnos e a `MAX_CARACTERES` de texto."""
    escolhidos: list[tuple[int, str, str]] = []
    total = 0
    for turno in turnos[:LOTE]:
        total += len(turno[2])
        if escolhidos and total > MAX_CARACTERES:
            break
        escolhidos.append(turno)
    return escolhidos


def como_texto(turnos: Sequence[tuple[int, str, str]]) -> str:
    linhas = []
    for _, role, texto in turnos:
        quem = "Diogo" if role == "user" else "Nox"
        linhas.append(f"{quem}: {' '.join(texto.split())[:400]}")
    return "\n".join(linhas)


_INGLES = ("the ", " he ", "she ", "his ", "her ", " owns ", " wants ", " has ", " is ")


def parece_ingles(facto: str) -> bool:
    """O gpt-oss-20b escorrega para ingles; um facto em ingles nao entra."""
    alvo = f" {facto.lower()} "
    return any(palavra in alvo for palavra in _INGLES)


def limpar_resposta(texto: str) -> list[str]:
    """Uma lista de factos a partir do que o modelo devolveu."""
    factos = []
    for linha in texto.splitlines():
        limpa = linha.strip().lstrip("-*•0123456789. ").strip()
        if not limpa or len(limpa) < 8:
            continue
        if limpa.upper().startswith("NADA"):
            continue
        if parece_ingles(limpa):
            continue
        factos.append(" ".join(limpa.split())[:200])
        if len(factos) >= MAX_FACTOS:
            break
    return factos


def heuristico(turnos: Sequence[tuple[int, str, str]]) -> list[str]:
    """O que se consegue sem modelo: frases do dono que ensinam factos."""
    from nox.memory.extract import extract_facts

    factos: list[str] = []
    for _, role, texto in turnos:
        if role != "user":
            continue
        for _, facto in extract_facts(texto):
            limpo = " ".join(facto.split())[:200]
            if limpo and limpo not in factos:
                factos.append(limpo)
            if len(factos) >= MAX_FACTOS:
                return factos
    return factos


def resumir(turnos: Sequence[tuple[int, str, str]], llm: LlmClient) -> list[str]:
    """Pede ao modelo os factos duraveis deste trecho.

    O `gpt-oss-20b` devolve resposta vazia com prompts grandes; nesse caso
    tenta-se uma vez com menos conversa e, se continuar vazio, fica o que a
    heuristica consegue ler das frases do dono.
    """
    if not turnos:
        return []
    for pedaco in (turnos, turnos[-15:]):
        prompt = PROMPT.format(maximo=MAX_FACTOS, conversa=como_texto(pedaco))
        try:
            resposta = llm.complete([Message(role="user", content=prompt)], system="")
        except (LlmError, OSError):
            continue
        factos = limpar_resposta(resposta)
        if factos:
            return factos
    return heuristico(turnos)


def com_data(facto: str, quando: float | None = None) -> str:
    """Facto com a data a frente, para a memoria nao ficar sem tempo."""
    dia = time.strftime("%Y-%m-%d", time.localtime(quando or time.time()))
    return f"{dia}: {facto}"
