from pathlib import Path

import numpy as np
import pytest

from nox.audio.types import Pcm, silence
from nox.audio.voiceprint import (
    VoiceProfile,
    add_profile,
    build_profile,
    embed,
    fbank,
    forget_profile,
    load_profiles,
    save_profiles,
    similarity,
)

pytest.importorskip("numpy")

SAMPLE_RATE = 16000


def test_fbank_needs_enough_audio() -> None:
    assert fbank(Pcm(b"\x00\x00" * 100), SAMPLE_RATE) is None


def test_fbank_returns_mel_bands() -> None:
    features = fbank(Pcm(silence(600, SAMPLE_RATE)), SAMPLE_RATE)
    assert features is not None
    assert features.shape[1] == 80


def test_profile_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "voz.json"
    save_profiles([VoiceProfile(embedding=[0.1, 0.2, 0.3], samples=2, name="rui")], path)

    loaded = load_profiles(path)
    assert len(loaded) == 1
    assert loaded[0].name == "rui"
    assert loaded[0].samples == 2
    assert loaded[0].embedding == pytest.approx([0.1, 0.2, 0.3])


def test_missing_profile_is_empty(tmp_path: Path) -> None:
    assert load_profiles(tmp_path / "nao.json") == []


def test_multiple_profiles_coexist(tmp_path: Path) -> None:
    path = tmp_path / "voz.json"
    add_profile(VoiceProfile(embedding=[1.0], samples=1, name="rui"), path)
    add_profile(VoiceProfile(embedding=[2.0], samples=1, name="ana"), path)

    assert [item.name for item in load_profiles(path)] == ["rui", "ana"]


def test_enrolling_the_same_name_replaces_it(tmp_path: Path) -> None:
    path = tmp_path / "voz.json"
    add_profile(VoiceProfile(embedding=[1.0], samples=1, name="rui"), path)
    add_profile(VoiceProfile(embedding=[3.0], samples=2, name="rui"), path)

    loaded = load_profiles(path)
    assert len(loaded) == 1
    assert loaded[0].samples == 2


def test_forget_one_or_all(tmp_path: Path) -> None:
    path = tmp_path / "voz.json"
    add_profile(VoiceProfile(embedding=[1.0], samples=1, name="rui"), path)
    add_profile(VoiceProfile(embedding=[2.0], samples=1, name="ana"), path)

    assert forget_profile("rui", path) == 1
    assert [item.name for item in load_profiles(path)] == ["ana"]
    assert forget_profile(None, path) == 1
    assert load_profiles(path) == []


def test_similarity_of_identical_vectors() -> None:
    vector = np.array([0.3, 0.4, 0.5], dtype=np.float32)
    assert similarity(vector, vector) == pytest.approx(1.0)


def test_build_profile_without_audio_fails() -> None:
    from nox.audio.voiceprint import VoiceprintError

    with pytest.raises(VoiceprintError, match="amostras"):
        build_profile([Pcm(b"\x00\x00" * 50)], SAMPLE_RATE)


@pytest.mark.skipif(
    not (Path.home() / "AppData/Local/HeyNox/models/wespeaker/model.onnx").is_file(),
    reason="modelo de locutor não instalado",
)
def test_embedding_is_normalised() -> None:
    vector = embed(Pcm(silence(800, SAMPLE_RATE)), SAMPLE_RATE)
    assert vector is not None
    assert float(np.linalg.norm(vector)) == pytest.approx(1.0, rel=1e-4)
