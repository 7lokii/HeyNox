"""Redução de ruído e portão adaptativo.

Duas ferramentas com objetivos diferentes:

- `spectral_gate` limpa uma frase inteira antes do STT (subtração espectral).
- `NoiseGate` decide, bloco a bloco, se vale a pena acordar o reconhecedor —
  aprende o ruído de fundo e fecha-se quando o nível não se distingue dele.

Nenhuma usa `scipy`: só numpy, que já vem com o extra de áudio.
"""

from __future__ import annotations

import numpy as np

from nox.audio.types import Pcm, rms


def spectral_gate(
    pcm: Pcm,
    sample_rate: int,
    *,
    strength: float = 1.5,
    noise_percentile: float = 10.0,
    frame_ms: int = 32,
    floor: float = 0.08,
) -> Pcm:
    """Atenua o ruído estacionário por subtração espectral.

    Estima o ruído por banda como o percentil baixo da magnitude ao longo dos
    quadros — o que domina nos momentos em que ninguém fala — e subtrai-o.
    `floor` impede que os bins fiquem a zero e o som pareça "submarino".
    """
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    window = max(256, int(sample_rate * frame_ms / 1000))
    if len(samples) < window * 2:
        return pcm

    hop = window // 2
    count = 1 + (len(samples) - window) // hop
    offsets = np.arange(window)[None, :] + hop * np.arange(count)[:, None]
    hann = np.hanning(window).astype(np.float32)
    frames = samples[offsets] * hann

    spectrum = np.fft.rfft(frames, axis=1)
    magnitude = np.abs(spectrum)
    noise = np.percentile(magnitude, noise_percentile, axis=0)
    gain = np.clip(1.0 - strength * (noise / (magnitude + 1e-9)), floor, 1.0)

    cleaned = np.fft.irfft(spectrum * gain, n=window, axis=1) * hann
    output = np.zeros(len(samples), dtype=np.float32)
    weight = np.zeros(len(samples), dtype=np.float32)
    window_sq = hann * hann
    for index in range(count):
        start = index * hop
        output[start : start + window] += cleaned[index]
        weight[start : start + window] += window_sq
    # Nas pontas a soma dos quadros tende para zero: dividir por ela
    # amplificava o ruído em vez de o cortar.
    output /= np.maximum(weight, 0.1)

    return Pcm((np.clip(output, -1.0, 1.0) * 32767).astype(np.int16).tobytes())


class NoiseGate:
    """Portão adaptativo para a wake word.

    O piso de ruído desce depressa (para apanhar o silêncio real) e sobe devagar
    (para não ser enganado por uma frase). Um bloco só passa se estiver
    `factor` vezes acima desse piso.
    """

    def __init__(self, *, factor: float = 2.5, floor: float | None = None) -> None:
        self._factor = factor
        self._floor = floor

    @property
    def floor(self) -> float:
        return self._floor or 0.0

    def is_open(self, chunk: Pcm) -> bool:
        level = rms(chunk)
        if self._floor is None:
            # Primeiro bloco: é a melhor estimativa de ambiente que temos.
            self._floor = max(level, 1.0)
            return False

        if level < self._floor:
            # O ambiente baixou: seguir de imediato.
            self._floor = max(level, 1.0)
        elif level < self._floor * 1.6:
            # Perto do piso: é ambiente a subir devagar.
            self._floor += (level - self._floor) * 0.05
        # Muito acima do piso: é fala. O piso não se mexe.

        return level > self._floor * self._factor


class StreamingDenoiser:
    """Subtração espectral em fluxo, com sobreposição de 50%.

    O `spectral_gate` precisa da frase inteira; este trabalha bloco a bloco,
    com um bloco de atraso. É o que permite limpar o áudio antes do Vosk sem
    esperar que a pessoa acabe de falar.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        *,
        frame_ms: int = 60,
        strength: float = 1.5,
        learn: float = 0.02,
    ) -> None:
        self._frame = max(64, round(sample_rate * frame_ms / 1000))
        self._hop = self._frame // 2
        self._window = np.hanning(self._frame).astype(np.float32)
        self._noise: np.ndarray | None = None
        self._prev = np.zeros(self._hop, dtype=np.float32)
        self._tail = np.zeros(self._hop, dtype=np.float32)
        self._strength = strength
        self._learn = learn

    def process(self, chunk: Pcm) -> Pcm:
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        if len(samples) != self._hop:
            # Tamanho inesperado: devolver intacto é melhor do que partir o fluxo.
            return chunk

        frame = np.concatenate([self._prev, samples])
        self._prev = samples

        spectrum = np.fft.rfft(frame * self._window)
        magnitude = np.abs(spectrum)
        if self._noise is None:
            self._noise = magnitude.copy()

        gain = np.clip(1.0 - self._strength * self._noise / (magnitude + 1e-9), 0.1, 1.0)
        cleaned = np.fft.irfft(spectrum * gain, n=self._frame) * self._window

        output = cleaned[: self._hop] + self._tail
        self._tail = cleaned[self._hop :]

        # Só aprende ruído quando o quadro se parece com o ruído já conhecido.
        if float(np.mean(magnitude)) < float(np.mean(self._noise)) * 1.5:
            self._noise += (magnitude - self._noise) * self._learn

        # hann² sobreposto a 50% soma 0,75 (média 0,375 em cada metade).
        scaled = np.clip(output / 0.75, -1.0, 1.0)
        return Pcm((scaled * 32767).astype(np.int16).tobytes())
