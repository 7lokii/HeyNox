from array import array

import pytest

from nox.audio.types import Pcm, duration_ms, frame_count, rms, silence
from nox.audio.vad import EnergyVad, Segmenter

SAMPLE_RATE = 16000


def chunk(ms: int, amplitude: int) -> Pcm:
    frames = round(ms * SAMPLE_RATE / 1000)
    return Pcm(array("h", [amplitude] * frames).tobytes())


def test_silence_has_expected_duration() -> None:
    assert duration_ms(silence(100, SAMPLE_RATE), SAMPLE_RATE) == 100


def test_frame_count_and_duration() -> None:
    block = chunk(30, 1000)
    assert frame_count(block) == 480
    assert duration_ms(block, SAMPLE_RATE) == 30


def test_rms_of_silence_is_zero() -> None:
    assert rms(silence(50, SAMPLE_RATE)) == 0.0


def test_rms_of_tone_matches_amplitude() -> None:
    assert rms(chunk(10, 1000)) == pytest.approx(1000.0)


def test_energy_vad_separates_speech_from_silence() -> None:
    vad = EnergyVad(threshold=350.0)
    assert vad.is_speech(chunk(30, 2000)) is True
    assert vad.is_speech(chunk(30, 0)) is False


def test_segmenter_emits_after_silence() -> None:
    segmenter = Segmenter(EnergyVad(), sample_rate=SAMPLE_RATE)
    for _ in range(12):
        assert segmenter.feed(chunk(30, 2000)) is None

    result = None
    for _ in range(40):
        result = segmenter.feed(chunk(30, 0))
        if result is not None:
            break

    assert result is not None
    assert duration_ms(result, SAMPLE_RATE) >= 360


def test_segmenter_drops_short_blips() -> None:
    segmenter = Segmenter(EnergyVad(), sample_rate=SAMPLE_RATE)
    for _ in range(4):
        assert segmenter.feed(chunk(30, 2000)) is None
    for _ in range(40):
        assert segmenter.feed(chunk(30, 0)) is None


def test_segmenter_keeps_pre_roll() -> None:
    segmenter = Segmenter(EnergyVad(), sample_rate=SAMPLE_RATE, pre_roll_ms=300)
    for _ in range(3):
        segmenter.feed(chunk(30, 0))
    for _ in range(12):
        segmenter.feed(chunk(30, 2000))

    result = None
    for _ in range(40):
        result = segmenter.feed(chunk(30, 0))
        if result is not None:
            break

    assert result is not None
    assert duration_ms(result, SAMPLE_RATE) >= 450


def test_segmenter_caps_long_utterance() -> None:
    segmenter = Segmenter(EnergyVad(), sample_rate=SAMPLE_RATE, max_utterance_ms=300)
    results = [segmenter.feed(chunk(30, 2000)) for _ in range(10)]
    assert results[-1] is not None


def test_segmenter_flush_closes_open_utterance() -> None:
    segmenter = Segmenter(EnergyVad(), sample_rate=SAMPLE_RATE)
    for _ in range(12):
        segmenter.feed(chunk(30, 2000))
    assert segmenter.flush() is not None
    assert segmenter.flush() is None
