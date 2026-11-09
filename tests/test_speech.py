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


def test_stt_provider_openai_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    config = Config.model_validate({"stt": {"provider": "openai"}})
    with pytest.raises(ModelError, match="GROQ_API_KEY"):
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


def test_cloud_transcriber_needs_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    config = Config.model_validate({"stt": {"provider": "openai"}})
    with pytest.raises(ModelError, match="GROQ_API_KEY"):
        build_transcriber(config)


def test_multipart_payload_has_the_expected_parts() -> None:
    from nox.audio.types import silence
    from nox.speech.stt import _multipart

    payload = _multipart("XB", "whisper-large-v3-turbo", "pt", silence(200, 16000), 16000)

    assert b'name="model"' in payload
    assert b'name="language"' in payload
    assert b'filename="audio.wav"' in payload
    assert payload.startswith(b"--XB\r\n")
    assert payload.endswith(b"--XB--\r\n")


def test_multipart_carries_the_prompt() -> None:
    from nox.audio.types import silence
    from nox.speech.stt import _multipart

    prompt = "O assistente chama-se Nox. Hey Nox."
    payload = _multipart(
        "XB", "whisper-large-v3-turbo", "pt", silence(200, 16000), 16000, prompt=prompt
    )

    assert b'name="prompt"' in payload
    assert prompt.encode() in payload


def test_fallback_transcriber_uses_the_local_model() -> None:
    from nox.speech.stt import FallbackTranscriber

    class Broken:
        def transcribe(self, audio: bytes, sample_rate: int) -> str:
            raise ModelError("sem rede")

    class Fixed:
        def transcribe(self, audio: bytes, sample_rate: int) -> str:
            return "olá"

    errors: list[ModelError] = []
    transcriber = FallbackTranscriber(Broken(), Fixed(), on_fallback=errors.append)

    assert transcriber.transcribe(b"\x00\x00" * 160, 16000) == "olá"
    assert len(errors) == 1


def test_lazy_transcriber_builds_only_once() -> None:
    from nox.speech.stt import LazyTranscriber

    builds: list[int] = []

    class Fixed:
        def transcribe(self, audio: bytes, sample_rate: int) -> str:
            return "olá"

    def factory() -> Fixed:
        builds.append(1)
        return Fixed()

    transcriber = LazyTranscriber(factory)
    transcriber.transcribe(b"\x00\x00" * 160, 16000)
    transcriber.transcribe(b"\x00\x00" * 160, 16000)

    assert builds == [1]


def test_cloud_transcriber_falls_back_to_the_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from nox.speech.stt import FallbackTranscriber

    monkeypatch.setenv("GROQ_API_KEY", "chave-de-teste")
    config = Config.model_validate(
        {"stt": {"provider": "openai", "fallback_provider": "faster-whisper"}}
    )

    assert isinstance(build_transcriber(config), FallbackTranscriber)
