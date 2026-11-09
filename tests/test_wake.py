import pytest

from nox.audio.types import Pcm
from nox.audio.wake import AlwaysAwake, NeverWake, VoskWakeWord, WakeWordError, matches


def test_matches_accepts_the_recognizer_spelling() -> None:
    # O Vosk pt escreve "Nox" como "inox" — foi o que saiu nos testes reais.
    assert matches("a inox", ("nox",)) is True
    assert matches("hey nox", ("nox",)) is True
    assert matches("olá inox, que horas são", ("nox",)) is True


def test_matches_ignores_unrelated_speech() -> None:
    assert matches("bom dia", ("nox",)) is False
    assert matches("no", ("nox",)) is False
    assert matches("", ("nox",)) is False


def test_matches_is_case_and_accent_insensitive() -> None:
    assert matches("NÓX", ("nox",)) is True


def test_fake_detectors_are_predictable() -> None:
    chunk = Pcm(b"\x00\x00")
    assert AlwaysAwake().process(chunk) is True
    assert NeverWake().process(chunk) is False


def test_vosk_rejects_other_sample_rates() -> None:
    with pytest.raises(WakeWordError, match="16 kHz"):
        VoskWakeWord("hey nox", sample_rate=48000)


def test_vosk_rejects_phrases_without_content() -> None:
    with pytest.raises(WakeWordError, match="distintivas"):
        VoskWakeWord("hey", sample_rate=16000)
