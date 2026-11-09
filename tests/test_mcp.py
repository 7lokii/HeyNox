import sys
from pathlib import Path

from nox.config import Config
from nox.mcp.client import McpServer
from nox.tools.mcp import build_mcp_tools

FAKE = Path(__file__).with_name("fake_mcp_server.py")


def test_client_initialize_list_and_call() -> None:
    server = McpServer("fake", sys.executable, [str(FAKE)], timeout_s=15)
    try:
        server.start()
        tools = server.list_tools()
        assert [tool.name for tool in tools] == ["echo"]
        assert tools[0].description == "Devolve o texto recebido"

        ok, text = server.call_tool("echo", {"text": "olá"})
        assert ok is True
        assert text == "eco: olá"
    finally:
        server.stop()


def test_tools_are_registered_with_a_prefix() -> None:
    config = Config.model_validate(
        {
            "mcp": {
                "enabled": True,
                "timeout_s": 15,
                "servers": {
                    "fake": {"command": sys.executable, "args": [str(FAKE)]},
                },
            }
        }
    )
    tools = build_mcp_tools(config)
    try:
        assert [tool.name for tool in tools] == ["mcp_fake_echo"]
        result = tools[0].run({"text": "teste"})
        assert result.ok is True
        assert result.content == "eco: teste"
    finally:
        for tool in tools:
            tool._server.stop()


def test_disabled_mcp_returns_nothing() -> None:
    assert build_mcp_tools(Config()) == []


def test_a_broken_server_is_skipped() -> None:
    config = Config.model_validate(
        {
            "mcp": {
                "enabled": True,
                "timeout_s": 2,
                "servers": {"morto": {"command": "isto-nao-existe-nox"}},
            }
        }
    )
    warnings: list[str] = []

    tools = build_mcp_tools(config, out=warnings.append)

    assert tools == []
    assert warnings and "indisponível" in warnings[0]
