import os

import pytest

from nox.audio.types import duration_ms, rms
from nox.brain.agent import normalize
from nox.config import Config
from nox.models import ModelError, piper_dir
from nox.speech.stt import build_transcriber
from nox.speech.tts import build_synthesizer, split_sentences

PIPER_MODEL = piper_dir() / "pt_PT-tugão-medium.onnx"


def test_unknown_tts_provider_is_reported() -> None:
    config = Config.model_validate({"tts": {"provider": "elevenlabs"}})
    with pytest.raises(ModelError, match="não está implementado"):
        build_synthesizer(config)


def test_unknown_stt_provider_is_reported() -> None:
    config = Config.model_validate({"stt": {"provider": "openai"}})
    with pytest.raises(ModelError, match="não está implementado"):
        build_transcriber(config)


@pytest.mark.skipif(not PIPER_MODEL.is_file(), reason="voz Piper não está instalada")
def test_piper_produces_audible_audio() -> None:
    synthesizer = build_synthesizer(Config())
    audio = synthesizer.synthesize("Bom dia. Eu sou o Nox.")

    assert synthesizer.sample_rate == 22050
    assert duration_ms(audio, synthesizer.sample_rate) > 500
    assert rms(audio) > 100


@pytest.mark.skipif(not PIPER_MODEL.is_file(), reason="voz Piper não está instalada")
def test_piper_returns_nothing_for_empty_text() -> None:
    assert build_synthesizer(Config()).synthesize("   ") == b""


@pytest.mark.skipif(
    not PIPER_MODEL.is_file() or os.environ.get("NOX_SLOW_TESTS") != "1",
    reason="precisa do modelo Whisper e de NOX_SLOW_TESTS=1",
)
def test_tts_to_stt_round_trip() -> None:
    """O teste que interessa: o que o Nox diz tem de voltar como texto.

    Compara palavras, não frases: o modelo troca "a ouvir" por "ouvindo" e
    escreve números em dígitos, mas o conteúdo tem de sobreviver.
    """
    synthesizer = build_synthesizer(Config())
    transcriber = build_transcriber(Config.model_validate({"stt": {"device": "cpu"}}))

    spoken = "O Nox está a ouvir muito bem."
    heard = transcriber.transcribe(synthesizer.synthesize(spoken), synthesizer.sample_rate).lower()

    assert "nox" in heard, f"o nome perdeu-se: {heard!r}"
    expected = set(normalize(spoken).split())
    got = set(normalize(heard).split())
    overlap = len(expected & got) / len(expected)
    assert overlap >= 0.6, f"ouvido: {heard!r} (sobreposição {overlap:.0%})"


def test_split_sentences_keeps_short_phrases_whole() -> None:
    assert split_sentences("Sou o Nox. Em que posso ajudar?") == [
        "Sou o Nox.",
        "Em que posso ajudar?",
    ]


def test_split_sentences_breaks_long_clauses() -> None:
    long_sentence = (
        "Isto é uma frase bastante longa, com várias orações, "
        "que não deve ser sintetizada de uma só vez porque demora."
    )
    parts = split_sentences(long_sentence, max_chars=40)
    assert len(parts) > 1
    assert all(len(part) <= 40 for part in parts)


def test_prompt_echo_is_detected() -> None:
    from nox.speech.stt import looks_hallucinated

    prompt = "O assistente chama-se Nox. Hey Nox."
    assert looks_hallucinated("O assistente chama-se Nox. Hey Nox.", prompt) is True
    assert (
        looks_hallucinated(
            "O O assistente chama-se. O O assistente chama-se. O O assistente chama-se.", prompt
        )
        is True
    )


def test_real_speech_is_not_flagged() -> None:
    from nox.speech.stt import looks_hallucinated

    prompt = "O assistente chama-se Nox. Hey Nox."
    assert looks_hallucinated("Que horas são?", prompt) is False
    assert looks_hallucinated("Abre o meu projeto.", prompt) is False
