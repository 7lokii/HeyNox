"""Interface web local do HeyNox.

Só stdlib: `ThreadingHTTPServer` e o HUD compilado. Ouve em 127.0.0.1 e não
tem autenticação própria: no homelab o único cliente é o proxy autenticado do
NoxSec, em `/heynox`. O browser local só é aberto no modo `--ui`.
"""

from __future__ import annotations

import base64
import json
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from nox import __version__
from nox.audio.wake import VoskWakeVerifier, WakeVerifier, strip_wake_word
from nox.automation.routines import RoutineScheduler, RoutineStore
from nox.brain.agent import Agent, build_agent
from nox.config import Config, NoxError
from nox.desktop.guard import EMERGENCY
from nox.integrations.whatsapp import (
    WHATSAPP_GUEST_SYSTEM,
    WHATSAPP_OWNER_SYSTEM,
    WHATSAPP_SYSTEM,
    WhatsAppService,
)
from nox.models import ensure_vosk_model
from nox.paths import user_data_dir
from nox.safety.approvals import ApprovalBroker
from nox.metrics import RegistoDeMetricas, Turno, registo_por_omissao
from nox.ui import settings as settings_ui
from nox.ui import static as hud
from nox.ui.state import NoxState
from nox.voice import run_voice

DEFAULT_PORT = 8765
MAX_PORT = 8785
# Uma frase de 50 s a 16 kHz mono são 1,6 MB; acima disso é abuso, não voz.
MAX_VOICE_BYTES = 1_600_000


