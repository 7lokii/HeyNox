"""Contexto dos projetos do dono, para o Nox saber onde vive o quê.

O Nox corre no homelab; a workspace esta no desktop. Este modulo le, por SSH, o
manifest dos projetos, os `AGENTS.md` e as notas do vault, e escreve um resumo
curto em `<dados>/contexto-workspace.md`. O agente injecta esse resumo no system
prompt.

Nada de segredos: so estes ficheiros, por caminho fixo, e sem tocar em
`Dev\\secrets`, `.env` ou `.git`.
"""

from __future__ import annotations

import base64
import io
import subprocess
from dataclasses import dataclass
from pathlib import Path

from nox.paths import user_data_dir

MANIFEST = "E:/Workspace/AI-Resources/projects.manifest.yaml"
CHAVE = "/var/lib/heynox/ssh/desktop_ed25519"
DESTINO = "lokii@192.168.236.1"
LIMITE = 3500

# O que pode ser lido. Qualquer caminho fora desta lista e recusado, mesmo que
# alguem chame `ler_remoto` directamente.
PREFIXOS_PERMITIDOS = ("E:/Workspace/AI-Resources/", "E:/Workspace/Workspace-Vault/")


@dataclass
class Projeto:
    nome: str
    caminho: str
    aliases: list[str]
    tecnologias: list[str]
    contexto: str
    nota: str


def caminho_do_contexto() -> Path:
    return user_data_dir() / "contexto-workspace.md"


def ler_remoto(caminho: str, *, prazo: int = 25) -> str:
    """Le um ficheiro do desktop. Vazio quando nao existe ou o SSH falha."""
    normalizado = caminho.replace("\\", "/")
    if not normalizado.startswith(PREFIXOS_PERMITIDOS):
        raise ValueError(f"caminho fora da lista: {caminho}")
    # `-EncodedCommand` evita as aspas partidas entre bash, ssh e PowerShell.
    # O console do PowerShell escreve em cp850; sem isto os acentos chegam
    # partidos ao prompt ("decis?o").
    script = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        f"Get-Content -Raw -LiteralPath '{normalizado}' -Encoding UTF8"
    )
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
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if saida.returncode != 0:
        return ""
    return saida.stdout.decode("utf-8", errors="replace")


def projetos_do_manifest(texto: str) -> list[Projeto]:
    """Extrai o essencial de cada projeto. Manifest invalido devolve lista vazia."""
    import yaml

    try:
        dados = yaml.safe_load(texto) or {}
    except yaml.YAMLError:
        return []
    projetos: list[Projeto] = []
    for entrada in dados.get("projetos") or []:
        if not isinstance(entrada, dict):
            continue
        projetos.append(
            Projeto(
                nome=str(entrada.get("display_name") or entrada.get("id") or "").strip(),
                caminho=str(entrada.get("path") or "").strip(),
                aliases=[str(a) for a in (entrada.get("aliases") or [])][:8],
                tecnologias=[str(t) for t in (entrada.get("tecnologias") or [])][:6],
                contexto=" ".join(str(entrada.get("contexto") or "").split())[:280],
                nota=str(entrada.get("nota_vault") or "").strip(),
            )
        )
    return [p for p in projetos if p.nome]


def estado_da_nota(nota: str) -> tuple[str, list[str]]:
    """Separa o paragrafo de estado e as linhas em aberto do proximo passo."""
    estado, proximos = "", []
    dentro_estado = False
    dentro_proximo = False
    for linha in nota.splitlines():
        limpa = linha.strip()
        if limpa.startswith("## "):
            titulo = limpa[3:].strip().lower()
            dentro_estado = titulo.startswith("estado")
            dentro_proximo = titulo.startswith("próximo") or titulo.startswith("proximo")
            continue
        if dentro_estado and not estado and limpa and not limpa.startswith("-"):
            estado = " ".join(limpa.split())[:240]
        if dentro_proximo and limpa.startswith("- [ ]"):
            texto = " ".join(limpa[5:].split())[:120]
            if texto:
                proximos.append(texto)
            if len(proximos) >= 2:
                break
    return estado, proximos


def render(projetos: list[Projeto], notas: dict[str, str]) -> str:
    """Resumo em markdown, cortado a LIMITE caracteres."""
    partes = [
        "Contexto dos projetos do dono, gerado a partir do manifest e do vault.",
        "Usa isto para saber onde vive o que ele refere. Se o estado aqui parecer",
        "antigo, diz que e um resumo e oferece verificar o ficheiro.",
        "",
    ]
    for projeto in projetos:
        linha = f"### {projeto.nome}"
        if projeto.caminho:
            linha += f" — `{projeto.caminho}`"
        partes.append(linha)
        if projeto.aliases:
            partes.append("Tambem chamado: " + ", ".join(projeto.aliases))
        if projeto.tecnologias:
            partes.append("Tecnologias: " + ", ".join(projeto.tecnologias))
        if projeto.contexto:
            partes.append("O que e: " + projeto.contexto)
        estado, proximos = estado_da_nota(notas.get(projeto.nota, ""))
        if estado:
            partes.append("Estado: " + estado)
        if proximos:
            partes.append("Em aberto: " + "; ".join(proximos))
        partes.append("")
    texto = "\n".join(partes).strip()
    return texto[:LIMITE]


def caminhos_da_nota(nota: str) -> list[str]:
    """A nota pode ser um ficheiro ou uma pasta com o mesmo nome dentro.

    O NoxSec vive em `02 Projetos/NoxSec/NoxSec.md`; os outros projetos usam
    `02 Projetos/<Nome>.md`. Tentar as duas formas evita perder metade do estado.
    """
    if not nota:
        return []
    base = "E:/Workspace/Workspace-Vault/" + nota.lstrip("/")
    candidatos = [base]
    if base.lower().endswith(".md"):
        sem_extensao = base[:-3]
        candidatos.append(sem_extensao + "/" + sem_extensao.rsplit("/", 1)[-1] + ".md")
    return candidatos


def ler_nota(nota: str) -> str:
    for caminho in caminhos_da_nota(nota):
        texto = ler_remoto(caminho)
        if texto.strip():
            return texto
    return ""


def gerar(*, escrever: bool = True) -> str:
    """Le o desktop, monta o resumo e grava-o no diretorio de dados."""
    manifest = ler_remoto(MANIFEST)
    projetos = projetos_do_manifest(manifest)
    notas = {p.nota: ler_nota(p.nota) for p in projetos if p.nota}
    texto = render(projetos, notas)
    if escrever and texto:
        destino = caminho_do_contexto()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + "\n", encoding="utf-8")
    return texto


def bloco_para_prompt(limite: int = LIMITE) -> str:
    """Texto pronto a juntar ao system prompt, ou vazio se nao houver resumo."""
    caminho = caminho_do_contexto()
    if not caminho.is_file():
        return ""
    try:
        texto = caminho.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not texto:
        return ""
    return "\n" + texto[:limite] + "\n"


def main() -> int:
    texto = gerar()
    print(f"{len(texto)} caracteres em {caminho_do_contexto()}")
    return 0 if texto else 1


if __name__ == "__main__":
    raise SystemExit(main())
