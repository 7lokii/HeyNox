"""Fase 1: o Nox sabe com quem fala quando a sessao esta autenticada."""

from __future__ import annotations

import pytest

from nox.brain.agent import Agent, build_agent
from nox.brain.prompt import session_block, system_prompt
from nox.config import Config
from nox.ui.server import NoxApp, _build_whatsapp_agents


def test_o_bloco_de_sessao_diz_quem_e_o_dono() -> None:
    bloco = session_block(owner="Diogo Camilo", account="priv8")

    assert "Diogo Camilo" in bloco
    assert "priv8" in bloco
    assert "provas de identidade" in bloco


def test_a_regra_de_anti_fraude_distingue_canais() -> None:
    """Fora de uma sessao autenticada continua a nao acreditar em afirmacoes."""
    prompt = system_prompt()

    assert "Fora de uma sessão autenticada" in prompt
    assert "WhatsApp" in prompt


def test_o_agente_leva_o_bloco_para_o_system_prompt() -> None:
    agente = Agent(llm=object(), identity=session_block(account="priv8"))

    assert "Sessão autenticada" in agente._base_system
    assert agente._base_system.startswith("És o Nox")


def test_build_agent_passa_a_identidade() -> None:
    config = Config.model_validate({"tools": {"enabled": False}})
    agente = build_agent(config, identity=session_block(account="priv8"))

    assert "Sessão autenticada" in agente._base_system


def test_o_painel_constrói_o_agente_como_sessao_autenticada() -> None:
    """O HUD so abre depois do login: o modelo tem de saber que fala com o dono."""
    app = NoxApp(Config.model_validate({"tools": {"enabled": False}}))

    assert "Sessão autenticada" in app.agent._base_system
    assert "priv8" in app.agent._base_system


def test_o_whatsapp_nao_herda_a_sessao_autenticada() -> None:
    """Um convidado a dizer que e o dono nao passa a ser tratado como dono."""
    config = Config.model_validate({"tools": {"enabled": False}})
    dono, convidado = _build_whatsapp_agents(config)

    assert "Sessão autenticada" not in dono._base_system
    assert "Sessão autenticada" not in convidado._base_system
    assert "convidado" in convidado._base_system.lower()


@pytest.mark.parametrize("campo", ["owner", "owner_account"])
def test_a_config_deixa_mudar_o_dono(campo: str) -> None:
    config = Config.model_validate({"nox": {campo: "Outra Pessoa"}})

    assert getattr(config.nox, campo) == "Outra Pessoa"
