"""Deteção da wake word.

O contrato é incremental: cada bloco de áudio entra, um booleano sai. É assim
que o openWakeWord funciona e é assim que o microfone vai entregar os dados.

Não existe modelo openWakeWord treinado para "hey nox", por isso a deteção real
é feita com o Vosk: reconhecimento local contínuo e procura da palavra no texto.
"""

from __future__ import annotations

import json
import unicodedata
from collections import deque
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from nox.audio.denoise import NoiseGate, StreamingDenoiser
from nox.audio.types import Pcm
from nox.audio.vad import WebRtcVad
from nox.config import NoxError
from nox.models import ensure_vosk_model
from nox.optional import require

# Palavras de ativação que não distinguem nada: o reconhecedor pt transforma
# "hey" em "a"/"ei" e não vale a pena exigi-las.
_FILLER_WORDS = {"hey", "ei", "hei", "ola", "oi", "ok"}


class WakeWordError(NoxError):
    """A wake word não pôde ser configurada."""


class WakeWordDetector(Protocol):
    def process(self, chunk: Pcm) -> bool:
        """True quando a wake word terminou de ser dita neste bloco."""
        ...


class AlwaysAwake:
    """Modo texto e testes: não há wake word a validar."""

    def process(self, chunk: Pcm) -> bool:
        return True


class NeverWake:
    """Silencia a ativação por voz sem desligar o pipeline."""

    def process(self, chunk: Pcm) -> bool:
        return False


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return "".join(ch if ch.isalnum() else " " for ch in stripped).strip()


def wake_tokens(phrases: Sequence[str] | str) -> tuple[str, ...]:
    """Palavras que distinguem a ativação, sem "hey"/"ei"/"olá".

    "Nox", "Ei Nox" e "Hey Nox" dão todas o mesmo token: basta ouvir a palavra.
    """
    options = [phrases] if isinstance(phrases, str) else list(phrases)
    tokens = {
        word
        for phrase in options
        for word in normalize(phrase).split()
        if word not in _FILLER_WORDS
    }
    return tuple(sorted(tokens))


def matches(text: str, tokens: tuple[str, ...]) -> bool:
    """True se alguma palavra contiver um dos tokens.

    Comparação por substring de propósito: o reconhecedor pt escreve "Nox" como
    "inox", e uma distância de edição deixaria passar "no", que é comum demais.
    """
    words = normalize(text).split()
    return any(token in word for word in words for token in tokens)


class VoskWakeWord:
    """Wake word por reconhecimento contínuo.

    O Vosk custa ~25% de um núcleo a reconhecer, por isso só é alimentado
    enquanto o VAD ouve fala (com 1,5 s de tolerância, para não cortar a pausa
    entre "hey" e "nox").

    O reconhecedor de português escreve "Nox" como "inox" — é essa a forma que
    se procura, além da própria palavra.
    """

    def __init__(
        self,
        phrases: Sequence[str] | str = "hey nox",
        *,
        model_path: Path | str | None = None,
        sample_rate: int = 16000,
        hold_s: float = 1.5,
        noise_gate: bool = True,
        noise_gate_factor: float = 2.5,
        denoise: bool = True,
        denoise_floor: float = 250.0,
    ) -> None:
        if sample_rate != 16000:
            raise WakeWordError("a wake word por Vosk só funciona a 16 kHz")

        tokens = wake_tokens(phrases)
        if not tokens:
            raise WakeWordError(f"nenhuma de {phrases} tem palavras distintivas")

        require("vosk")
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        path = Path(model_path) if model_path else ensure_vosk_model()
        self._recognizer = KaldiRecognizer(Model(str(path)), sample_rate)
        self._tokens = tokens
        self._gate = WebRtcVad(sample_rate)
        self._noise = NoiseGate(factor=noise_gate_factor) if noise_gate else None
        self._denoiser = StreamingDenoiser(sample_rate) if denoise else None
        self._denoise_floor = denoise_floor
        self._sample_rate = sample_rate
        self._hold_s = hold_s
        # Contado em segundos de áudio, não em relógio: assim o detetor é
        # determinístico e testável sem esperar em tempo real.
        self._hold_left = 0.0
        self._idle = True
        # O Vosk precisa de contexto antes da palavra: sem este pré-roll ouvia
        # só a fala, sem o silêncio que a antecede, e não fechava a palavra.
        self._pre_roll: deque[Pcm] = deque(maxlen=max(1, round(hold_s * 1000 / 30)))

    def process(self, chunk: Pcm) -> bool:
        if self._denoiser is not None:
            # Corre sempre (para manter a estimativa de ruído fresca), mas só
            # substitui o áudio quando o ambiente é de facto ruidoso: em
            # silêncio, limpar estraga palavras curtas como "Nox".
            cleaned = self._denoiser.process(chunk)
            if self._noise is None or self._noise.floor > self._denoise_floor:
                chunk = cleaned
        duration = len(chunk) / 2 / self._sample_rate
        # O portão tem de ver todos os blocos para continuar a aprender o
        # ambiente, mesmo quando a resposta é "não".
        loud = self._noise is None or self._noise.is_open(chunk)
        speech = self._gate.is_speech(chunk)

        if loud or speech:
            if self._idle:
                # Primeiro bloco depois do silêncio: recuperar o contexto.
                for buffered in self._pre_roll:
                    self._recognizer.AcceptWaveform(buffered)
                self._pre_roll.clear()
            self._hold_left = self._hold_s
            self._idle = False
        elif self._hold_left > 0:
            self._hold_left -= duration
        else:
            # Fim do troço: uma palavra curta ("Nox") só aparece no resultado
            # final do Vosk, nunca no parcial. Sem este flush, perdia-se.
            if self._idle:
                self._pre_roll.append(chunk)
                return False
            self._idle = True
            return self._flush()

        if self._recognizer.AcceptWaveform(chunk):
            text = json.loads(self._recognizer.Result()).get("text", "")
        else:
            text = json.loads(self._recognizer.PartialResult()).get("partial", "")

        if self._matches(text):
            self._reset()
            return True
        return False

    def _flush(self) -> bool:
        text = json.loads(self._recognizer.FinalResult()).get("text", "")
        self._recognizer.Reset()
        if self._matches(text):
            self._reset()
            return True
        return False

    def _reset(self) -> None:
        self._recognizer.Reset()
        self._hold_left = 0.0
        self._idle = True
        self._pre_roll.clear()

    def _matches(self, text: str) -> bool:
        return matches(text, self._tokens)