def _build_whatsapp_agents(config: Config) -> tuple[Agent, Agent]:
    """Dois agentes separados: o dono e os convidados não partilham conversa."""

    def build(extra_system: str) -> Agent:
        return build_agent(
            config,
            with_tools=False,
            with_memory=False,
            allow_emergency=False,
            extra_system=WHATSAPP_SYSTEM + extra_system,
        )

    return build(WHATSAPP_OWNER_SYSTEM), build(WHATSAPP_GUEST_SYSTEM)


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
        settings: settings_ui.SettingsStore | None = None,
        whatsapp: WhatsAppService | None = None,
        wake_verifier: WakeVerifier | None = None,
    ) -> None:
        self.config = config
        self.state = state or NoxState()
        # Injeta-se nos testes: o padrão escreve no diretório real do utilizador.
        self.settings = settings or settings_ui.SettingsStore()
        self.approvals = approvals or ApprovalBroker(
            timeout=config.tools.approval_timeout_s,
            full_access=config.tools.full_access,
        )
        self.routines = RoutineStore()
        self.agent = agent or build_agent(config, approvals=self.approvals)
        # O canal WhatsApp não vê ferramentas nem a memória privada. O dono e
        # os restantes membros têm agentes separados, para a conversa de um não
        # servir de contexto ao outro.
        self.whatsapp_owner_agent, self.whatsapp_guest_agent = _build_whatsapp_agents(config)
        self.logs: list[str] = []
        self.whatsapp = whatsapp or WhatsAppService(self._whatsapp_reply, log=self.logs.append)
        self._wire_whatsapp_context()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._synth = None
        self._speaker = None
        self._voice_error = ""
        self._voice_awake_until = 0.0
        self._transcriber = None
        self._transcriber_lock = threading.Lock()
        self._synth_lock = threading.Lock()
        self._wake_verifier = wake_verifier
        self._wake_verifier_injected = wake_verifier is not None
        # Medição por turno: onde é que o tempo vai. Ver nox/metrics.py.
        self.metrics = registo_por_omissao()
        self._wake_verifier_lock = threading.Lock()

    def _wire_whatsapp_context(self) -> None:
        """O dono vê o histórico; o convidado só vê a contagem do grupo."""
        self.whatsapp_owner_agent.context = lambda _text: self.whatsapp.context(owner=True)
        self.whatsapp_guest_agent.context = lambda _text: self.whatsapp.context(owner=False)

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

    def _whatsapp_reply(self, text: str, _sender: str, owner: bool) -> str:
        """Resposta no grupo: o dono e os convidados usam agentes diferentes."""
        agent = self.whatsapp_owner_agent if owner else self.whatsapp_guest_agent
        answer = agent.reply(text)
        label = "dono" if owner else "convidado"
        self.state.add_turn("user", f"(WhatsApp {label}) {text}")
        self.state.add_turn("assistant", answer)
        return answer

    def whatsapp_payload(self) -> dict[str, Any]:
        return self.whatsapp.payload()

    def start_whatsapp(self) -> None:
        """Retoma o modo se estava ligado quando a app fechou."""
        self.whatsapp.resume()

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
        except (NoxError, ImportError) as exc:
            # OptionalDependencyError é ImportError: sem esta captura o botão
            # voltava a "Ouvir" sem explicar porquê.
            self._voice_error = str(exc)
            self.logs.append(f"voz: {exc}")
            self.state.add_turn("assistant", f"Erro: {exc}")
        finally:
            self.state.set_voice(False)

    def voice_error(self) -> str:
        return self._voice_error

    def _wake_check(self) -> WakeVerifier:
        """Constrói o Vosk uma vez; o modelo fica em cache no processo."""
        with self._wake_verifier_lock:
            if self._wake_verifier is not None:
                return self._wake_verifier
            settings = self.config.wake
            try:
                model = ensure_vosk_model(
                    settings.model,
                    progress=lambda message: self.logs.append(f"wake: {message}"),
                )
                self._wake_verifier = VoskWakeVerifier(
                    settings.phrases or [self.config.nox.wake_word],
                    model_path=model,
                    sample_rate=16000,
                    grammar=settings.grammar or None,
                )
            except (NoxError, ImportError, OSError) as exc:
                self.logs.append(f"wake: {exc}")
                raise NoxError(f"não consegui validar a wake word: {exc}") from exc
            return self._wake_verifier

    def aquecer_voz(self) -> None:
        """Carrega em segundo plano o que custa no primeiro turno.

        O Vosk leva cerca de 800 ms a carregar o modelo e o Piper leva cerca de
        300 ms a carregar o ONNX. Feito no arranque, o custo nao cai no primeiro
        «Nox» do dia. Falha em silencio: sem o modelo, o primeiro turno carrega-o
        como antes, so que mais devagar.
        """
        if self.config.wake.provider == "off" and self.config.tts.provider != "piper":
            return

        def carregar() -> None:
            if self.config.wake.provider != "off":
                try:
                    self._wake_check()
                except Exception:  # noqa: BLE001 - aquecer nunca trava o servico
                    pass
            if self.config.tts.provider == "piper":
                try:
                    self._piper()
                except Exception:  # noqa: BLE001
                    pass

        threading.Thread(target=carregar, daemon=True, name="nox-aquecer").start()

    def _sintetizar_resposta(self, texto: str) -> tuple[str, str, str]:
        """Áudio da resposta em base64, o mime e o erro, se houver.

        O `edge` devolve MP3 (rede); o `piper` devolve WAV (local). O browser
        recebe o mime junto com o áudio para saber o que tocar.
        """
        provider = self.config.tts.provider
        try:
            if provider == "edge":
                from nox.speech.edge import synthesize_mp3

                mp3 = synthesize_mp3(
                    texto,
                    self.config.tts.voice,
                    speed=self.config.tts.speed,
                    cache=self.config.tts.cache,
                )
                if not mp3:
                    return "", "", ""
                return base64.b64encode(mp3).decode("ascii"), "audio/mpeg", ""

            if provider == "piper":
                from nox.audio.wav import wav_bytes
                from nox.speech.tts_cache import CacheDeVoz, cache_por_omissao

                cache = cache_por_omissao() if self.config.tts.cache else None
                chave = CacheDeVoz.chave(
                    texto, self.config.tts.voice, self.config.tts.speed
                )
                if cache is not None:
                    existente = cache.obter(chave, ".wav")
                    if existente is not None:
                        return base64.b64encode(existente).decode("ascii"), "audio/wav", ""

                sintetizador = self._piper()
                audio = sintetizador.synthesize(texto)
                if not audio:
                    return "", "", ""
                wav = wav_bytes(audio, sintetizador.sample_rate)
                if cache is not None:
                    cache.guardar(chave, wav, ".wav")
                return base64.b64encode(wav).decode("ascii"), "audio/wav", ""
            return "", "", ""
        except (NoxError, ImportError, OSError) as exc:
            # O texto vai na mesma; o HUD cai para a voz do sistema.
            return "", "", str(exc)

    def _piper(self):
        """O Piper carregado uma vez; o modelo é descarregado se faltar."""
        with self._synth_lock:
            if self._synth is None:
                from nox.models import ensure_piper_voice
                from nox.speech.tts import PiperSynthesizer

                caminho = ensure_piper_voice(
                    self.config.tts.voice, directory=self.settings.root / "models" / "piper"
                )
                self._synth = PiperSynthesizer(caminho, speed=self.config.tts.speed)
            return self._synth

    def voice_turn(self, audio: bytes, sample_rate: int) -> dict[str, Any]:
        """Turno de voz vindo do microfone do browser/WebView.

        O homelab não tem placa de som: quem ouve é o dispositivo que abriu o
        HUD. O áudio sobe em PCM 16 bits, é transcrito aqui e a resposta volta
        em texto e MP3 para o browser tocar.
        """
        from nox.audio.types import Pcm
        from nox.speech.stt import build_transcriber

        pcm = Pcm(audio)
        inicio = time.monotonic()
        wake_ms: float | None = None
        stt_ms: float | None = None
        llm_ms: float | None = None
        tts_ms: float | None = None
        wake_gate = self.config.wake.provider != "off"
        phrases = self.config.wake.phrases or [self.config.nox.wake_word]
        now = time.monotonic()
        armed = wake_gate and now < self._voice_awake_until
        validated = False
        if wake_gate and not armed:
            # O Vosk valida a posição no áudio antes de o Whisper ser chamado.
            # Conversa sem ativação não sai para a cloud.
            marca_wake = time.monotonic()
            if not self._wake_check().accepts(pcm, sample_rate):
                return {
                    "text": "",
                    "answer": "",
                    "audio": "",
                    "voice_error": "",
                    "wake": False,
                    "hint": f"diz «{self.config.nox.name}» para falar.",
                }
            validated = True
            wake_ms = (time.monotonic() - marca_wake) * 1000

        with self._transcriber_lock:
            if self._transcriber is None:
                self._transcriber = build_transcriber(self.config)
        marca_stt = time.monotonic()
        text = self._transcriber.transcribe(pcm, sample_rate)
        stt_ms = (time.monotonic() - marca_stt) * 1000
        if not text:
            if wake_gate and validated:
                # O Vosk ouviu a ativação, mas o Whisper não devolveu texto
                # (acontece com um "Nox" muito curto). A ativação é válida:
                # abre-se a janela para o pedido seguinte.
                self._voice_awake_until = now + self.config.wake.timeout_s
                return {
                    "text": "",
                    "answer": "",
                    "audio": "",
                    "voice_error": "",
                    "wake": True,
                    "hint": f"diz o pedido depois de «{self.config.nox.name}».",
                }
            return {
                "text": "",
                "answer": "",
                "audio": "",
                "voice_error": "",
                "wake": True,
                "hint": "",
            }

        if wake_gate and validated:
            # O Vosk é a autoridade da posição. O Whisper pode não repetir
            # "Nox" (ou colocá-la noutro sítio); a transcrição é o pedido, e a
            # palavra só se retira quando abre a frase.
            command = strip_wake_word(text, phrases)
            if command == text.strip():
                command = text.strip()
            if not command:
                # Dizer só "Nox" e fazer uma pausa é uma ativação válida: o
                # pedido seguinte chega noutro turno, como no loop --voice.
                self._voice_awake_until = now + self.config.wake.timeout_s
                return {
                    "text": text,
                    "answer": "",
                    "audio": "",
                    "voice_error": "",
                    "wake": True,
                    "hint": f"diz o pedido depois de «{self.config.nox.name}».",
                }
        else:
            command = text

        if wake_gate:
            # Consumido o pedido, a janela fecha. Só volta a abrir com outra
            # ativação; uma resposta não deixa o microfone à escuta do Nox.
            self._voice_awake_until = 0.0

        self.state.add_turn("user", text)
        marca_llm = time.monotonic()
        erro_llm = ""
        try:
            answer = self.agent.reply(command)
        except NoxError as exc:
            answer = f"Erro: {exc}"
            erro_llm = str(exc)
        llm_ms = (time.monotonic() - marca_llm) * 1000
        self.state.add_turn("assistant", answer)
        # Cada novo pedido exige a wake word. A única janela é a aberta por
        # dizer só "Nox" e fazer uma pausa; uma resposta não arma outra.

        encoded = ""
        audio_mime = ""
        voice_error = ""
        marca_tts = time.monotonic()
        if answer and not answer.startswith("Erro:"):
            encoded, audio_mime, voice_error = self._sintetizar_resposta(answer)
        if encoded:
            tts_ms = (time.monotonic() - marca_tts) * 1000

        self.metrics.registar(
            Turno(
                origem="hud",
                wake_ms=wake_ms,
                stt_ms=stt_ms,
                llm_ms=llm_ms,
                tts_ms=tts_ms,
                total_ms=(time.monotonic() - inicio) * 1000,
                pedido_chars=len(text or ""),
                resposta_chars=len(answer or ""),
                ok=not erro_llm,
                erro=erro_llm,
            )
        )
        return {
            "text": text,
            "answer": answer,
            "audio": encoded,
            "audio_mime": audio_mime,
            "voice_error": voice_error,
            "wake": True,
            "hint": "",
        }

    # ---------------------- configuração na interface ----------------------

    def setup_required(self) -> bool:
        """Primeiro arranque: sem chave de modelo, a app pede a configuração."""
        return not self.settings.has_model_key()

    def settings_payload(self) -> dict[str, Any]:
        return {
            "providers": [provider.as_dict() for provider in settings_ui.PROVIDERS],
            "values": self.settings.values(),
            "secrets": self.settings.secrets_status(),
            "setup_required": self.setup_required(),
            "version": __version__,
            "paths": {
                "data": str(self.settings.root),
                "config": str(self.settings.config_path),
                "env": str(self.settings.env_path),
            },
        }

    def apply_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Grava e passa a usar o que ficou gravado, sem reiniciar a app."""
        result = self.settings.save(payload)
        was_voice = bool(self.state.snapshot()["voice"])
        if was_voice:
            self.stop_voice()
        self.config = settings_ui.load_config(self.settings.config_path)
        self.approvals.set_full_access(self.config.tools.full_access)
        if not self._wake_verifier_injected:
            with self._wake_verifier_lock:
                self._wake_verifier = None
        with self._transcriber_lock:
            self._transcriber = None
        self.agent = build_agent(self.config, approvals=self.approvals)
        self.whatsapp_owner_agent, self.whatsapp_guest_agent = _build_whatsapp_agents(self.config)
        self._wire_whatsapp_context()
        self._synth = None
        self._speaker = None
        result["setup_required"] = self.setup_required()
        if was_voice and self.config.nox.voice_enabled:
            threading.Thread(target=self.start_voice, daemon=True).start()
        return result

class Handler(BaseHTTPRequestHandler):
    app: NoxApp

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — assinatura da stdlib
        """Silencia o log de pedidos: a consola é do Nox, não do HTTP."""
        return

    def do_GET(self) -> None:  # noqa: N802 — nome imposto pela stdlib
        if self.path in ("/", "/index.html"):
            self._send_asset()
        elif self.path == "/api/health":
            self._send_json({"ok": True, "service": "heynox"})
        elif self.path == "/api/state":
            snapshot = self.app.state.snapshot()
            snapshot["approvals"] = self.app.approvals.pending()
            snapshot["emergency"] = EMERGENCY.active
            snapshot["voice_error"] = self.app.voice_error()
            snapshot["setup_required"] = self.app.setup_required()
            snapshot["full_access"] = self.app.approvals.full_access
            self._send_json(snapshot)
        elif self.path.split("?", 1)[0] == "/api/metrics":
            # Quantos turnos resumir; por omissão 200, o suficiente para uma
            # sessão e barato de ler.
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            try:
                ultimos = int(query.get("turnos", ["200"])[0])
            except ValueError:
                ultimos = 200
            self._send_json(self.app.metrics.resumo(max(1, min(ultimos, 5000))))
        elif self.path == "/api/settings":
            self._send_json(self.app.settings_payload())
        elif self.path == "/api/devices":
            self._send_json(
                {"devices": self._devices(), "selected": self.app.config.audio.input_device}
            )
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
        elif self.path == "/api/whatsapp":
            self._safe_json(self.app.whatsapp_payload)
        elif self.path.startswith("/api/"):
            self.send_error(404)
        else:
            # Estáticos do HUD compilado: /assets/index-xxx.js, /favicon.svg.
            self._send_asset()

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/say":
            text = str(self._body().get("text", "")).strip()
            if not text:
                self._send_json({"error": "texto vazio"}, status=400)
                return
            self._send_json({"answer": self.app.say(text)})
        elif path == "/api/voice":
            running = bool(self._body().get("on"))
            self.app.set_voice(running)
            self._send_json({"voice": running})
        elif path == "/api/voice/turn":
            self._voice_turn()
        elif path == "/api/memory/forget":
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
        elif self.path == "/api/whatsapp":
            on = bool(self._body().get("on", False))
            self._safe_json(lambda: self.app.whatsapp.set_enabled(on))
        elif self.path == "/api/whatsapp/group":
            jid = str(self._body().get("jid", "")).strip()
            try:
                payload = self.app.whatsapp.select_group(jid)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
        elif self.path == "/api/whatsapp/groups":
            self._safe_json(self.app.whatsapp.refresh_groups)
        elif self.path == "/api/whatsapp/mode":
            mode = str(self._body().get("mode", "")).strip()
            try:
                payload = self.app.whatsapp.set_mode(mode)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
        elif self.path == "/api/settings":
            self._safe_json(lambda: self.app.apply_settings(self._body()))
        elif self.path == "/api/settings/test":
            self._safe_json(lambda: self._test_key())
        else:
            self.send_error(404)

    def _voice_turn(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length % 2:
            self._send_json({"error": "audio invalido"}, status=400)
            return
        if length > MAX_VOICE_BYTES:
            self._send_json({"error": "audio demasiado longo"}, status=413)
            return
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        try:
            sample_rate = int(query.get("rate", ["16000"])[0])
        except ValueError:
            sample_rate = 16000
        if not 8000 <= sample_rate <= 48000:
            self._send_json({"error": "taxa de amostragem invalida"}, status=400)
            return
        audio = self.rfile.read(length)
        try:
            self._send_json(self.app.voice_turn(audio, sample_rate))
        except (NoxError, ImportError) as exc:
            self._send_json({"error": str(exc)}, status=503)
        except Exception as exc:  # noqa: BLE001 - o HUD tem de receber uma explicação
            self._send_json({"error": f"a voz falhou: {exc}"}, status=500)

    def _test_key(self) -> dict[str, Any]:
        ok, message = self.app.settings.test_key(self._body())
        return {"ok": ok, "message": message}

    def _safe_json(self, producer: Callable[[], dict[str, Any]]) -> None:
        """Uma leitura falhada tem de virar um 500 em JSON, não uma resposta vazia."""
        try:
            self._send_json(producer())
        except Exception as exc:  # noqa: BLE001 — a interface não pode ficar sem resposta
            self._send_json({"error": str(exc)}, status=500)

    def _devices(self) -> list[dict[str, Any]]:
        """Microfones visíveis, sem deixar a interface rebentar sem PortAudio."""
        try:
            from nox.audio.devices import input_devices

            return [{"index": index, "name": name} for index, name in input_devices()]
        except Exception:  # noqa: BLE001 — sem áudio a lista fica vazia
            return []

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


def build_server(
    app: NoxApp, port: int = DEFAULT_PORT, *, strict_port: bool = False
) -> tuple[ThreadingHTTPServer, int]:
    """Sobe o servidor no primeiro porto livre, ou só no porto pedido."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    candidates = (port,) if strict_port else range(port, MAX_PORT + 1)
    for candidate in candidates:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as exc:
            if strict_port:
                raise NoxError(f"o porto {candidate} já está ocupado") from exc
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
    strict_port: bool = False,
    out: Callable[[str], None] = print,
) -> int:
    app = NoxApp(config)
    app.aquecer_voz()
    server, bound = build_server(app, port, strict_port=strict_port)
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
    if open_browser:
        webbrowser.open(url)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Se o modo estava ligado, volta a ligar em segundo plano; a UI mostra o
    # estado assim que o servidor responde.
    app.start_whatsapp()
    try:
        while thread.is_alive():
            thread.join(0.5)
    except KeyboardInterrupt:
        out("a fechar")
    finally:
        if scheduler is not None:
            scheduler.stop()
        app.stop_voice()
        app.whatsapp.stop()
        app.approvals.cancel_all()
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
        _release_port()
    return 0


def _claim_port(port: int) -> None:
    # Sem o porto guardado, um segundo arranque não encontra esta instância e
    # sobe outra em 8766, com a primeira órfã.
    with suppress(OSError):
        user_data_dir().mkdir(parents=True, exist_ok=True)
        user_data_dir().joinpath("ui.port").write_text(str(port), encoding="utf-8")


def _release_port() -> None:
    with suppress(OSError):
        user_data_dir().joinpath("ui.port").unlink(missing_ok=True)
