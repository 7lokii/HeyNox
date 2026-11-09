"""Loop de conversação por voz.

Microfone -> VAD/Segmenter -> STT -> Agent -> TTS -> altifalante.

Sem wake word: o Nox ouve sempre. A ativação por "Hey Nox" entra quando houver
modelo treinado; até lá, `--voice` é conversa contínua.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from threading import Event

from nox.audio.levels import MicMeter
from nox.audio.mic import AudioError, SoundDeviceSource
from nox.audio.source import AudioSource, WavSource
from nox.audio.speaker import SoundDeviceSpeaker, Speaker
from nox.audio.types import Pcm, rms
from nox.audio.vad import EnergyVad, Segmenter, VoiceActivityDetector, WebRtcVad
from nox.audio.wake import VoskWakeWord, WakeWordDetector
from nox.brain.agent import Agent, build_agent
from nox.config import Config, NoxError
from nox.models import ModelError
from nox.speech.stt import Transcriber, build_transcriber
from nox.speech.tts import Synthesizer, build_synthesizer, split_sentences


class Step(Enum):
    """Resultado de ler um bloco de áudio."""

    IDLE = auto()
    TURN = auto()
    END = auto()


# Frases curtas sintetizadas uma vez no arranque. Cobrem o silêncio enquanto o
# STT e o modelo trabalham, para a resposta não parecer um congelamento.
FILLERS = ("Hmm.", "Deixa-me ver.", "Um momento.")


@dataclass
class VoiceLoop:
    source: AudioSource
    segmenter: Segmenter
    transcriber: Transcriber
    synthesizer: Synthesizer
    speaker: Speaker
    agent: Agent
    out: Callable[[str], None]
    name: str = "Nox"
    block_frames: int = 480
    fillers: tuple[str, ...] = ()
    wake: WakeWordDetector | None = None
    wake_timeout_s: float = 8.0
    follow_up_s: float = 6.0
    barge_in: bool = False
    barge_in_ms: int = 300
    barge_in_threshold: float = 800.0
    min_rms: float = 120.0
    duplicate_window_s: float = 3.0
    on_turn: Callable[[str, str], None] | None = None
    on_status: Callable[[str], None] | None = None
    on_frame: Callable[[list[float]], None] | None = None
    on_input: Callable[[list[float]], None] | None = None
    stop_event: Event | None = None
    _meter: MicMeter | None = field(default=None, repr=False, init=False)
    _armed: bool = field(default=False, repr=False)
    _armed_at: float = field(default=0.0, repr=False)
    _follow_up: bool = field(default=False, repr=False)
    _last_text: str = field(default="", repr=False)
    _last_at: float = field(default=0.0, repr=False)
    _filler_audio: list[Pcm] = field(default_factory=list, repr=False)
    _filler_index: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if self.on_input is not None:
            self._meter = MicMeter(self.segmenter.sample_rate, on_frame=self.on_input)

    def run(self, *, max_turns: int | None = None) -> int:
        # Carregar modelos leva segundos; o microfone já encheu entretanto.
        self.source.flush()
        self._prepare_fillers()
        label = getattr(self.source, "device_label", "")
        if label:
            self.out(f"microfone: {label[:70]}")
        if self.wake is None:
            self.out("A ouvir. Fala à vontade; Ctrl+C para parar.")
        else:
            self.out("A aguardar a palavra de ativação. Ctrl+C para parar.")
        self._status("a ouvir" if self.wake is None else "a aguardar palavra")
        turns = 0
        try:
            while max_turns is None or turns < max_turns:
                if self.stop_event is not None and self.stop_event.is_set():
                    break
                outcome = self.step()
                if outcome is Step.END:
                    break
                if outcome is Step.TURN:
                    turns += 1
        except KeyboardInterrupt:
            self.out("")
        finally:
            self._status("parado")
        return turns

    def step(self) -> Step:
        """Lê um bloco de áudio e trata o turno, se a frase fechou."""
        chunk = self.source.read(self.block_frames)
        if not chunk:
            return Step.END
        if self._meter is not None:
            self._meter.process(chunk)

        if self.wake is not None and not self._armed:
            if self.wake.process(chunk):
                self._armed = True
                self._armed_at = time.monotonic()
                self._follow_up = False
                self.segmenter.reset()
                self.out(f"{self.name}> (pode falar)")
                self._status("a ouvir")
                self._status("a ouvir")
            return Step.IDLE

        if self._armed and time.monotonic() - self._armed_at > self.wake_timeout_s:
            self._armed = False
            self.segmenter.reset()
            self.out(f"{self.name}> (não ouvi nada)")
            self._status("a aguardar palavra")
            self._status("a aguardar palavra")
            return Step.IDLE

        utterance = self.segmenter.feed(chunk)
        if not utterance:
            return Step.IDLE
        return Step.TURN if self.handle(utterance) else Step.IDLE

    def handle(self, utterance: Pcm) -> bool:
        # Abaixo disto é ruído: transcrever só produziria invenções.
        if rms(utterance) < self.min_rms:
            return False

        rate = self.segmenter.sample_rate
        # O filler toca enquanto o STT trabalha: cobre o silêncio sem lhe somar
        # tempo. Em série, o "Hmm." atrasava a transcrição em vez de a esconder.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.transcriber.transcribe, utterance, rate)
            self._play_filler()
            text = pending.result().strip()
        if not text:
            return False

        # A mesma frase duas vezes em poucos segundos é eco ou reprocessamento,
        # não uma repetição deliberada.
        now = time.monotonic()
        if text == self._last_text and now - self._last_at < self.duplicate_window_s:
            self.out(f"{self.name}> (repetido, ignorado)")
            return False
        self._last_text, self._last_at = text, now

        self.out(f"tu> {text}")
        self._turn("user", text)
        self._status("a pensar")
        try:
            answer = self.agent.reply(text)
        except NoxError as exc:
            self.out(f"Erro: {exc}")
            return False
        self.out(f"{self.name}> {answer}")
        self._turn("assistant", answer)

        self._status("a falar")
        interrupted = self.speak(answer)
        if interrupted:
            # O utilizador está a falar: não deitar fora o que ele já disse nem
            # voltar a exigir a palavra de ativação.
            self._armed_at = time.monotonic()
            return True
        # O microfone encheu enquanto o Nox falava; deitar fora antes de voltar
        # a ouvir evita transcrever a própria resposta.
        self.source.flush()
        # Continua a ouvir para a réplica, sem exigir a palavra outra vez.
        if self.wake is not None and self.follow_up_s > 0:
            self._armed = True
            self._armed_at = time.monotonic()
            self._follow_up = True
            self._status("a ouvir")
        else:
            self._armed = False
            self._status("a ouvir" if self.wake is None else "a aguardar palavra")
        return True

    def speak(self, text: str) -> bool:
        """Fala por frases, sintetizando a seguinte enquanto a atual é reproduzida.

        A primeira frase chega ao altifalante sem esperar pela síntese do resto.
        Devolve True se o utilizador interrompeu.
        """
        sentences = split_sentences(text)
        if not sentences:
            return False
        rate = self.synthesizer.sample_rate
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.synthesizer.synthesize, sentences[0])
            for index in range(len(sentences)):
                audio = pending.result()
                if index + 1 < len(sentences):
                    pending = pool.submit(self.synthesizer.synthesize, sentences[index + 1])
                if not audio:
                    continue
                if self.barge_in and self._play_listening(audio, rate):
                    return True
                if not self.barge_in:
                    self.speaker.play(audio, rate)
        return False

    def _play_listening(self, audio: Pcm, rate: int) -> bool:
        """Reproduz enquanto escuta; devolve True se foi interrompido.

        O que dispara é fala sustentada acima de um limiar de energia — o VAD
        sozinho deixa passar o eco do próprio Nox. Com altifalantes o limiar
        não chega para distinguir as duas vozes: daí a flag estar desligada.
        """
        self.speaker.start(audio, rate)
        block_ms = round(self.block_frames * 1000 / self.segmenter.sample_rate)
        needed = max(1, self.barge_in_ms // max(block_ms, 1))
        consecutive = 0
        heard: list[Pcm] = []

        while self.speaker.is_playing():
            chunk = self.source.read(self.block_frames)
            if not chunk:
                break
            if self._is_barge_in(chunk):
                consecutive += 1
                heard.append(chunk)
                if consecutive >= needed:
                    self.speaker.stop()
                    self.out(f"{self.name}> (interrompido)")
                    # O início da frase do utilizador já foi lido: entra no
                    # segmentador para não se perder a primeira palavra.
                    for buffered in heard:
                        self.segmenter.feed(buffered)
                    return True
            else:
                consecutive = 0
                heard.clear()
        return False

    def _is_barge_in(self, chunk: Pcm) -> bool:
        return self.segmenter.vad.is_speech(chunk) and rms(chunk) >= self.barge_in_threshold

    def _turn(self, role: str, text: str) -> None:
        if self.on_turn is not None:
            self.on_turn(role, text)

    def _status(self, status: str) -> None:
        if self.on_status is not None:
            self.on_status(status)

    def _prepare_fillers(self) -> None:
        """Sintetiza as frases de espera uma única vez, no arranque.

        Em paralelo: com voz de rede, três pedidos em série custam três
        handshakes antes de o Nox começar a ouvir.
        """
        if not self.fillers:
            return
        with ThreadPoolExecutor(max_workers=len(self.fillers)) as pool:
            self._filler_audio = list(pool.map(self.synthesizer.synthesize, self.fillers))

    def _play_filler(self) -> None:
        if not self._filler_audio:
            return
        audio = self._filler_audio[self._filler_index % len(self._filler_audio)]
        self._filler_index += 1
        if audio:
            self.speaker.play(audio, self.synthesizer.sample_rate)


def build_source(config: Config, input_file: Path | None = None) -> AudioSource:
    settings = config.audio
    if input_file is not None:
        return WavSource(input_file, sample_rate=settings.sample_rate)
    return SoundDeviceSource(
        sample_rate=settings.sample_rate,
        block_ms=settings.block_ms,
        device=settings.input_device,
        fallback=settings.input_fallback,
    )


def build_vad(config: Config) -> VoiceActivityDetector:
    settings = config.audio.vad
    if settings.provider == "webrtc":
        return WebRtcVad(
            config.audio.sample_rate,
            aggressiveness=settings.aggressiveness,
            frame_ms=config.audio.block_ms,
        )
    if settings.provider == "silero":
        raise ModelError("vad.provider 'silero' ainda não está implementado; usa 'webrtc'")
    return EnergyVad()


def build_segmenter(config: Config) -> Segmenter:
    return Segmenter(
        build_vad(config),
        sample_rate=config.audio.sample_rate,
        silence_ms=config.audio.vad.silence_ms,
    )


def build_wake(
    config: Config, *, progress: Callable[[str], None] | None = None
) -> WakeWordDetector | None:
    """Detetor de wake word, ou None para o Nox ouvir sempre."""
    settings = config.wake
    if settings.provider == "off":
        return None
    if settings.provider == "vosk":
        from nox.models import ensure_vosk_model

        model = ensure_vosk_model(settings.model, progress=progress)
        profiles = []
        if config.wake.voiceprint:
            from nox.audio.voiceprint import load_profiles

            profiles = load_profiles()
        return VoskWakeWord(
            config.wake.phrases or [config.nox.wake_word],
            model_path=model,
            sample_rate=config.audio.sample_rate,
            noise_gate=config.audio.noise_gate,
            noise_gate_factor=config.audio.noise_gate_factor,
            denoise=config.audio.denoise_wake,
            profiles=profiles,
            voiceprint_threshold=config.wake.voiceprint_threshold,
            grammar=config.wake.grammar or None,
        )
    raise ModelError(f"wake.provider '{settings.provider}' desconhecido")


def run_voice(
    config: Config,
    *,
    out: Callable[[str], None],
    input_file: Path | None = None,
    use_wake: bool = True,
    agent: Agent | None = None,
    on_turn: Callable[[str, str], None] | None = None,
    on_status: Callable[[str], None] | None = None,
    on_frame: Callable[[list[float]], None] | None = None,
    on_input: Callable[[list[float]], None] | None = None,
    stop_event: Event | None = None,
) -> int:
    """Arranca o pipeline completo. Devolve o número de turnos."""
    try:
        source = build_source(config, input_file)
    except NoxError as exc:
        out(f"Erro: {exc}")
        return 2

    # Um ficheiro já é o pedido: não faz sentido exigir a palavra de ativação.
    wake = (
        build_wake(config, progress=lambda m: out(f"aviso: {m}"))
        if use_wake and input_file is None
        else None
    )

    try:
        loop = VoiceLoop(
            source=source,
            segmenter=build_segmenter(config),
            transcriber=build_transcriber(config),
            synthesizer=build_synthesizer(config, progress=lambda m: out(f"aviso: {m}")),
            speaker=SoundDeviceSpeaker(on_frame=on_frame),
            agent=agent or build_agent(config, voice=True),
            out=out,
            name=config.nox.name,
            fillers=FILLERS if config.nox.voice_fillers else (),
            min_rms=config.audio.min_speech_rms,
            wake=wake,
            wake_timeout_s=config.wake.timeout_s,
            follow_up_s=config.wake.follow_up_s,
            barge_in=config.audio.barge_in,
            barge_in_ms=config.audio.barge_in_ms,
            barge_in_threshold=config.audio.barge_in_threshold,
            on_turn=on_turn,
            on_status=on_status,
            stop_event=stop_event,
            block_frames=round(config.audio.sample_rate * config.audio.block_ms / 1000),
        )
        return loop.run()
    except (NoxError, AudioError) as exc:
        out(f"Erro: {exc}")
        return 2
    finally:
        source.close()
