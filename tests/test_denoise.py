import numpy as np
import pytest

from nox.audio.denoise import NoiseGate, StreamingDenoiser, spectral_gate
from nox.audio.types import Pcm, rms, silence

pytest.importorskip("numpy")

SAMPLE_RATE = 16000


def tone(ms: int, amplitude: int = 4000) -> Pcm:
    frames = round(SAMPLE_RATE * ms / 1000)
    wave = np.sin(np.linspace(0, 60 * np.pi, frames)) * amplitude
    return Pcm(wave.astype(np.int16).tobytes())


def noisy(audio: Pcm, level: float, seed: int = 1) -> Pcm:
    rng = np.random.default_rng(seed)
    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
    mixed = samples + rng.normal(0, level, len(samples)).astype(np.float32)
    return Pcm(np.clip(mixed, -32768, 32767).astype(np.int16).tobytes())


def test_spectral_gate_cuts_noise_in_silence() -> None:
    audio = noisy(Pcm(silence(600, SAMPLE_RATE) + tone(600)), level=800)

    cleaned = spectral_gate(audio, SAMPLE_RATE)
    window = 500 * SAMPLE_RATE // 1000 * 2

    assert rms(Pcm(cleaned[:window])) < rms(Pcm(audio[:window])) * 0.75


def test_spectral_gate_keeps_the_speech() -> None:
    audio = noisy(Pcm(silence(400, SAMPLE_RATE) + tone(600)), level=300)

    cleaned = spectral_gate(audio, SAMPLE_RATE)
    start = 450 * SAMPLE_RATE // 1000 * 2
    end = start + 400 * SAMPLE_RATE // 1000 * 2

    assert rms(Pcm(cleaned[start:end])) > rms(Pcm(audio[start:end])) * 0.6


def test_spectral_gate_ignores_short_audio() -> None:
    audio = tone(20)
    assert spectral_gate(audio, SAMPLE_RATE) == audio


def test_noise_gate_closes_on_steady_noise_and_opens_on_speech() -> None:
    gate = NoiseGate(factor=2.5)
    quiet = Pcm(np.full(480, 40, dtype=np.int16).tobytes())
    loud = Pcm(np.full(480, 3000, dtype=np.int16).tobytes())

    assert gate.is_open(quiet) is False  # primeiro bloco define o piso
    assert gate.is_open(quiet) is False
    assert gate.is_open(loud) is True
    assert gate.is_open(quiet) is False


def test_noise_gate_follows_a_quieter_room() -> None:
    gate = NoiseGate(factor=2.5)
    for level in (400, 400):
        gate.is_open(Pcm(np.full(480, level, dtype=np.int16).tobytes()))

    quieter = Pcm(np.full(480, 100, dtype=np.int16).tobytes())
    assert gate.is_open(quieter) is False
    assert gate.floor < 200


def test_streaming_denoiser_keeps_the_level() -> None:
    # O primeiro quadro tem de ser silêncio: é dele que sai a estimativa de
    # ruído. Sem isso o denoiser trataria o próprio tom como ruído.
    audio = Pcm(silence(300, SAMPLE_RATE) + tone(500))
    denoiser = StreamingDenoiser(SAMPLE_RATE)
    output = b"".join(
        denoiser.process(Pcm(audio[index : index + 960])) for index in range(0, len(audio), 960)
    )

    start = 320 * SAMPLE_RATE // 1000 * 2
    assert rms(Pcm(output[start:])) == pytest.approx(rms(Pcm(audio[start:])), rel=0.25)


def test_streaming_denoiser_cuts_steady_noise() -> None:
    audio = noisy(Pcm(silence(400, SAMPLE_RATE) + tone(400)), level=800)
    denoiser = StreamingDenoiser(SAMPLE_RATE)
    output = b"".join(
        denoiser.process(Pcm(audio[index : index + 960])) for index in range(0, len(audio), 960)
    )

    window = 300 * SAMPLE_RATE // 1000 * 2
    assert rms(Pcm(output[:window])) < rms(Pcm(audio[:window])) * 0.6


def test_streaming_denoiser_passes_odd_sized_chunks_through() -> None:
    denoiser = StreamingDenoiser(SAMPLE_RATE)
    chunk = tone(10)
    assert denoiser.process(chunk) == chunk
