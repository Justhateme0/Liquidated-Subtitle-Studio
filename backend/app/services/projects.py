from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from math import isclose
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from ..config import (
    ALLOWED_BACKGROUND_IMAGE_EXTENSIONS,
    ALLOWED_BACKGROUND_VIDEO_EXTENSIONS,
    FFMPEG_BIN,
    DEFAULT_CANVAS_WIDTH,
    PROJECTS_DIR,
)
from ..database import get_job, get_project_row, patch_job, upsert_project
from ..types import JobDocument, JobStatus, ProjectDocument, ProjectStatus, now_iso
from .ffmpeg import configure_ffmpeg_runtime, hidden_subprocess_kwargs

LEGACY_POSITION_X = DEFAULT_CANVAS_WIDTH / 2
LEGACY_POSITION_Y = 892.0
INTERRUPTED_PROCESSING_ERROR = "Processing was interrupted by backend restart. Run the track again."
INTERRUPTED_EXPORT_ERROR = "Export was interrupted by backend restart. Start export again."
STALE_PROCESSING_ERROR = "Processing stopped responding. Run the track again."
STALE_EXPORT_ERROR = "Export stopped responding. Start export again."
MISSING_PIPELINE_JOB_ERROR = "Processing job is missing. Run the track again."
MISSING_EXPORT_JOB_ERROR = "Export job is missing. Start export again."
JOB_STALE_SECONDS = 45


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def source_dir(project_id: str) -> Path:
    return project_dir(project_id) / "source"


def fonts_dir(project_id: str) -> Path:
    return project_dir(project_id) / "fonts"


def backgrounds_dir(project_id: str) -> Path:
    return project_dir(project_id) / "backgrounds"


def exports_dir(project_id: str) -> Path:
    return project_dir(project_id) / "exports"


def audio_dir(project_id: str) -> Path:
    return project_dir(project_id) / "audio"


def metadata_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def ensure_project_folders(project_id: str) -> None:
    for path in (
        project_dir(project_id),
        source_dir(project_id),
        fonts_dir(project_id),
        backgrounds_dir(project_id),
        exports_dir(project_id),
        audio_dir(project_id),
    ):
        path.mkdir(parents=True, exist_ok=True)


def to_public_url(path: Path) -> str:
    relative = path.resolve().relative_to(PROJECTS_DIR.parent.resolve())
    return "/storage/" + relative.as_posix()


