"""Ferramentas de servidores MCP, expostas ao agente.

Cada ferramenta de um servidor MCP passa a ser uma ferramenta do Nox com o nome
`mcp_<servidor>_<ferramenta>`. O modelo vê a descrição e o schema originais.

Arrancar processos externos no arranque é uma decisão explícita: `mcp.enabled`
está desligado por omissão.
"""

from __future__ import annotations

import re
from typing import Any

from nox.config import Config
from nox.mcp.client import McpError, McpServer, McpToolInfo
from nox.tools.base import ToolResult


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return clean[:40] or "x"


class McpToolAdapter:
    def __init__(self, server: McpServer, server_name: str, info: McpToolInfo) -> None:
        self._server = server
        self._tool = info.name
        self.name = f"mcp_{_slug(server_name)}_{_slug(info.name)}"
        self.description = f"[MCP:{server_name}] {info.description or info.name}"
        self.schema = info.schema

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            ok, text = self._server.call_tool(self._tool, arguments)
        except McpError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(ok, text)


def build_mcp_tools(config: Config, *, out: Any = None) -> list[Any]:
    """Arranca os servidores configurados e devolve as ferramentas.

    Um servidor que falhe é ignorado com um aviso — não impede o Nox de arrancar.
    """
    if not config.mcp.enabled or not config.mcp.servers:
        return []

    tools: list[Any] = []
    used: set[str] = set()
    for name, settings in config.mcp.servers.items():
        if not settings.enabled:
            continue
        server = McpServer(
            name,
            settings.command,
            settings.args,
            settings.env,
            timeout_s=config.mcp.timeout_s,
        )
        try:
            server.start()
            infos = server.list_tools()
        except McpError as exc:
            if out is not None:
                out(f"aviso: MCP '{name}' indisponível: {exc}")
            server.stop()
            continue
        if not infos:
            server.stop()
            continue
        for info in infos:
            adapter = McpToolAdapter(server, name, info)
            if adapter.name in used:
                adapter.name = f"{adapter.name}_2"
            used.add(adapter.name)
            tools.append(adapter)
    return tools
