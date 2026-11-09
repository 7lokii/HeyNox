"""Skills: playbooks em Markdown que ensinam o Nox a fazer uma tarefa.

Uma skill é um ficheiro `.md` com frontmatter:

    ---
    name: resumo-diario
    description: Como resumir o dia em três pontos
    ---
    Instruções completas...

O índice (nome + descrição) entra no system prompt; o corpo só é carregado
quando o modelo pede a skill com a ferramenta `skill`. É o mesmo princípio das
skills de agente: contexto barato até ser preciso.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from nox.paths import install_dir, user_data_dir

MAX_BODY = 12_000


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path


def parse_skill(text: str, path: Path) -> Skill | None:
    """Lê frontmatter simples. Sem nome ou sem corpo, a skill é ignorada."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    name = str(meta.get("name") or "").strip()
    description = str(meta.get("description") or "").strip()
    body = parts[2].strip()
    if not name or not body:
        return None
    return Skill(name=name, description=description, body=body[:MAX_BODY], path=path)


def skill_dirs() -> list[Path]:
    """Primeiro as do projeto, depois as do utilizador (estas ganham)."""
    return [install_dir() / "skills", user_data_dir() / "skills"]


def load_skills(dirs: list[Path] | None = None) -> list[Skill]:
    found: dict[str, Skill] = {}
    for directory in dirs if dirs is not None else skill_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            try:
                skill = parse_skill(path.read_text(encoding="utf-8"), path)
            except OSError:
                continue
            if skill is not None:
                found[skill.name] = skill
    return [found[name] for name in sorted(found)]


def skill_index(skills: list[Skill]) -> str:
    if not skills:
        return ""
    lines = "\n".join(
        f"- {skill.name}: {skill.description or '(sem descrição)'}" for skill in skills
    )
    return (
        "\nSkills disponíveis (usa a ferramenta `skill` para carregar as instruções "
        "antes de executar):\n" + lines + "\n"
    )


def find_skill(skills: list[Skill], name: str) -> Skill | None:
    wanted = name.strip().lower()
    for skill in skills:
        if skill.name.lower() == wanted:
            return skill
    return None
