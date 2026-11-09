"""Captura de microfone via sounddevice (PortAudio)."""

from __future__ import annotations

from nox.audio.types import Pcm
from nox.config import NoxError
from nox.optional import require


class AudioError(NoxError):
    """O microfone não abriu, desapareceu ou devolveu erro."""


class SoundDeviceSource:
    """Entrega blocos de PCM 16 bits mono, na taxa pedida."""

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        block_ms: int = 30,
        device: str | None = None,
    ) -> None:
        require("sounddevice")
        import sounddevice as sd

        self.sample_rate = sample_rate
        self._frames = max(1, round(sample_rate * block_ms / 1000))
        try:
            self._stream = sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._frames,
                device=None if device in (None, "", "default") else device,
            )
            self._stream.start()
        except Exception as exc:  # PortAudioError e erros de driver
            raise AudioError(f"não consegui abrir o microfone: {exc}") from exc

    def read(self, frames: int) -> Pcm:
        try:
            data, _overflowed = self._stream.read(frames)
        except Exception as exc:
            raise AudioError(f"falha a ler do microfone: {exc}") from exc
        return Pcm(data.tobytes())

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


def list_input_devices() -> list[tuple[int, str]]:
    """Pares (índice, nome) dos dispositivos de entrada. Para diagnóstico."""
    require("sounddevice")
    import sounddevice as sd

    devices = sd.query_devices()
    return [
        (index, item["name"])
        for index, item in enumerate(devices)
        if item["max_input_channels"] > 0
    ]