def title_from_filename(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "Untitled track"


def create_project(filename: str, raw_bytes: bytes) -> ProjectDocument:
    project_id = uuid4().hex
    ensure_project_folders(project_id)

    extension = Path(filename).suffix.lower()
    audio_path = source_dir(project_id) / f"source{extension}"
    audio_path.write_bytes(raw_bytes)

    document = ProjectDocument(
        id=project_id,
        status=ProjectStatus.queued,
        title=title_from_filename(filename),
        source_audio_path=str(audio_path),
        source_audio_url=to_public_url(audio_path),
    )
    save_project(document)
    return document


def save_project(project: ProjectDocument) -> ProjectDocument:
    project.updated_at = now_iso()
    path = metadata_path(project.id)
    path.write_text(
        json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    upsert_project(project, path)
    return project


def migrate_legacy_caption_positions(project: ProjectDocument) -> bool:
    style_uses_legacy_position = isclose(project.style.position_x, LEGACY_POSITION_X, abs_tol=0.5) and isclose(
        project.style.position_y,
        LEGACY_POSITION_Y,
        abs_tol=0.5,
    )
    if not style_uses_legacy_position:
        return False

    captions_use_legacy_position = all(
        isclose(caption.position_x, LEGACY_POSITION_X, abs_tol=0.5)
        and isclose(caption.position_y, LEGACY_POSITION_Y, abs_tol=0.5)
        for caption in project.captions
    )
    if project.captions and not captions_use_legacy_position:
        return False

    center_x = project.style.canvas_width / 2
    center_y = project.style.canvas_height / 2
    project.style.position_x = center_x
    project.style.position_y = center_y
    for caption in project.captions:
        caption.position_x = center_x
        caption.position_y = center_y
    return True


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _append_error(project: ProjectDocument, message: str) -> bool:
    if not message or message in project.errors:
        return False
    project.errors.append(message)
    return True


def reconcile_job_runtime_state(job: JobDocument | None) -> JobDocument | None:
    if job is None or job.status not in {JobStatus.queued, JobStatus.running}:
        return job

    age_seconds = (datetime.now(timezone.utc) - _parse_iso(job.updated_at)).total_seconds()
    if age_seconds < JOB_STALE_SECONDS:
        return job

    reason = STALE_EXPORT_ERROR if job.kind == "export" else STALE_PROCESSING_ERROR
    return patch_job(
        job.id,
        status=JobStatus.failed,
        progress=100,
        message=reason,
        error=reason,
    )


def reconcile_project_runtime_state(project: ProjectDocument) -> bool:
    changed = False

    if project.status is ProjectStatus.processing:
        if not project.pipeline_job_id:
            next_status = ProjectStatus.ready if project.captions else ProjectStatus.failed
            if project.status is not next_status:
                project.status = next_status
                changed = True
            changed = _append_error(project, MISSING_PIPELINE_JOB_ERROR) or changed
        else:
            job = reconcile_job_runtime_state(get_job(project.pipeline_job_id))
            if job is None:
                next_status = ProjectStatus.ready if project.captions else ProjectStatus.failed
                if project.status is not next_status:
                    project.status = next_status
                    changed = True
                changed = _append_error(project, MISSING_PIPELINE_JOB_ERROR) or changed
            elif job.status is JobStatus.failed:
                next_status = ProjectStatus.ready if project.captions else ProjectStatus.failed
                if project.status is not next_status:
                    project.status = next_status
                    changed = True
                changed = _append_error(project, job.error or job.message or STALE_PROCESSING_ERROR) or changed
            elif job.status is JobStatus.completed:
                next_status = (
                    ProjectStatus.ready if (project.transcript_words or project.captions) else ProjectStatus.failed
                )
                if project.status is not next_status:
                    project.status = next_status
                    changed = True
                if project.status is ProjectStatus.failed:
                    changed = _append_error(project, "Pipeline finished without captions. Run the track again.") or changed

    if project.status is ProjectStatus.exporting:
        has_active_export = False
        for artifact in project.exports.values():
            if not artifact.job_id:
                if artifact.status in {JobStatus.queued, JobStatus.running}:
                    artifact.status = JobStatus.failed
                    changed = True
                changed = _append_error(project, MISSING_EXPORT_JOB_ERROR) or changed
                continue

            job = reconcile_job_runtime_state(get_job(artifact.job_id))
            if job is None:
                if artifact.status is not JobStatus.failed:
                    artifact.status = JobStatus.failed
                    changed = True
                changed = _append_error(project, MISSING_EXPORT_JOB_ERROR) or changed
                continue

            if artifact.status is not job.status:
                artifact.status = job.status
                changed = True

            if job.status in {JobStatus.queued, JobStatus.running}:
                has_active_export = True
            elif job.status is JobStatus.failed:
                changed = _append_error(project, job.error or job.message or STALE_EXPORT_ERROR) or changed

        if not has_active_export:
            next_status = ProjectStatus.ready if project.captions else ProjectStatus.failed
            if project.status is not next_status:
                project.status = next_status
                changed = True

    return changed


def load_project(project_id: str) -> ProjectDocument:
    path = metadata_path(project_id)
    if path.exists():
        project = ProjectDocument.model_validate_json(path.read_text(encoding="utf-8"))
        changed = migrate_legacy_caption_positions(project)
        changed = reconcile_project_runtime_state(project) or changed
        if changed:
            save_project(project)
        return project

    row = get_project_row(project_id)
    if row is None:
        raise FileNotFoundError(f"Project {project_id} was not found")
    raise FileNotFoundError(
        f"Project {project_id} exists in the database but the JSON snapshot is missing"
    )


def replace_project(project: ProjectDocument) -> ProjectDocument:
    return save_project(project)


def recover_interrupted_projects() -> int:
    recovered = 0
    for path in PROJECTS_DIR.glob("*/project.json"):
        project = ProjectDocument.model_validate_json(path.read_text(encoding="utf-8"))
        changed = False

        if project.status is ProjectStatus.processing:
            project.status = ProjectStatus.ready if project.captions else ProjectStatus.failed
            if INTERRUPTED_PROCESSING_ERROR not in project.errors:
                project.errors.append(INTERRUPTED_PROCESSING_ERROR)
            changed = True

        if project.status is ProjectStatus.exporting:
            project.status = ProjectStatus.ready if project.captions else ProjectStatus.failed
            if INTERRUPTED_EXPORT_ERROR not in project.errors:
                project.errors.append(INTERRUPTED_EXPORT_ERROR)
            for artifact in project.exports.values():
                if artifact.status in {JobStatus.queued, JobStatus.running}:
                    artifact.status = JobStatus.failed
            changed = True

        if changed:
            save_project(project)
            recovered += 1

    return recovered


def store_font(project_id: str, filename: str, payload: bytes) -> tuple[str, str]:
    destination = fonts_dir(project_id) / f"{uuid4().hex}{Path(filename).suffix.lower()}"
    destination.write_bytes(payload)
    return str(destination), to_public_url(destination)


def store_background(project_id: str, filename: str, payload: bytes) -> tuple[str, str, str]:
    extension = Path(filename).suffix.lower()
    background_folder = backgrounds_dir(project_id)
    background_folder.mkdir(parents=True, exist_ok=True)

    if extension in ALLOWED_BACKGROUND_IMAGE_EXTENSIONS:
        destination = background_folder / f"{uuid4().hex}{extension}"
        destination.write_bytes(payload)
        kind = "image"
    elif extension in ALLOWED_BACKGROUND_VIDEO_EXTENSIONS:
        configure_ffmpeg_runtime()
        with NamedTemporaryFile(delete=False, suffix=extension, dir=background_folder) as temp_file:
            temp_file.write(payload)
            temp_input = Path(temp_file.name)

        destination = background_folder / f"{uuid4().hex}.mp4"
        try:
            completed = subprocess.run(
                [
                    str(FFMPEG_BIN),
                    "-y",
                    "-i",
                    str(temp_input),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(destination),
                ],
                capture_output=True,
                text=True,
                env=dict(os.environ),
                **hidden_subprocess_kwargs(),
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    completed.stderr.strip() or completed.stdout.strip() or "Background video conversion failed."
                )
        finally:
            temp_input.unlink(missing_ok=True)
        kind = "video"
    else:
        raise ValueError(f"Unsupported background file type: {extension}")

    return str(destination), to_public_url(destination), kind
