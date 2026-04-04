from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable
from uuid import uuid4

from ..database import patch_job, upsert_job
from ..types import ExportArtifact, ExportPreset, JobDocument, JobStatus, ProjectDocument, ProjectStatus, TranscriptWord
from .captions import build_caption_lines
from .ffmpeg import configure_ffmpeg_runtime, probe_duration
from .projects import audio_dir, load_project, replace_project, to_public_url
from .rendering import render_export

WHISPER_CUDA_MODEL_SIZE = "large-v3"
WHISPER_CPU_PRIMARY_MODEL_SIZE = "medium"
WHISPER_CPU_FALLBACK_MODEL_SIZE = "small"
WHISPER_CUDA_BEAM_SIZE = 5
WHISPER_CPU_BEAM_SIZE = 4
WHISPER_VAD_PARAMETERS = {"min_silence_duration_ms": 500}
WHISPER_LANGUAGE_HINT = "ru"
LOW_CONFIDENCE_THRESHOLD = 0.55
LOW_DENSITY_WORDS_PER_SECOND = 0.85
JOB_HEARTBEAT_INTERVAL_SECONDS = 5.0
DEMUCS_MAX_CPU_JOBS = 4
_WHISPER_MODELS: dict[tuple[str, str, str], Any] = {}
_CUDA_AVAILABLE: bool | None = None
ProgressCallback = Callable[[float, str], None]


@dataclass(slots=True)
class TranscriptionCandidate:
    words: list[TranscriptWord]
    duration: float | None
    average_confidence: float
    words_per_second: float
    source: str
    language: str | None


class JobHeartbeat:
    def __init__(self, job_id: str, *, progress: float, message: str) -> None:
        self.job_id = job_id
        self._progress = progress
        self._message = message
        self._lock = Lock()
        self._stop_event = Event()
        self._thread = Thread(target=self._run, daemon=True)

    def start(self) -> "JobHeartbeat":
        self._thread.start()
        return self

    def update(self, *, progress: float | None = None, message: str | None = None) -> None:
        with self._lock:
            if progress is not None:
                self._progress = progress
            if message is not None:
                self._message = message

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=0.2)

    def _snapshot(self) -> tuple[float, str]:
        with self._lock:
            return self._progress, self._message

    def _run(self) -> None:
        while not self._stop_event.wait(JOB_HEARTBEAT_INTERVAL_SECONDS):
            progress, message = self._snapshot()
            try:
                _update_job(self.job_id, progress=progress, message=message)
            except KeyError:
                return


def start_pipeline_job(project: ProjectDocument, job: JobDocument) -> None:
    upsert_job(job)
    Thread(target=_run_pipeline, args=(project.id, job.id), daemon=True).start()


def start_export_job(project_id: str, job: JobDocument, preset: ExportPreset) -> None:
    upsert_job(job)
    Thread(target=_run_export, args=(project_id, job.id, preset), daemon=True).start()


def _run_pipeline(project_id: str, job_id: str) -> None:
    project = load_project(project_id)
    try:
        _update_job(job_id, status=JobStatus.running, progress=3, message="Preparing project")
        project.status = ProjectStatus.processing
        project.pipeline_job_id = job_id
        replace_project(project)

        _update_job(job_id, progress=14, message="Separating vocals with Demucs")
        demucs_heartbeat = JobHeartbeat(
            job_id,
            progress=14,
            message="Separating vocals with Demucs",
        ).start()
        try:
            vocal_path = separate_vocals(Path(project.source_audio_path), project_id)
        finally:
            demucs_heartbeat.stop()
        project.vocal_audio_path = str(vocal_path)
        project.vocal_audio_url = to_public_url(vocal_path)
        replace_project(project)

        _update_job(job_id, progress=52, message="Loading faster-whisper model")
        transcription_heartbeat = JobHeartbeat(
            job_id,
            progress=52,
            message="Loading faster-whisper model",
        ).start()

        def report_transcription_progress(progress: float, message: str) -> None:
            transcription_heartbeat.update(progress=progress, message=message)
            _update_job(job_id, progress=progress, message=message)

        try:
            words, duration = transcribe_audio(
                vocal_path,
                Path(project.source_audio_path),
                progress_callback=report_transcription_progress,
            )
        finally:
            transcription_heartbeat.stop()

        _update_job(job_id, progress=82, message="Grouping timed words into caption lines")
        project.transcript_words = words
        project.captions = build_caption_lines(words)
        project.audio_duration_seconds = duration or probe_duration(Path(project.source_audio_path))
        project.status = ProjectStatus.ready
        replace_project(project)

        _update_job(
            job_id,
            status=JobStatus.completed,
            progress=100,
            message="Project is ready for editing and export",
            result={"project_id": project.id},
        )
    except Exception as exc:
        project = load_project(project_id)
        project.status = ProjectStatus.failed
        project.errors.append(str(exc))
        replace_project(project)
        _update_job(
            job_id,
            status=JobStatus.failed,
            progress=100,
            message="Pipeline failed",
            error=str(exc),
        )


