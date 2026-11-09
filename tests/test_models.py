import pytest

from nox.models import ModelError, voice_urls


def test_voice_urls_encode_non_ascii_names() -> None:
    model_url, config_url = voice_urls("pt_PT-tugão-medium")

    assert "tug%C3%A3o" in model_url
    assert model_url.endswith("pt_PT-tug%C3%A3o-medium.onnx")
    assert config_url.endswith("pt_PT-tug%C3%A3o-medium.onnx.json")
    assert "/pt/pt_PT/" in model_url


def test_voice_urls_handle_plain_names() -> None:
    model_url, _ = voice_urls("en_US-lessac-medium")
    assert model_url.endswith("en_US-lessac-medium.onnx")


@pytest.mark.parametrize("voice", ["tugao", "pt_PT", ""])
def test_invalid_voice_names_are_rejected(voice: str) -> None:
    with pytest.raises(ModelError, match="inválida"):
        voice_urls(voice)
