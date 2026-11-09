"""Deteção da wake word.

O contrato é incremental: cada bloco de áudio entra, um booleano sai. É assim
que o openWakeWord funciona e é assim que o microfone vai entregar os dados.

Não existe modelo openWakeWord treinado para "hey nox", por isso a deteção real
é feita com o Vosk: reconhecimento local contínuo e procura da palavra no texto.
"""

from __future__ import annotations

import json
import time
import unicodedata
from pathlib import Path
from typing import Protocol

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
        phrase: str = "hey nox",
        *,
        model_path: Path | str | None = None,
        sample_rate: int = 16000,
        hold_s: float = 1.5,
    ) -> None:
        if sample_rate != 16000:
            raise WakeWordError("a wake word por Vosk só funciona a 16 kHz")

        tokens = [word for word in normalize(phrase).split() if word not in _FILLER_WORDS]
        if not tokens:
            raise WakeWordError(f"a frase '{phrase}' não tem palavras distintivas")

        require("vosk")
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        path = Path(model_path) if model_path else ensure_vosk_model()
        self._recognizer = KaldiRecognizer(Model(str(path)), sample_rate)
        self._tokens = tuple(tokens)
        self._gate = WebRtcVad(sample_rate)
        self._hold_s = hold_s
        self._hold_until = 0.0

    def process(self, chunk: Pcm) -> bool:
        now = time.monotonic()
        if self._gate.is_speech(chunk):
            self._hold_until = now + self._hold_s
        elif now > self._hold_until:
            return False

        if self._recognizer.AcceptWaveform(chunk):
            text = json.loads(self._recognizer.Result()).get("text", "")
        else:
            text = json.loads(self._recognizer.PartialResult()).get("partial", "")

        if self._matches(text):
            # Limpa o estado para a próxima ativação não herdar esta frase.
            self._recognizer.Reset()
            self._hold_until = 0.0
            return True
        return False

    def _matches(self, text: str) -> bool:
        return matches(text, self._tokens)
