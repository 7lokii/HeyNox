"""Interface web local.

Só stdlib: `ThreadingHTTPServer` e um ficheiro HTML. Ouve em 127.0.0.1 — não
há autenticação porque não há rede: quem chega ao porto já está na máquina.
Com `tray=True` (o `.exe`), o ícone da bandeja manda no ciclo de vida.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from nox.automation.routines import RoutineScheduler, RoutineStore
from nox.brain.agent import Agent, build_agent
from nox.config import Config, NoxError
from nox.desktop.guard import EMERGENCY
from nox.paths import user_data_dir
from nox.safety.approvals import ApprovalBroker
from nox.ui import static as hud
from nox.ui.state import NoxState
from nox.voice import run_voice

DEFAULT_PORT = 8765
MAX_PORT = 8785


def html_path() -> Path:
    """O `index.html` que a raiz serve. Ver `nox/ui/static.py`."""
    return hud.index_file()


class NoxApp:
    """Liga o motor à interface: conversa por texto, voz e estado."""

    def __init__(
        self,
        config: Config,
        state: NoxState | None = None,
        agent: Agent | None = None,
        approvals: ApprovalBroker | None = None,
    ) -> None:
        self.config = config
        self.state = state or NoxState()
        self.approvals = approvals or ApprovalBroker(timeout=config.tools.approval_timeout_s)
        self.routines = RoutineStore()
        self.agent = agent or build_agent(config, approvals=self.approvals)
        self.logs: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._synth = None
        self._speaker = None
        self._voice_error = ""

    def say(self, text: str) -> str:
        return self._respond(text, label=None)

    def run_routine(self, prompt: str) -> str:
        """Corre uma rotina e deixa-a marcada na conversa como tal."""
        return self._respond(prompt, label=f"(rotina) {prompt}")

    def _respond(self, text: str, *, label: str | None) -> str:
        self.state.add_turn("user", label or text)
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
        self._voice_error = ""
        self.state.set_voice(True)
        self.state.set_status("a arrancar")
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
                agent=self.agent,
                on_turn=self.state.add_turn,
                on_status=self.state.set_status,
                on_frame=self.state.set_levels,
                on_input=self.state.set_input_levels,
                stop_event=self._stop,
            )
        except NoxError as exc:
            self._voice_error = str(exc)
            self.logs.append(f"voz: {exc}")
            self.state.add_turn("assistant", f"Erro: {exc}")
        finally:
            self.state.set_voice(False)

    def voice_error(self) -> str:
        return self._voice_error


class Handler(BaseHTTPRequestHandler):
    app: NoxApp

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — assinatura da stdlib
        """Silencia o log de pedidos: a consola é do Nox, não do HTTP."""
        return

    def do_GET(self) -> None:  # noqa: N802 — nome imposto pela stdlib
        if self.path in ("/", "/index.html"):
            self._send_asset()
        elif self.path == "/api/state":
            snapshot = self.app.state.snapshot()
            snapshot["approvals"] = self.app.approvals.pending()
            snapshot["emergency"] = EMERGENCY.active
            snapshot["voice_error"] = self.app.voice_error()
            self._send_json(snapshot)
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
        elif self.path.startswith("/api/"):
            self.send_error(404)
        else:
            # Estáticos do HUD compilado: /assets/index-xxx.js, /favicon.svg.
            self._send_asset()

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
        elif self.path == "/api/approvals":
            body = self._body()
            approval_id = str(body.get("id", "")).strip()
            if not approval_id:
                self._send_json({"error": "falta o id"}, status=400)
                return
            decided = self.app.approvals.decide(approval_id, bool(body.get("approved")))
            self._send_json({"decided": decided})
        elif self.path == "/api/emergency":
            on = bool(self._body().get("on", True))
            if on:
                EMERGENCY.trigger()
            else:
                EMERGENCY.clear()
            self._send_json({"emergency": EMERGENCY.active})
        else:
            self.send_error(404)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Corpo que não é UTF-8 (um cliente antigo em cp1252, por exemplo)
            # respondia com um traceback e fechava a ligação. Um pedido mal
            # formado é um 400, não uma queda.
            return {}
        return data if isinstance(data, dict) else {}

    def _send_asset(self) -> None:
        found = hud.resolve(self.path)
        if found is None:
            self.send_error(404)
            return
        path, content_type = found
        try:
            content = path.read_bytes()
        except OSError as exc:
            self.send_error(500, str(exc))
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        # Build local: um ficheiro novo tem de aparecer no recarregar seguinte.
        self.send_header("Cache-Control", "no-cache")
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


def existing_instance() -> str | None:
    """URL de uma interface já a correr nesta máquina, se responder.

    O `.exe` é associado ao atalho: um segundo clique não pode subir outro
    servidor (o segundo perderia o registo num porto de 8766 em diante e o
    primeiro ficaria sem forma de ser encontrado).
    """
    try:
        with urllib.request.urlopen(  # noqa: S310 — URL fixo em 127.0.0.1
            f"{_state_url()}/api/state", timeout=0.6
        ) as response:
            json.loads(response.read() or b"{}")
            return _state_url()
    except (OSError, ValueError):
        return None


def _state_url() -> str:
    try:
        port = int(user_data_dir().joinpath("ui.port").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        port = DEFAULT_PORT
    return f"http://127.0.0.1:{port}"


def serve(
    config: Config,
    *,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    tray: bool = False,
    desktop: bool = False,
    out: Callable[[str], None] = print,
) -> int:
    app = NoxApp(config)
    server, bound = build_server(app, port)
    url = f"http://127.0.0.1:{bound}/"
    out(f"Nox UI em {url}")
    _claim_port(bound)
    scheduler: RoutineScheduler | None = None
    if config.automation.enabled:
        scheduler = RoutineScheduler(
            app.routines,
            lambda routine: app.run_routine(routine.prompt),
            tick_s=config.automation.tick_s,
            on_error=lambda routine, exc: app.logs.append(f"rotina {routine.id} falhou: {exc}"),
        )
        scheduler.start()
    # Em modo desktop quem mostra o HUD é a janela, não o browser.
    if open_browser and not desktop:
        webbrowser.open(url)

    icon = None
    if tray:
        try:
            from nox.ui.tray import Tray

            icon = Tray(
                url,
                on_open=lambda: _open_browser(url),
                on_toggle_voice=app.set_voice,
                # O `pystray` só sai do `run()` pelo `on_quit`; o HTTP é
                # parado a seguir, no `finally`.
                on_quit=lambda: None,
                voice_on=app.state.snapshot()["voice"],
            )
        except ImportError as exc:
            out(f"aviso: sem ícone na bandeja ({exc})")
            icon = None

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if desktop:
            _run_desktop(url, out)
        elif icon is not None:
            icon.run()
        else:
            while thread.is_alive():
                thread.join(0.5)
    except KeyboardInterrupt:
        out("a fechar")
    finally:
        if icon is not None:
            icon.stop()
        if scheduler is not None:
            scheduler.stop()
        app.stop_voice()
        app.approvals.cancel_all()
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
        _release_port()
    return 0


def _run_desktop(url: str, out: Callable[[str], None]) -> None:
    """Abre a janela nativa. Sem o extra `shell`, cai para o browser.

    Bloqueia até a janela fechar: é o ciclo de vida da app.
    """
    from nox.ui import window

    if not window.available():
        out("aviso: sem janela nativa (falta o extra `shell`); abro no browser")
        webbrowser.open(url)
        while True:
            time.sleep(0.5)
    window.open_window(url)


def _open_browser(url: str) -> None:
    webbrowser.open(url)


def _claim_port(port: int) -> None:
    # Sem o porto guardado, um segundo arranque não encontra esta instância e
    # sobe outra em 8766, com a primeira órfã.
    with suppress(OSError):
        user_data_dir().mkdir(parents=True, exist_ok=True)
        user_data_dir().joinpath("ui.port").write_text(str(port), encoding="utf-8")


def _release_port() -> None:
    with suppress(OSError):
        user_data_dir().joinpath("ui.port").unlink(missing_ok=True)
