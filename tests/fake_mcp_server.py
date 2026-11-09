"""Servidor MCP mínimo para os testes: initialize, tools/list e tools/call."""

import json
import sys
from typing import Any, cast

cast(Any, sys.stdin).reconfigure(encoding="utf-8")
cast(Any, sys.stdout).reconfigure(encoding="utf-8")


def reply(request_id: object, result: dict) -> None:
    print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    message = json.loads(line)
    method = message.get("method")
    if "id" not in message:
        continue
    if method == "initialize":
        reply(
            message["id"],
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "1.0"},
            },
        )
    elif method == "tools/list":
        reply(
            message["id"],
            {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Devolve o texto recebido",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                    }
                ]
            },
        )
    elif method == "tools/call":
        arguments = message.get("params", {}).get("arguments", {})
        reply(
            message["id"],
            {
                "content": [{"type": "text", "text": f"eco: {arguments.get('text', '')}"}],
                "isError": False,
            },
        )
    else:
        reply(message["id"], {})
