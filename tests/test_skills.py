from pathlib import Path

from nox.skills import find_skill, load_skills, parse_skill, skill_index
from nox.tools.skills import SkillTool


def test_parse_a_skill() -> None:
    text = "---\nname: resumo\ndescription: Como resumir\n---\nFaz três pontos.\n"
    skill = parse_skill(text, Path("resumo.md"))

    assert skill is not None
    assert skill.name == "resumo"
    assert skill.description == "Como resumir"
    assert skill.body == "Faz três pontos."


def test_parse_rejects_incomplete_skills() -> None:
    assert parse_skill("sem frontmatter", Path("x.md")) is None
    assert parse_skill("---\nname: x\n---\n", Path("x.md")) is None
    assert parse_skill("---\ndescription: y\n---\ncorpo", Path("x.md")) is None


def test_load_skills_and_index(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        "---\nname: alfa\ndescription: A\n---\ncorpo A", encoding="utf-8"
    )
    (tmp_path / "b.md").write_text(
        "---\nname: beta\ndescription: B\n---\ncorpo B", encoding="utf-8"
    )
    (tmp_path / "c.md").write_text("lixo", encoding="utf-8")

    skills = load_skills([tmp_path])

    assert [skill.name for skill in skills] == ["alfa", "beta"]
    index = skill_index(skills)
    assert "alfa: A" in index
    assert "skill" in index


def test_user_skills_override_project_ones(tmp_path: Path) -> None:
    project = tmp_path / "project"
    user = tmp_path / "user"
    project.mkdir()
    user.mkdir()
    (project / "a.md").write_text(
        "---\nname: igual\ndescription: projeto\n---\nA", encoding="utf-8"
    )
    (user / "a.md").write_text(
        "---\nname: igual\ndescription: utilizador\n---\nB", encoding="utf-8"
    )

    skills = load_skills([project, user])

    assert len(skills) == 1
    assert skills[0].description == "utilizador"


def test_empty_index_is_empty() -> None:
    assert skill_index([]) == ""


def test_find_skill_is_case_insensitive() -> None:
    skill = parse_skill("---\nname: Resumo\n---\ncorpo", Path("x.md"))
    assert skill is not None
    assert find_skill([skill], "resumo") is skill


def test_skill_tool_returns_the_body() -> None:
    skill = parse_skill("---\nname: resumo\ndescription: d\n---\nFaz três pontos.", Path("x.md"))
    assert skill is not None
    tool = SkillTool([skill])

    result = tool.run({"name": "resumo"})

    assert result.ok is True
    assert "Faz três pontos." in result.content


def test_skill_tool_lists_available_on_a_miss() -> None:
    skill = parse_skill("---\nname: resumo\n---\ncorpo", Path("x.md"))
    assert skill is not None

    result = SkillTool([skill]).run({"name": "outra"})

    assert result.ok is False
    assert "resumo" in result.content
