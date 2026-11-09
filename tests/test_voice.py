from array import array

from nox.audio.source import FakeSource
from nox.audio.types import Pcm
from nox.audio.vad import EnergyVad, Segmenter
from nox.brain.agent import Agent
from nox.brain.llm import EchoLlm
from nox.speech.stt import ScriptedTranscriber
from nox.voice import Step, VoiceLoop

RATE = 16000


def block(ms: int, amplitude: int) -> Pcm:
    frames = round(RATE * ms / 1000)
    return Pcm(array("h", [amplitude] * frames).tobytes())


class RecordingSpeaker:
    def __init__(self) -> None:
        self.played: list[tuple[int, int]] = []

    def play(self, audio: Pcm, sample_rate: int) -> None:
        self.played.append((len(audio), sample_rate))

    def stop(self) -> None:
        return None


class RecordingSynthesizer:
    sample_rate = 16000

    def __init__(self) -> None:
        self.texts: list[str] = []

    def synthesize(self, text: str) -> Pcm:
        self.texts.append(text)
        return block(10, 1000)


class FlushingSource(FakeSource):
    """Conta os flush: o loop tem de limpar o buffer ao arrancar e após falar."""

    def __init__(self, chunks: list[Pcm]) -> None:
        super().__init__(chunks, sample_rate=RATE)
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1


def build_loop(
    chunks: list[Pcm],
    phrases: tuple[str, ...] = ("olá",),
    source: FakeSource | None = None,
) -> tuple[VoiceLoop, list[str], RecordingSpeaker, RecordingSynthesizer]:
    lines: list[str] = []
    speaker = RecordingSpeaker()
    synthesizer = RecordingSynthesizer()
    loop = VoiceLoop(
        source=source or FakeSource(chunks, sample_rate=RATE),
        segmenter=Segmenter(EnergyVad(), sample_rate=RATE),
        transcriber=ScriptedTranscriber(phrases),
        synthesizer=synthesizer,
        speaker=speaker,
        agent=Agent(EchoLlm()),
        out=lines.append,
        name="Nox",
        block_frames=480,
    )
    return loop, lines, speaker, synthesizer


def speech_then_silence() -> list[Pcm]:
    return [block(30, 2000) for _ in range(12)] + [block(30, 0) for _ in range(30)]


def test_loop_answers_one_turn() -> None:
    loop, lines, speaker, synthesizer = build_loop(speech_then_silence())

    assert loop.run(max_turns=1) == 1
    assert "tu> olá" in lines
    assert "Nox> (eco) olá" in lines
    assert synthesizer.texts == ["(eco) olá"]
    assert len(speaker.played) == 1


def test_loop_stops_when_source_ends() -> None:
    loop, lines, _, _ = build_loop([block(30, 0) for _ in range(5)])

    assert loop.run() == 0
    assert lines[0].startswith("A ouvir")


def test_silence_alone_never_produces_a_turn() -> None:
    loop, _, speaker, _ = build_loop([block(30, 0) for _ in range(40)])

    assert loop.run() == 0
    assert speaker.played == []


def test_empty_transcription_does_not_speak() -> None:
    loop, lines, speaker, _ = build_loop(speech_then_silence(), phrases=())

    assert loop.run() == 0
    assert speaker.played == []
    assert not any(line.startswith("tu>") for line in lines)


def test_loop_clears_the_microphone_buffer() -> None:
    source = FlushingSource(speech_then_silence())
    loop, _, _, _ = build_loop([], source=source)

    loop.run(max_turns=1)

    # Uma vez ao arrancar (modelos a carregar) e outra depois de falar.
    assert source.flushes == 2


def test_step_reports_end_of_stream() -> None:
    loop, _, _, _ = build_loop([])
    assert loop.step() is Step.END


def test_speak_sends_each_sentence_to_the_synthesizer() -> None:
    loop, _, speaker, synthesizer = build_loop([])

    loop.speak("Um. Dois. Três.")

    assert synthesizer.texts == ["Um.", "Dois.", "Três."]
    assert len(speaker.played) == 3


def test_speak_does_nothing_for_empty_text() -> None:
    loop, _, speaker, synthesizer = build_loop([])

    loop.speak("   ")

    assert synthesizer.texts == []
    assert speaker.played == []


def test_fillers_cover_the_wait_before_the_answer() -> None:
    loop, _, speaker, synthesizer = build_loop(speech_then_silence())
    loop.fillers = ("Hmm.",)

    loop.run(max_turns=1)

    assert synthesizer.texts[0] == "Hmm."
    assert "(eco) olá" in synthesizer.texts
    assert len(speaker.played) == 2


def test_no_fillers_means_no_extra_speech() -> None:
    loop, _, speaker, synthesizer = build_loop(speech_then_silence())

    loop.run(max_turns=1)

    assert synthesizer.texts == ["(eco) olá"]
    assert len(speaker.played) == 1
