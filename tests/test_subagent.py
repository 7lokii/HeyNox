from typing import cast

from nox.brain.agent import Agent
from nox.config import NoxError
from nox.tools.subagent import SpawnAgentTool


class FakeAgent:
    def __init__(self, answer: str = "feito") -> None:
        self.answer = answer
        self.tasks: list[str] = []

    def reply(self, task: str) -> str:
        self.tasks.append(task)
        return f"{self.answer}: {task}"


def test_spawn_agent_returns_the_result() -> None:
    agent = FakeAgent()
    tool = SpawnAgentTool(lambda: cast(Agent, agent))

    result = tool.run({"task": "resume o dia"})

    assert result.ok is True
    assert result.content == "feito: resume o dia"
    assert agent.tasks == ["resume o dia"]


def test_spawn_agent_needs_a_task() -> None:
    tool = SpawnAgentTool(lambda: cast(Agent, FakeAgent()))
    result = tool.run({"task": "  "})
    assert result.ok is False
    assert "falta a tarefa" in result.content


def test_spawn_agent_reports_errors() -> None:
    class Broken:
        def reply(self, task: str) -> str:
            raise NoxError("modelo em baixo")

    tool = SpawnAgentTool(lambda: cast(Agent, Broken()))

    result = tool.run({"task": "x"})

    assert result.ok is False
    assert "modelo em baixo" in result.content
