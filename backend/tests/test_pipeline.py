from pathlib import Path

from backend.app.services.pipeline import (
    DEMUCS_MAX_CPU_JOBS,
    LOW_CONFIDENCE_WORD_RATIO_THRESHOLD,
    SUSPICIOUS_WORD_RATIO_THRESHOLD,
    WHISPER_CUDA_MODEL_SIZE,
    WHISPER_CPU_FALLBACK_MODEL_SIZE,
    WHISPER_CPU_PRIMARY_MODEL_SIZE,
    TranscriptionCandidate,
    _build_demucs_command,
    _cpu_parallelism,
    _iter_transcription_settings,
    _normalize_transcript_words,
    _run_demucs_in_process,
    _score_transcription_candidate,
    _should_retry_transcription,
    transcribe_audio,
)
from backend.app.types import TranscriptWord


def _candidate(
    *,
    confidence: float,
    words_per_second: float,
    source: str,
    low_confidence_ratio: float = 0.0,
    suspicious_word_ratio: float = 0.0,
) -> TranscriptionCandidate:
    return TranscriptionCandidate(
        words=[
            TranscriptWord(
                id="word-1",
                text="Привет",
                start=0.0,
                end=0.4,
                confidence=confidence,
            )
        ],
        duration=1.0,
        average_confidence=confidence,
        words_per_second=words_per_second,
        source=source,
        language="ru",
        low_confidence_ratio=low_confidence_ratio,
        suspicious_word_ratio=suspicious_word_ratio,
    )


def test_should_retry_transcription_for_low_confidence_or_sparse_words():
    assert _should_retry_transcription(_candidate(confidence=0.42, words_per_second=1.8, source="vocals")) is True
    assert _should_retry_transcription(_candidate(confidence=0.72, words_per_second=0.5, source="vocals")) is True
    assert _should_retry_transcription(_candidate(confidence=0.78, words_per_second=1.6, source="vocals")) is False


def test_should_retry_transcription_for_noisy_words():
    assert _should_retry_transcription(
        _candidate(
            confidence=0.73,
            words_per_second=1.4,
            source="vocals",
            low_confidence_ratio=LOW_CONFIDENCE_WORD_RATIO_THRESHOLD + 0.01,
        )
    ) is True
    assert _should_retry_transcription(
        _candidate(
            confidence=0.73,
            words_per_second=1.4,
            source="vocals",
            suspicious_word_ratio=SUSPICIOUS_WORD_RATIO_THRESHOLD + 0.01,
        )
    ) is True


def test_score_transcription_candidate_prefers_stronger_candidate():
    weak = _candidate(confidence=0.51, words_per_second=0.7, source="vocals")
    strong = _candidate(confidence=0.74, words_per_second=1.4, source="source")

    assert _score_transcription_candidate(strong) > _score_transcription_candidate(weak)


def test_iter_transcription_settings_skips_cuda_without_gpu(monkeypatch):
    monkeypatch.setattr("backend.app.services.pipeline._cuda_available", lambda: False)
    settings = _iter_transcription_settings()

    assert all(device == "cpu" for device, _, _, _ in settings)
    assert all(model_size != WHISPER_CUDA_MODEL_SIZE for device, _, model_size, _ in settings if device == "cpu")
    assert any(model_size == WHISPER_CPU_PRIMARY_MODEL_SIZE for device, _, model_size, _ in settings if device == "cpu")
    assert any(model_size == WHISPER_CPU_FALLBACK_MODEL_SIZE for device, _, model_size, _ in settings if device == "cpu")


def test_iter_transcription_settings_prefers_cuda_when_available(monkeypatch):
    monkeypatch.setattr("backend.app.services.pipeline._cuda_available", lambda: True)
    settings = _iter_transcription_settings()

    assert settings[0][0] == "cuda"
    assert settings[0][2] == WHISPER_CUDA_MODEL_SIZE


def test_build_demucs_command_uses_parallel_cpu_jobs(monkeypatch):
    monkeypatch.setattr("backend.app.services.pipeline._cuda_available", lambda: False)
    monkeypatch.setattr("backend.app.services.pipeline.os.cpu_count", lambda: 16)

    command = _build_demucs_command(Path("track.mp3"), Path("out"))

    assert command[1:4] == ["-m", "demucs.separate", "--two-stems=vocals"]
    assert "-d" in command
    assert command[command.index("-d") + 1] == "cpu"
    assert "-j" in command
    assert command[command.index("-j") + 1] == str(min(DEMUCS_MAX_CPU_JOBS, 8))


