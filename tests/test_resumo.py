"""Fase 4c: resumir conversa antiga em factos com data."""

from __future__ import annotations

from pathlib import Path

from nox.brain.agent import Agent
from nox.brain.llm import LlmError
from nox.memory.resumo import (
    LOTE,
    MANTER_RECENTES,
    MINIMO_PARA_RESUMIR,
    com_data,
    em_lote,
    limpar_resposta,
    resumir,
    turnos_a_resumir,
)
from nox.memory.store import MemoryStore


class FakeLlm:
    """Responde sempre a mesma lista de factos."""

    def __init__(self, resposta: str = "gosta de café\n- trabalha no NoxSec") -> None:
        self.resposta = resposta
        self.chamadas = 0

    def complete(self, messages, system: str = "") -> str:  # noqa: ARG002
        self.chamadas += 1
        return self.resposta


class FalhaLlm:
    def complete(self, messages, system: str = "") -> str:  # noqa: ARG002
        raise LlmError("sem rede")


def test_limpar_resposta_tira_bullets_e_numeros() -> None:
    factos = limpar_resposta("- gosta de café\n1. vive em Lisboa\nNADA\n\ncurto")

    assert factos == ["gosta de café", "vive em Lisboa"]


def test_facto_em_ingles_e_descartado() -> None:
    texto = "Diogo owns the computer.\nO Diogo tem 8 GB de RAM."

    assert limpar_resposta(texto) == ["O Diogo tem 8 GB de RAM."]


def test_limpar_resposta_respeita_o_maximo() -> None:
    factos = limpar_resposta("\n".join(f"facto numero {i} com palavras" for i in range(9)))

    assert len(factos) == 5


def test_turnos_a_resumir_deixa_os_recentes() -> None:
    turnos = [(i, "user", f"t{i}") for i in range(30)]

    antigos = turnos_a_resumir(turnos, manter=10)

    assert len(antigos) == 20
    assert antigos[-1][0] == 19


def test_sem_llm_nao_grava_nada(tmp_path: Path) -> None:
    memoria = MemoryStore(tmp_path / "nox.db")
    turnos = [(i, "user", "olá") for i in range(5)]

    assert resumir(turnos, FalhaLlm()) == []
    memoria.close()


def test_o_agente_guarda_factos_e_limpa_os_turnos(tmp_path: Path) -> None:
    memoria = MemoryStore(tmp_path / "nox.db")
    for i in range(MINIMO_PARA_RESUMIR + MANTER_RECENTES):
        memoria.add_turn("local", "user" if i % 2 == 0 else "assistant", f"volta {i}")
    agente = Agent(llm=FakeLlm(), memory=memoria)

    gravados = agente._resumir_conversa()

    assert gravados == 2
    factos = memoria.facts()
    assert len(factos) == 2
    assert all(f.kind == "resumo" for f in factos)
    assert all(": " in f.text for f in factos)  # data a frente
    assert memoria.count_turns() == MINIMO_PARA_RESUMIR + MANTER_RECENTES - LOTE
    memoria.close()


def test_resumo_falhado_nao_apaga_conversa(tmp_path: Path) -> None:
    memoria = MemoryStore(tmp_path / "nox.db")
    for i in range(MINIMO_PARA_RESUMIR + MANTER_RECENTES):
        memoria.add_turn("local", "user", f"volta {i}")
    agente = Agent(llm=FalhaLlm(), memory=memoria)

    gravados = agente._resumir_conversa()

    assert gravados == 0
    assert memoria.count_turns() == MINIMO_PARA_RESUMIR + MANTER_RECENTES
    memoria.close()


def test_em_lote_limita_turnos_e_caracteres() -> None:
    """288 turnos de uma vez nao cabem no contexto do modelo."""
    muitos = [(i, "user", "x" * 200) for i in range(300)]

    escolhidos = em_lote(muitos)

    assert len(escolhidos) <= LOTE
    assert sum(len(t[2]) for t in escolhidos) <= 6200


def test_com_data_usa_o_dia_de_hoje() -> None:
    facto = com_data("gosta de café")

    assert facto[4] == "-" and facto[7] == "-"
    assert facto.endswith("gosta de café")
