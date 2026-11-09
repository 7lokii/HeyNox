"""Cliente MCP por stdio.

Fala JSON-RPC 2.0 com um servidor MCP lançado como processo filho: `initialize`,
`tools/list` e `tools/call`. Sem dependências — só `subprocess` e `json`.

O protocolo é de linhas: cada mensagem é um JSON numa linha. O leitor corre num
thread e entrega as mensagens por fila, para um servidor lento não bloquear o
Nox para sempre.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

from nox.config import NoxError

PROTOCOL_VERSION = "2024-11-05"


class McpError(NoxError):
    """O servidor MCP falhou ou não respondeu."""


@dataclass
class McpToolInfo:
    name: str
    description: str
    schema: dict[str, Any]


class McpServer:
    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        *,
        timeout_s: float = 20.0,
    ) -> None:
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.timeout_s = timeout_s
        self._proc: subprocess.Popen[str] | None = None
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._lock = threading.Lock()
        self._counter = 0
        self._initialized = False

    # --- processo --------------------------------------------------------

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        env = {**os.environ, **self.env}
        options: dict[str, Any] = {}
        if sys.platform == "win32":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            self._proc = subprocess.Popen(  # noqa: S603 — comando vem da config local
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=env,
                **options,
            )
        except OSError as exc:
            raise McpError(f"não consegui arrancar o servidor MCP '{self.name}': {exc}") from exc
        self._queue = queue.Queue()
        threading.Thread(target=self._read, name=f"mcp-{self.name}", daemon=True).start()
        atexit.register(self.stop)
        self._initialize()

    def _read(self) -> None:
        process = self._proc
        if process is None or process.stdout is None:
            self._queue.put(None)
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._queue.put(message)
        self._queue.put(None)

    def _send(self, payload: dict[str, Any]) -> None:
        process = self._proc
        if process is None or process.stdin is None:
            raise McpError(f"o servidor MCP '{self.name}' não está a correr")
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise McpError(f"não consegui falar com o servidor MCP '{self.name}': {exc}") from exc

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self._counter += 1
            request_id = self._counter
            payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
            if params is not None:
                payload["params"] = params
            self._send(payload)

            deadline = time.monotonic() + self.timeout_s
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise McpError(f"o servidor MCP '{self.name}' não respondeu a {method}")
                try:
                    message = self._queue.get(timeout=remaining)
                except queue.Empty as exc:
                    raise McpError(
                        f"o servidor MCP '{self.name}' não respondeu a {method}"
                    ) from exc
                if message is None:
                    raise McpError(f"o servidor MCP '{self.name}' fechou a ligação")
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    error = message["error"]
                    text = error.get("message", error) if isinstance(error, dict) else error
                    raise McpError(f"o servidor MCP '{self.name}' recusou {method}: {text}")
                result = message.get("result")
                return result if isinstance(result, dict) else {}

    def _initialize(self) -> None:
        if self._initialized:
            return
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "HeyNox", "version": "0.1"},
            },
        )
        self._notify("notifications/initialized", {})
        self._initialized = True

    # --- API -------------------------------------------------------------

    def start(self) -> None:
        self._ensure_started()

    def list_tools(self) -> list[McpToolInfo]:
        self._ensure_started()
        result = self._request("tools/list", {})
        tools = result.get("tools") or []
        parsed: list[McpToolInfo] = []
        for item in tools:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            schema = item.get("inputSchema")
            parsed.append(
                McpToolInfo(
                    name=str(item["name"]),
                    description=str(item.get("description") or ""),
                    schema=schema if isinstance(schema, dict) else {"type": "object"},
                )
            )
        return parsed

    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        self._ensure_started()
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content") or []
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text") or ""))
        text = "\n".join(part for part in texts if part).strip() or "(sem resultado)"
        return not bool(result.get("isError")), text

    def stop(self) -> None:
        process = self._proc
        self._proc = None
        self._initialized = False
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            with contextlib.suppress(OSError):
                process.kill()