def _run_export(project_id: str, job_id: str, preset: ExportPreset) -> None:
    project = load_project(project_id)
    try:
        _update_job(job_id, status=JobStatus.running, progress=5, message=f"Rendering {preset.value}")
        project.status = ProjectStatus.exporting
        artifact = project.exports.get(preset.value) or ExportArtifact(preset=preset)
        artifact.status = JobStatus.running
        artifact.job_id = job_id
        artifact.output_url = None
        artifact.file_path = None
        project.exports[preset.value] = artifact
        replace_project(project)

        export_heartbeat = JobHeartbeat(
            job_id,
            progress=5,
            message=f"Rendering {preset.value}",
        ).start()
        try:
            project = render_export(project, preset)
        finally:
            export_heartbeat.stop()
        project.status = ProjectStatus.ready
        replace_project(project)
        _update_job(
            job_id,
            status=JobStatus.completed,
            progress=100,
            message=f"{preset.value} export is ready",
            result=project.exports[preset.value].model_dump(mode="json"),
        )
    except Exception as exc:
        project = load_project(project_id)
        project.status = ProjectStatus.failed
        artifact = project.exports.get(preset.value)
        if artifact:
            artifact.status = JobStatus.failed
        project.errors.append(str(exc))
        replace_project(project)
        _update_job(
            job_id,
            status=JobStatus.failed,
            progress=100,
            message=f"{preset.value} export failed",
            error=str(exc),
        )


