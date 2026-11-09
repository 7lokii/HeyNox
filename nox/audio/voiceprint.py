"""Impressão vocal: reconhecer quem fala.

Um perfil de voz é a média de vários embeddings WeSpeaker (ONNX, 256 dimensões)
calculados sobre amostras do utilizador. No arranque da wake word, a frase
detetada é comparada com o perfil por similaridade de cosseno.

Porque não MFCC: a média e o desvio de MFCC deram 0,989 de semelhança entre uma
voz masculina e uma feminina — mede o canal e o texto, não a pessoa.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from nox.audio.types import Pcm, resample
from nox.config import NoxError
from nox.models import ensure_speaker_model
from nox.paths import user_data_dir

SAMPLE_RATE = 16000
FRAME = 400  # 25 ms
HOP = 160  # 10 ms
N_FFT = 512
N_MELS = 80
MIN_FRAMES = 10


class VoiceprintError(NoxError):
    """O perfil de voz não pôde ser criado ou lido."""


def profile_path() -> Path:
    return user_data_dir() / "voiceprint.json"


def mel_filters(sample_rate: int = SAMPLE_RATE, n_mels: int = N_MELS) -> np.ndarray:
    def hz_to_mel(hz: float) -> float:
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def mel_to_hz(mel: np.ndarray) -> np.ndarray:
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    edges = np.linspace(hz_to_mel(20.0), hz_to_mel(sample_rate / 2), n_mels + 2)
    bins = np.floor((N_FFT + 1) * mel_to_hz(edges) / sample_rate).astype(int)
    filters = np.zeros((n_mels, N_FFT // 2 + 1))
    for index in range(1, n_mels + 1):
        left, centre, right = bins[index - 1], bins[index], bins[index + 1]
        for k in range(left, centre):
            filters[index - 1, k] = (k - left) / max(centre - left, 1)
        for k in range(centre, right):
            filters[index - 1, k] = (right - k) / max(right - centre, 1)
    return filters


def fbank(pcm: Pcm, sample_rate: int) -> np.ndarray | None:
    """80 filtros mel em escala logarítmica, com normalização por média."""
    if sample_rate != SAMPLE_RATE:
        pcm = resample(pcm, sample_rate, SAMPLE_RATE)
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if len(samples) < FRAME:
        return None

    count = 1 + (len(samples) - FRAME) // HOP
    offsets = np.arange(FRAME)[None, :] + HOP * np.arange(count)[:, None]
    window = np.hamming(FRAME).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(samples[offsets] * window, n=N_FFT, axis=1)) ** 2
    features = np.log(spectrum @ mel_filters().T + 1e-10).astype(np.float32)
    if len(features) < MIN_FRAMES:
        return None
    # Normalização por média (CMN): remove o canal, deixa a voz.
    return features - features.mean(axis=0, keepdims=True)


def embed(pcm: Pcm, sample_rate: int, *, session: object | None = None) -> np.ndarray | None:
    """Vetor de 256 dimensões que representa a voz, ou None se faltar áudio."""
    features = fbank(pcm, sample_rate)
    if features is None:
        return None
    runner = session or _session()
    output = runner.run(None, {"input_features": features[None, :, :]})[0][0]  # type: ignore[attr-defined]
    vector = np.asarray(output, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else None


_SESSION: object | None = None


def _session() -> object:
    global _SESSION
    if _SESSION is None:
        import onnxruntime as ort

        _SESSION = ort.InferenceSession(str(ensure_speaker_model()))
    return _SESSION


def similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Cosseno entre dois embeddings. 1.0 é a mesma voz."""
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator else 0.0


@dataclass
class VoiceProfile:
    embedding: list[float]
    samples: int

    @property
    def vector(self) -> np.ndarray:
        return np.asarray(self.embedding, dtype=np.float32)


def build_profile(clips: list[Pcm], sample_rate: int) -> VoiceProfile:
    vectors = [vector for clip in clips if (vector := embed(clip, sample_rate)) is not None]
    if not vectors:
        raise VoiceprintError("não consegui extrair voz das amostras: grava pelo menos 1 s de fala")
    mean = np.mean(vectors, axis=0)
    return VoiceProfile(embedding=(mean / np.linalg.norm(mean)).tolist(), samples=len(vectors))


def save_profile(profile: VoiceProfile, path: Path | None = None) -> Path:
    target = path or profile_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(profile)), encoding="utf-8")
    return target


def load_profile(path: Path | None = None) -> VoiceProfile | None:
    target = path or profile_path()
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return VoiceProfile(
            embedding=[float(value) for value in payload["embedding"]],
            samples=int(payload.get("samples", 1)),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise VoiceprintError(f"perfil de voz inválido em {target}: {exc}") from exc


def forget_profile(path: Path | None = None) -> bool:
    target = path or profile_path()
    if target.is_file():
        target.unlink()
        return True
    return False


def is_me(audio: Pcm, sample_rate: int, profile: VoiceProfile, *, threshold: float) -> bool:
    """True se a voz do áudio se parecer com o perfil acima do limiar."""
    vector = embed(audio, sample_rate)
    if vector is None:
        return False
    return similarity(vector, profile.vector) >= threshold
