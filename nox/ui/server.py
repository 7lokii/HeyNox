"""Interface web local.

Só stdlib: `ThreadingHTTPServer` e um ficheiro HTML. Ouve em 127.0.0.1 — não
há autenticação porque não há rede: quem chega ao porto já está na máquina.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from nox.brain.agent import Agent, build_agent
from nox.config import Config, NoxError
from nox.paths import bundle_dir
from nox.ui.state import NoxState
from nox.voice import run_voice

DEFAULT_PORT = 8765
MAX_PORT = 8785


def html_path() -> Path:
    for candidate in (
        Path(__file__).with_name("index.html"),
        bundle_dir() / "nox" / "ui" / "index.html",
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("index.html não encontrado no pacote")


class NoxApp:
    """Liga o motor à interface: conversa por texto, voz e estado."""

    def __init__(
        self,
        config: Config,
        state: NoxState | None = None,
        agent: Agent | None = None,
    ) -> None:
        self.config = config
        self.state = state or NoxState()
        self.agent = agent or build_agent(config)
        self.logs: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._synth = None
        self._speaker = None

    def say(self, text: str) -> str:
        self.state.add_turn("user", text)
        try:
            answer = self.agent.reply(text)
        except NoxError as exc:
            answer = f"Erro: {exc}"
        self.state.add_turn("assistant", answer)
        if self.config.nox.voice_enabled and not answer.startswith("Erro:"):
            threading.Thread(target=self._speak, args=(answer,), daemon=True).start()
        return answer

    def _speak(self, text: str) -> None:
        """Fala a resposta sem bloquear o pedido HTTP.

        É o que dá matéria ao espectro: a interface desenha o áudio que está
        mesmo a sair, não uma animação a fingir.
        """
        self.state.set_status("a falar")
        try:
            if self._synth is None:
                from nox.audio.speaker import SoundDeviceSpeaker
                from nox.speech.tts import build_synthesizer

                self._synth = build_synthesizer(self.config)
                self._speaker = SoundDeviceSpeaker(on_frame=self.state.set_levels)
            audio = self._synth.synthesize(text)
            if audio and self._speaker is not None:
                self._speaker.play(audio, self._synth.sample_rate)
        except (NoxError, OSError):
            return
        finally:
            # Em modo voz o estado é do loop; aqui só se não houver loop.
            if not self.state.snapshot()["voice"]:
                self.state.set_status("parado")

    def memory_facts(self) -> list[dict[str, Any]]:
        if self.agent.memory is None:
            return []
        return [
            {"id": fact.id, "kind": fact.kind, "text": fact.text}
            for fact in self.agent.memory.facts(limit=50)
        ]

    def forget(self, pattern: str) -> int:
        if self.agent.memory is None or not pattern.strip():
            return 0
        return self.agent.memory.forget(pattern)

    def set_voice(self, running: bool) -> None:
        if running:
            self.start_voice()
        else:
            self.stop_voice()

    def start_voice(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.state.set_voice(True)
        self._thread = threading.Thread(target=self._voice_loop, daemon=True)
        self._thread.start()

    def stop_voice(self) -> None:
        self._stop.set()
        self.state.set_voice(False)

    def _voice_loop(self) -> None:
        try:
            run_voice(
                self.config,
                out=self.logs.append,
                on_turn=self.state.add_turn,
                on_status=self.state.set_status,
                on_frame=self.state.set_levels,
                on_input=self.state.set_input_levels,
                stop_event=self._stop,
            )
        except NoxError as exc:
            self.state.add_turn("assistant", f"Erro: {exc}")
        finally:
            self.state.set_voice(False)


class Handler(BaseHTTPRequestHandler):
    app: NoxApp

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — assinatura da stdlib
        """Silencia o log de pedidos: a consola é do Nox, não do HTTP."""
        return

    def do_GET(self) -> None:  # noqa: N802 — nome imposto pela stdlib
        if self.path in ("/", "/index.html"):
            self._send_html()
        elif self.path == "/api/state":
            self._send_json(self.app.state.snapshot())
        elif self.path == "/api/levels":
            snapshot = self.app.state.snapshot()
            self._send_json(
                {
                    "levels": snapshot["levels"],
                    "input": snapshot["input_levels"],
                    "source": snapshot["source"],
                    "status": snapshot["status"],
                }
            )
        elif self.path == "/api/memory":
            self._send_json({"facts": self.app.memory_facts()})
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/say":
            text = str(self._body().get("text", "")).strip()
            if not text:
                self._send_json({"error": "texto vazio"}, status=400)
                return
            self._send_json({"answer": self.app.say(text)})
        elif self.path == "/api/voice":
            running = bool(self._body().get("on"))
            self.app.set_voice(running)
            self._send_json({"voice": running})
        elif self.path == "/api/memory/forget":
            pattern = str(self._body().get("pattern", "")).strip()
            self._send_json({"removed": self.app.forget(pattern)})
        else:
            self.send_error(404)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _send_html(self) -> None:
        try:
            content = html_path().read_bytes()
        except FileNotFoundError as exc:
            self.send_error(500, str(exc))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_server(app: NoxApp, port: int = DEFAULT_PORT) -> tuple[ThreadingHTTPServer, int]:
    """Sobe o servidor no primeiro porto livre."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    for candidate in range(port, MAX_PORT + 1):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError:
            continue
        return server, int(server.server_address[1])
    raise NoxError(f"nenhum porto livre entre {port} e {MAX_PORT}")


def serve(
    config: Config,
    *,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    out: Callable[[str], None] = print,
) -> int:
    app = NoxApp(config)
    server, bound = build_server(app, port)
    url = f"http://127.0.0.1:{bound}/"
    out(f"Nox UI em {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        out("a fechar")
    finally:
        app.stop_voice()
        server.server_close()
    return 0
