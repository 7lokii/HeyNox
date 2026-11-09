"""Captura de microfone via sounddevice (PortAudio).

Usa `RawInputStream` com callback e uma fila, não a API bloqueante: alguns
dispositivos — os Bluetooth em WDM-KS, por exemplo — recusam `read()` com
"Blocking API not supported yet". Com callback, funcionam.
"""

from __future__ import annotations

import queue
import time
from contextlib import suppress
from typing import Any

from nox.audio.devices import DevicePicker, match_input
from nox.audio.types import Pcm, resample
from nox.config import NoxError
from nox.optional import require

QUEUE_BLOCKS = 64


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
        fallback: str = "default",
    ) -> None:
        require("sounddevice")

        self.sample_rate = sample_rate
        self._frames = max(1, round(sample_rate * block_ms / 1000))
        self._picker = DevicePicker(device or "default", fallback)
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=QUEUE_BLOCKS)
        self._rate = sample_rate
        self.device_label = self._picker.label
        self._stream = self._open_best()

    def _open_best(self) -> Any:
        """Tenta o preferido, depois a omissão, depois o que o sistema der.

        Um headset Bluetooth pode estar ligado mas recusar-se a abrir (WDM-KS
        com o dispositivo ocupado). Nesse caso o Nox usa outra entrada em vez
        de ficar sem microfone.
        """
        candidates: list[int | None] = [self._picker.index]
        fallback_index = match_input(self._picker.fallback)
        if fallback_index not in candidates:
            candidates.append(fallback_index)
        if None not in candidates:
            candidates.append(None)

        last_error: AudioError | None = None
        for index in candidates:
            for rate in self._rates(index):
                try:
                    stream = self._open(index, rate)
                except AudioError as exc:
                    last_error = exc
                    continue
                self._rate = rate
                self.device_label = self._label_for(index)
                return stream

        raise last_error or AudioError("não há nenhum microfone disponível")

    def _rates(self, index: int | None) -> list[int]:
        rates = [self.sample_rate]
        if index is not None:
            import sounddevice as sd

            try:
                native = int(sd.query_devices(index)["default_samplerate"])
            except Exception:
                native = 0
            if native and native != self.sample_rate:
                rates.append(native)
        return rates

    def _label_for(self, index: int | None) -> str:
        if index is None:
            return "default"
        import sounddevice as sd

        try:
            return str(sd.query_devices(index)["name"])
        except Exception:
            return self._picker.label

    def _open(self, index: int | None, rate: int | None = None) -> Any:
        import sounddevice as sd

        rate = rate or self.sample_rate

        def callback(indata: bytes, frames: int, time_info: Any, status: Any) -> None:
            try:
                self._queue.put_nowait(bytes(indata))
            except queue.Full:
                # O consumidor está atrasado (o Nox a falar, por exemplo): deitar
                # fora o bloco mais antigo em vez de crescer sem limite.
                with suppress(queue.Empty):
                    self._queue.get_nowait()
                with suppress(queue.Full):
                    self._queue.put_nowait(bytes(indata))

        try:
            stream = sd.RawInputStream(
                samplerate=rate,
                channels=1,
                dtype="int16",
                blocksize=self._frames,
                device=index,
                callback=callback,
            )
            stream.start()
        except Exception as exc:  # PortAudioError e erros de driver
            raise AudioError(f"não consegui abrir o microfone: {exc}") from exc
        return stream

    def _recover(self) -> None:
        """O dispositivo pode ter desaparecido (Bluetooth). Volta a procurar."""
        with suppress(Exception):
            self._stream.stop()
        with suppress(Exception):
            self._stream.close()
        time.sleep(0.3)
        self._drain()
        self._stream = self._open_best()

    def _drain(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def read(self, frames: int) -> Pcm:
        try:
            return self._convert(self._queue.get(timeout=2.0))
        except queue.Empty:
            pass

        # Dois segundos sem dados: reabrir uma vez antes de desistir.
        self._recover()
        try:
            return self._convert(self._queue.get(timeout=2.0))
        except queue.Empty as exc:
            raise AudioError("o microfone parou de enviar áudio") from exc

    def _convert(self, data: bytes) -> Pcm:
        """O dispositivo pode correr a 8 kHz; o resto do Nox quer 16 kHz."""
        audio = Pcm(data)
        if self._rate != self.sample_rate:
            audio = resample(audio, self._rate, self.sample_rate)
        return audio

    def flush(self) -> None:
        """Deita fora o áudio acumulado — incluindo o que o Nox acabou de dizer."""
        self._drain()

    def close(self) -> None:
        with suppress(Exception):
            self._stream.stop()
        with suppress(Exception):
            self._stream.close()
