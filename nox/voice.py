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

from nox.audio.mic import AudioError, SoundDeviceSource
from nox.audio.source import AudioSource, WavSource
from nox.audio.speaker import SoundDeviceSpeaker, Speaker
from nox.audio.types import Pcm
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
    _armed: bool = field(default=False, repr=False)
    _armed_at: float = field(default=0.0, repr=False)
    _filler_audio: list[Pcm] = field(default_factory=list, repr=False)
    _filler_index: int = field(default=0, repr=False)

    def run(self, *, max_turns: int | None = None) -> int:
        # Carregar modelos leva segundos; o microfone já encheu entretanto.
        self.source.flush()
        self._prepare_fillers()
        if self.wake is None:
            self.out("A ouvir. Fala à vontade; Ctrl+C para parar.")
        else:
            self.out("A aguardar a palavra de ativação. Ctrl+C para parar.")
        turns = 0
        try:
            while max_turns is None or turns < max_turns:
                outcome = self.step()
                if outcome is Step.END:
                    break
                if outcome is Step.TURN:
                    turns += 1
        except KeyboardInterrupt:
            self.out("")
        return turns

    def step(self) -> Step:
        """Lê um bloco de áudio e trata o turno, se a frase fechou."""
        chunk = self.source.read(self.block_frames)
        if not chunk:
            return Step.END

        if self.wake is not None and not self._armed:
            if self.wake.process(chunk):
                self._armed = True
                self._armed_at = time.monotonic()
                self.segmenter.reset()
                self.out(f"{self.name}> (pode falar)")
            return Step.IDLE

        if self._armed and time.monotonic() - self._armed_at > self.wake_timeout_s:
            self._armed = False
            self.segmenter.reset()
            self.out(f"{self.name}> (não ouvi nada)")
            return Step.IDLE

        utterance = self.segmenter.feed(chunk)
        if not utterance:
            return Step.IDLE
        return Step.TURN if self.handle(utterance) else Step.IDLE

    def handle(self, utterance: Pcm) -> bool:
        rate = self.segmenter.sample_rate
        # O filler toca enquanto o STT trabalha: cobre o silêncio sem lhe somar
        # tempo. Em série, o "Hmm." atrasava a transcrição em vez de a esconder.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.transcriber.transcribe, utterance, rate)
            self._play_filler()
            text = pending.result().strip()
        if not text:
            return False
        self.out(f"tu> {text}")
        try:
            answer = self.agent.reply(text)
        except NoxError as exc:
            self.out(f"Erro: {exc}")
            return False
        self.out(f"{self.name}> {answer}")

        self.speak(answer)
        # O microfone encheu enquanto o Nox falava; deitar fora antes de voltar
        # a ouvir evita transcrever a própria resposta.
        self.source.flush()
        self._armed = False
        return True

    def speak(self, text: str) -> None:
        """Fala por frases, sintetizando a seguinte enquanto a atual é reproduzida.

        A primeira frase chega ao altifalante sem esperar pela síntese do resto.
        """
        sentences = split_sentences(text)
        if not sentences:
            return
        rate = self.synthesizer.sample_rate
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.synthesizer.synthesize, sentences[0])
            for index in range(len(sentences)):
                audio = pending.result()
                if index + 1 < len(sentences):
                    pending = pool.submit(self.synthesizer.synthesize, sentences[index + 1])
                if audio:
                    self.speaker.play(audio, rate)

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
        return VoskWakeWord(
            config.nox.wake_word,
            model_path=model,
            sample_rate=config.audio.sample_rate,
        )
    raise ModelError(f"wake.provider '{settings.provider}' desconhecido")


def run_voice(
    config: Config,
    *,
    out: Callable[[str], None],
    input_file: Path | None = None,
    use_wake: bool = True,
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
            speaker=SoundDeviceSpeaker(),
            agent=build_agent(config, voice=True),
            out=out,
            name=config.nox.name,
            fillers=FILLERS if config.nox.voice_fillers else (),
            wake=wake,
            wake_timeout_s=config.wake.timeout_s,
            block_frames=round(config.audio.sample_rate * config.audio.block_ms / 1000),
        )
        return loop.run()
    except (NoxError, AudioError) as exc:
        out(f"Erro: {exc}")
        return 2
    finally:
        source.close()
