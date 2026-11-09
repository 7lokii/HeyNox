"""Ferramenta para carregar uma skill pelo nome."""

from __future__ import annotations

from typing import Any

from nox.skills import Skill, find_skill
from nox.tools.base import ToolResult


class SkillTool:
    name = "skill"
    description = (
        "Carrega as instruções completas de uma skill pelo nome. Usa antes de "
        "executar uma tarefa que tenha uma skill associada."
    )
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Nome da skill"}},
        "required": ["name"],
    }

    def __init__(self, skills: list[Skill]) -> None:
        self._skills = skills

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name") or "").strip()
        if not name:
            return ToolResult(False, "falta o nome da skill")
        skill = find_skill(self._skills, name)
        if skill is None:
            available = ", ".join(item.name for item in self._skills) or "(nenhuma)"
            return ToolResult(False, f"não existe a skill {name}. Disponíveis: {available}")
        return ToolResult(True, f"# {skill.name}\n\n{skill.body}")


def build_skill_tools(skills: list[Skill]) -> list[Any]:
    return [SkillTool(skills)] if skills else []