def _update_job(
    job_id: str,
    *,
    status: JobStatus | None = None,
    progress: float | None = None,
    message: str | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    changes: dict[str, object] = {}
    if status is not None:
        changes["status"] = status
    if progress is not None:
        changes["progress"] = progress
    if message is not None:
        changes["message"] = message
    if result is not None:
        changes["result"] = result
    if error is not None:
        changes["error"] = error
    patch_job(job_id, **changes)


def _cuda_available() -> bool:
    global _CUDA_AVAILABLE
    if _CUDA_AVAILABLE is not None:
        return _CUDA_AVAILABLE

    try:
        import torch
    except Exception:
        _CUDA_AVAILABLE = False
        return _CUDA_AVAILABLE

    _CUDA_AVAILABLE = bool(torch.cuda.is_available())
    return _CUDA_AVAILABLE


def _cpu_parallelism() -> int:
    cpu_count = max(1, os.cpu_count() or 1)
    return max(1, min(DEMUCS_MAX_CPU_JOBS, cpu_count // 2 or 1))


def _find_vocal_stem(output_dir: Path) -> Path | None:
    return next(output_dir.rglob("vocals.*"), None)


def _build_demucs_command(source_audio: Path, output_dir: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "demucs.separate",
        "--two-stems=vocals",
        "-o",
        str(output_dir),
    ]
    if _cuda_available():
        command.extend(["-d", "cuda"])
    else:
        command.extend(["-d", "cpu", "-j", str(_cpu_parallelism())])
    command.append(str(source_audio))
    return command


def separate_vocals(source_audio: Path, project_id: str) -> Path:
    if importlib.util.find_spec("demucs") is None:
        raise RuntimeError(
            "demucs is not installed. Run backend/bootstrap.ps1 before processing audio."
        )

    configure_ffmpeg_runtime()
    output_dir = audio_dir(project_id) / "demucs"
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_vocal_file = _find_vocal_stem(output_dir)
    if existing_vocal_file is not None:
        return existing_vocal_file

    command = _build_demucs_command(source_audio, output_dir)
    completed = subprocess.run(command, capture_output=True, text=True, env=dict(os.environ))
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Demucs failed.")
    vocal_file = _find_vocal_stem(output_dir)
    if vocal_file is None:
        raise RuntimeError("Demucs finished without producing a vocals stem.")
    return vocal_file


def _score_transcription_candidate(candidate: TranscriptionCandidate) -> float:
    duration = max(candidate.duration or 0.0, 1.0)
    density_score = min(candidate.words_per_second / 2.0, 1.0) * 0.2
    confidence_score = candidate.average_confidence
    return confidence_score + density_score


def _should_retry_transcription(candidate: TranscriptionCandidate) -> bool:
    if not candidate.words:
        return True
    if candidate.average_confidence < LOW_CONFIDENCE_THRESHOLD:
        return True
    if candidate.duration and candidate.words_per_second < LOW_DENSITY_WORDS_PER_SECOND:
        return True
    return False


def _iter_transcription_settings() -> list[tuple[str, str, str, str | None]]:
    settings: list[tuple[str, str, str, str | None]] = []
    if _cuda_available():
        settings.extend(
            [
                ("cuda", "float16", WHISPER_CUDA_MODEL_SIZE, WHISPER_LANGUAGE_HINT),
                ("cuda", "float16", WHISPER_CUDA_MODEL_SIZE, None),
            ]
        )
    settings.extend(
        [
            ("cpu", "int8", WHISPER_CPU_PRIMARY_MODEL_SIZE, WHISPER_LANGUAGE_HINT),
            ("cpu", "int8", WHISPER_CPU_PRIMARY_MODEL_SIZE, None),
            ("cpu", "int8", WHISPER_CPU_FALLBACK_MODEL_SIZE, WHISPER_LANGUAGE_HINT),
            ("cpu", "int8", WHISPER_CPU_FALLBACK_MODEL_SIZE, None),
        ]
    )
    return settings


def _beam_size_for_device(device: str) -> int:
    if device == "cuda":
        return WHISPER_CUDA_BEAM_SIZE
    return WHISPER_CPU_BEAM_SIZE


def _transcription_message(source_label: str, model_size: str) -> str:
    return f"Transcribing {source_label} with faster-whisper ({model_size})"


def _transcribe_once(
    audio_path: Path,
    *,
    source_label: str,
    progress_callback: ProgressCallback | None = None,
    progress_range: tuple[float, float] = (52.0, 74.0),
) -> TranscriptionCandidate:
    if importlib.util.find_spec("faster_whisper") is None:
        raise RuntimeError(
            "faster-whisper is not installed. Run backend/bootstrap.ps1 before processing audio."
        )

    from faster_whisper import WhisperModel

    last_error: Exception | None = None
    range_start, range_end = progress_range
    for device, compute_type, model_size, language in _iter_transcription_settings():
        try:
            if progress_callback:
                progress_callback(
                    range_start,
                    f"Loading ASR model for {source_label} ({model_size}, {device})",
                )
            model = _WHISPER_MODELS.get((device, compute_type, model_size))
            if model is None:
                model = WhisperModel(model_size, device=device, compute_type=compute_type)
                _WHISPER_MODELS[(device, compute_type, model_size)] = model
            segments, info = model.transcribe(
                str(audio_path),
                beam_size=_beam_size_for_device(device),
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=WHISPER_VAD_PARAMETERS,
                language=language,
                condition_on_previous_text=False,
            )
            words: list[TranscriptWord] = []
            confidence_values: list[float] = []
            duration = info.duration
            last_reported_step = -1
            for segment in segments:
                if progress_callback and duration and duration > 0:
                    fraction = max(0.0, min(1.0, float(getattr(segment, "end", 0.0) or 0.0) / duration))
                    progress = range_start + (range_end - range_start) * fraction
                    progress_step = int(progress)
                    if progress_step > last_reported_step:
                        last_reported_step = progress_step
                        progress_callback(
                            progress,
                            _transcription_message(source_label, model_size),
                        )
                for word in segment.words or []:
                    cleaned = (word.word or "").strip()
                    if not cleaned:
                        continue
                    if word.probability is not None:
                        confidence_values.append(float(word.probability))
                    words.append(
                        TranscriptWord(
                            id=uuid4().hex,
                            text=cleaned,
                            start=round(word.start, 3),
                            end=round(word.end, 3),
                            confidence=round(word.probability, 4)
                            if word.probability is not None
                            else None,
                        )
                    )
            average_confidence = (
                sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
            )
            words_per_second = len(words) / max(duration or 0.0, 1.0)
            if progress_callback:
                progress_callback(range_end, _transcription_message(source_label, model_size))
            return TranscriptionCandidate(
                words=words,
                duration=duration,
                average_confidence=average_confidence,
                words_per_second=words_per_second,
                source=source_label,
                language=language or getattr(info, "language", None),
            )
        except Exception as exc:  # pragma: no cover
            last_error = exc
            continue
    raise RuntimeError(f"Whisper transcription failed on all devices: {last_error}")


def transcribe_audio(
    vocal_audio_path: Path,
    source_audio_path: Path | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[TranscriptWord], float | None]:
    vocal_candidate = _transcribe_once(
        vocal_audio_path,
        source_label="vocals",
        progress_callback=progress_callback,
        progress_range=(52.0, 74.0),
    )
    best_candidate = vocal_candidate

    if source_audio_path and source_audio_path != vocal_audio_path and _should_retry_transcription(vocal_candidate):
        source_candidate = _transcribe_once(
            source_audio_path,
            source_label="source",
            progress_callback=progress_callback,
            progress_range=(74.0, 82.0),
        )
        if _score_transcription_candidate(source_candidate) > _score_transcription_candidate(vocal_candidate):
            best_candidate = source_candidate

    return best_candidate.words, best_candidate.duration
