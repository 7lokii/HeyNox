import wave
from array import array

import pytest

from nox.audio.types import Pcm
from nox.audio.wav import WavError, read_wav, write_wav


def test_round_trip_keeps_samples(tmp_path) -> None:
    audio = Pcm(array("h", [100, -100] * 800).tobytes())
    path = write_wav(tmp_path / "a.wav", audio, 16000)

    read_back, rate = read_wav(path)
    assert rate == 16000
    assert read_back == audio


def test_write_creates_parent_directory(tmp_path) -> None:
    path = write_wav(tmp_path / "sub" / "dir" / "a.wav", Pcm(b"\x00\x00"), 16000)
    assert path.is_file()


def test_stereo_is_downmixed_to_mono(tmp_path) -> None:
    stereo = array("h", [100, 300] * 400)
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(stereo.tobytes())

    audio, rate = read_wav(path)
    assert rate == 16000
    assert set(array("h", audio)) == {200}


def test_eight_bit_wav_is_rejected(tmp_path) -> None:
    path = tmp_path / "8bit.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(8000)
        handle.writeframes(b"\x00" * 100)

    with pytest.raises(WavError, match="16 bits"):
        read_wav(path)


def test_missing_file_is_reported(tmp_path) -> None:
    with pytest.raises(WavError, match="não encontrado"):
        read_wav(tmp_path / "nao_existe.wav")


def test_non_wav_file_is_reported(tmp_path) -> None:
    path = tmp_path / "texto.wav"
    path.write_text("isto não é áudio", encoding="utf-8")
    with pytest.raises(WavError, match="WAV válido"):
        read_wav(path)