def test_cpu_parallelism_is_bounded(monkeypatch):
    monkeypatch.setattr("backend.app.services.pipeline.os.cpu_count", lambda: 3)

    assert _cpu_parallelism() == 1


def test_run_demucs_in_process_uses_cpu_options(monkeypatch):
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr("backend.app.services.pipeline._cuda_available", lambda: False)
    monkeypatch.setattr("backend.app.services.pipeline._cpu_parallelism", lambda: 3)
    monkeypatch.setattr("backend.app.services.pipeline.ensure_numpy_compat_aliases", lambda: captured.setdefault("alias", ["called"]))
    monkeypatch.setattr("backend.app.services.pipeline.ensure_standard_streams", lambda: __import__("contextlib").nullcontext())

    def fake_main(options: list[str]) -> None:
        captured["options"] = options

    import sys
    import types

    module = types.SimpleNamespace(main=fake_main)
    monkeypatch.setitem(sys.modules, "demucs.separate", module)

    _run_demucs_in_process(Path("track.mp3"), Path("out"))

    assert captured["options"] == [
        "--two-stems=vocals",
        "-o",
        "out",
        "-d",
        "cpu",
        "-j",
        "3",
        "track.mp3",
    ]
    assert captured["alias"] == ["called"]


def test_transcribe_audio_falls_back_to_source_when_vocals_are_weak(monkeypatch):
    vocal_candidate = _candidate(confidence=0.44, words_per_second=0.5, source="vocals")
    source_candidate = _candidate(confidence=0.81, words_per_second=1.6, source="source")

    def fake_transcribe_once(
        audio_path: Path,
        *,
        source_label: str,
        progress_callback=None,
        progress_range=(52.0, 74.0),
    ) -> TranscriptionCandidate:
        return vocal_candidate if source_label == "vocals" else source_candidate

    monkeypatch.setattr("backend.app.services.pipeline._transcribe_once", fake_transcribe_once)

    words, duration = transcribe_audio(Path("vocals.wav"), Path("source.mp3"))

    assert words == source_candidate.words
    assert duration == source_candidate.duration


def test_score_transcription_candidate_penalizes_suspicious_output():
    stable = _candidate(confidence=0.74, words_per_second=1.4, source="vocals")
    noisy = _candidate(
        confidence=0.74,
        words_per_second=1.4,
        source="vocals",
        low_confidence_ratio=0.35,
        suspicious_word_ratio=0.25,
    )

    assert _score_transcription_candidate(stable) > _score_transcription_candidate(noisy)


def test_normalize_transcript_words_merges_punctuation_and_skips_low_confidence_duplicates():
    words = [
        TranscriptWord(id="1", text="Привет", start=0.0, end=0.3, confidence=0.92),
        TranscriptWord(id="2", text=",", start=0.3, end=0.31, confidence=0.9),
        TranscriptWord(id="3", text="Привет", start=0.31, end=0.45, confidence=0.21),
        TranscriptWord(id="4", text="мир", start=0.46, end=0.8, confidence=0.88),
        TranscriptWord(id="5", text="!", start=0.8, end=0.82, confidence=0.86),
    ]

    normalized = _normalize_transcript_words(words)

    assert [word.text for word in normalized] == ["Привет,", "мир!"]


def test_transcribe_audio_falls_back_to_source_when_vocals_look_suspicious(monkeypatch):
    vocal_candidate = _candidate(
        confidence=0.74,
        words_per_second=1.3,
        source="vocals",
        suspicious_word_ratio=SUSPICIOUS_WORD_RATIO_THRESHOLD + 0.05,
    )
    source_candidate = _candidate(confidence=0.77, words_per_second=1.5, source="source")

    def fake_transcribe_once(
        audio_path: Path,
        *,
        source_label: str,
        progress_callback=None,
        progress_range=(52.0, 74.0),
    ) -> TranscriptionCandidate:
        return vocal_candidate if source_label == "vocals" else source_candidate

    monkeypatch.setattr("backend.app.services.pipeline._transcribe_once", fake_transcribe_once)

    words, duration = transcribe_audio(Path("vocals.wav"), Path("source.mp3"))

    assert words == source_candidate.words
    assert duration == source_candidate.duration
