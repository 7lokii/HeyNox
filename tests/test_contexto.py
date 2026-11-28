"""Fase 3.1: o resumo da workspace que o Nox leva no system prompt."""

from __future__ import annotations

import pytest

from nox import contexto

MANIFEST = """
projetos:
  - id: noxsec
    display_name: NoxSec
    path: E:\\Workspace\\Projects\\NoxSec
    aliases: [noxsec, homelab]
    tecnologias: [python, fastapi]
    nota_vault: "02 Projetos/NoxSec.md"
    contexto: >-
      Servidor caseiro com Proxmox, API, painel e app Android.
  - id: ashenstudio
    display_name: AshenStudio
    path: E:\\Workspace\\Projects\\AshenStudio
    aliases: [ashen, minecraft]
    nota_vault: "02 Projetos/AshenStudio.md"
    contexto: Estudio de jogos e servidores de Minecraft.
"""

NOTA = """
# NoxSec

## Estado

Tem cloud pessoal no homelab, com painel e app.

## Próximo passo

- [ ] **Fase 4: modelo** maior e menos ferramentas por turno
- [ ] **WhatsApp** desligado, falta ler o QR
- [ ] terceira linha que nao deve aparecer
"""


def test_le_o_essencial_do_manifest() -> None:
    projetos = contexto.projetos_do_manifest(MANIFEST)

    assert [p.nome for p in projetos] == ["NoxSec", "AshenStudio"]
    assert projetos[0].aliases == ["noxsec", "homelab"]
    assert "Proxmox" in projetos[0].contexto


def test_manifest_invalido_nao_rebenta() -> None:
    assert contexto.projetos_do_manifest("::: nao e yaml :::") == []


def test_estado_e_os_dois_primeiros_passos() -> None:
    estado, proximos = contexto.estado_da_nota(NOTA)

    assert estado.startswith("Tem cloud pessoal")
    assert len(proximos) == 2
    assert "Fase 4" in proximos[0]


def test_o_resumo_junta_tudo_e_respeita_o_limite() -> None:
    projetos = contexto.projetos_do_manifest(MANIFEST)
    texto = contexto.render(projetos, {"02 Projetos/NoxSec.md": NOTA})

    assert "NoxSec" in texto
    assert "Tambem chamado: noxsec, homelab" in texto
    assert "Estado: Tem cloud pessoal" in texto
    assert "Em aberto:" in texto
    assert "Fase 4" in texto
    assert len(texto) <= contexto.LIMITE


def test_o_resumo_cabe_no_prompt() -> None:
    """Um resumo grande nao pode engolir o system prompt."""
    projetos = contexto.projetos_do_manifest(MANIFEST)
    texto = contexto.render(projetos, {})
    assert len(texto) < 4000


def test_caminho_fora_da_lista_e_recusado() -> None:
    with pytest.raises(ValueError):
        contexto.ler_remoto("E:/Workspace/Dev/secrets/bitwarden.env")
    with pytest.raises(ValueError):
        contexto.ler_remoto("C:/Windows/System32/config/SAM")
