"""Loop de conversação por voz.

Microfone -> VAD/Segmenter -> STT -> Agent -> TTS -> altifalante.

Sem wake word: o Nox ouve sempre. A ativação por "Hey Nox" entra quando houver
modelo treinado; até lá, `--voice` é conversa contínua.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from nox.audio.mic import AudioError, SoundDeviceSource
from nox.audio.source import AudioSource, WavSource
from nox.audio.speaker import SoundDeviceSpeaker, Speaker
from nox.audio.types import Pcm
from nox.audio.vad import EnergyVad, Segmenter, VoiceActivityDetector, WebRtcVad
from nox.brain.agent import Agent, build_agent
from nox.config import Config, NoxError
from nox.models import ModelError
from nox.speech.stt import Transcriber, build_transcriber
from nox.speech.tts import Synthesizer, build_synthesizer


class Step(Enum):
    """Resultado de ler um bloco de áudio."""

    IDLE = auto()
    TURN = auto()
    END = auto()


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

    def run(self, *, max_turns: int | None = None) -> int:
        # Carregar modelos leva segundos; o microfone já encheu entretanto.
        self.source.flush()
        self.out("A ouvir. Fala à vontade; Ctrl+C para parar.")
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
        utterance = self.segmenter.feed(chunk)
        if not utterance:
            return Step.IDLE
        return Step.TURN if self.handle(utterance) else Step.IDLE

    def handle(self, utterance: Pcm) -> bool:
        text = self.transcriber.transcribe(utterance, self.segmenter.sample_rate).strip()
        if not text:
            return False
        self.out(f"tu> {text}")
        try:
            answer = self.agent.reply(text)
        except NoxError as exc:
            self.out(f"Erro: {exc}")
            return False
        self.out(f"{self.name}> {answer}")

        audio = self.synthesizer.synthesize(answer)
        if audio:
            self.speaker.play(audio, self.synthesizer.sample_rate)
        # O microfone encheu enquanto o Nox falava; deitar fora antes de voltar
        # a ouvir evita transcrever a própria resposta.
        self.source.flush()
        return True


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
    return Segmenter(build_vad(config), sample_rate=config.audio.sample_rate)


def run_voice(config: Config, *, out: Callable[[str], None], input_file: Path | None = None) -> int:
    """Arranca o pipeline completo. Devolve o número de turnos."""
    try:
        source = build_source(config, input_file)
    except NoxError as exc:
        out(f"Erro: {exc}")
        return 2

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
            block_frames=round(config.audio.sample_rate * config.audio.block_ms / 1000),
        )
        return loop.run()
    except (NoxError, AudioError) as exc:
        out(f"Erro: {exc}")
        return 2
    finally:
        source.close()
