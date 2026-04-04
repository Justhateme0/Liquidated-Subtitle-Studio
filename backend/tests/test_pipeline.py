from pathlib import Path

from backend.app.services.pipeline import (
    DEMUCS_MAX_CPU_JOBS,
    WHISPER_CUDA_MODEL_SIZE,
    WHISPER_CPU_FALLBACK_MODEL_SIZE,
    WHISPER_CPU_PRIMARY_MODEL_SIZE,
    TranscriptionCandidate,
    _build_demucs_command,
    _cpu_parallelism,
    _iter_transcription_settings,
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
    )


def test_should_retry_transcription_for_low_confidence_or_sparse_words():
    assert _should_retry_transcription(_candidate(confidence=0.42, words_per_second=1.8, source="vocals")) is True
    assert _should_retry_transcription(_candidate(confidence=0.72, words_per_second=0.5, source="vocals")) is True
    assert _should_retry_transcription(_candidate(confidence=0.78, words_per_second=1.6, source="vocals")) is False


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
