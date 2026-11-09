from array import array

import pytest

from nox.audio.levels import BANDS, MicMeter, band_energy, spectrum_frames
from nox.audio.types import Pcm, duration_ms, frame_count, rms, silence, trim_silence
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


def test_trim_silence_removes_the_padding() -> None:
    audio = Pcm(silence(600, SAMPLE_RATE) + chunk(300, 2000) + silence(600, SAMPLE_RATE))

    trimmed = trim_silence(audio, SAMPLE_RATE)

    assert 400 <= duration_ms(trimmed, SAMPLE_RATE) <= 560


def test_trim_silence_of_pure_silence_is_empty() -> None:
    assert trim_silence(silence(500, SAMPLE_RATE), SAMPLE_RATE) == b""


def test_spectrum_has_the_expected_shape() -> None:
    pytest.importorskip("numpy")
    frames = spectrum_frames(chunk(500, 2000), SAMPLE_RATE)

    assert frames
    assert len(frames[0]) == BANDS
    assert all(0.0 <= value <= 1.0 for frame in frames for value in frame)


def test_spectrum_of_silence_is_flat() -> None:
    pytest.importorskip("numpy")
    frames = spectrum_frames(silence(300, SAMPLE_RATE), SAMPLE_RATE)

    assert frames
    assert all(value == 0.0 for frame in frames for value in frame)


def test_spectrum_of_empty_audio_is_empty() -> None:
    pytest.importorskip("numpy")
    assert spectrum_frames(Pcm(b""), SAMPLE_RATE) == []


def test_band_energy_is_normalised() -> None:
    pytest.importorskip("numpy")
    values = band_energy(chunk(100, 3000), SAMPLE_RATE)

    assert len(values) == BANDS
    assert all(0.0 <= value <= 1.0 for value in values)
    assert max(values) > 0.5


def test_band_energy_of_silence_is_zero() -> None:
    pytest.importorskip("numpy")
    assert max(band_energy(silence(30, SAMPLE_RATE), SAMPLE_RATE)) == 0.0


def test_mic_meter_publishes_frames() -> None:
    pytest.importorskip("numpy")
    frames: list[list[float]] = []
    meter = MicMeter(SAMPLE_RATE, on_frame=frames.append)

    meter.process(chunk(30, 3000))

    assert len(frames) == 1
    assert max(frames[0]) > 0.3


def test_mic_meter_decays_on_silence() -> None:
    pytest.importorskip("numpy")
    meter = MicMeter(SAMPLE_RATE)
    for _ in range(6):
        meter.process(chunk(30, 3000))
    loud = max(meter.process(chunk(30, 3000)))

    quiet = loud
    for _ in range(10):
        quiet = max(meter.process(chunk(30, 0)))

    assert quiet < loud / 2
