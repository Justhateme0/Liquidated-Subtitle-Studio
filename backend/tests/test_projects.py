from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.services.projects import (
    INTERRUPTED_PROCESSING_ERROR,
    JOB_STALE_SECONDS,
    STALE_PROCESSING_ERROR,
    load_project,
    migrate_legacy_caption_positions,
    reconcile_job_runtime_state,
    recover_interrupted_projects,
    store_background,
)
from backend.app.types import CaptionLine, JobDocument, JobStatus, ProjectDocument, ProjectStatus, RenderStyle


def test_migrate_legacy_caption_positions_moves_old_layout_to_center():
    project = ProjectDocument(
        id="project-1",
        title="Track",
        source_audio_path="source.mp3",
        source_audio_url="/storage/source.mp3",
        captions=[
            CaptionLine(
                id="caption-1",
                text="line",
                start=0.0,
                end=1.0,
                position_x=540.0,
                position_y=892.0,
            )
        ],
        style=RenderStyle(position_x=540.0, position_y=892.0),
    )

    changed = migrate_legacy_caption_positions(project)

    assert changed is True
    assert project.style.position_x == 540.0
    assert project.style.position_y == 540.0
    assert project.captions[0].position_x == 540.0
    assert project.captions[0].position_y == 540.0


def test_recover_interrupted_projects_marks_processing_project_failed(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "project-1"
    project_dir.mkdir(parents=True)
    project_path = project_dir / "project.json"
    project = ProjectDocument(
        id="project-1",
        title="Track",
        source_audio_path="source.mp3",
        source_audio_url="/storage/source.mp3",
        status=ProjectStatus.processing,
    )
    project_path.write_text(project.model_dump_json(indent=2), encoding="utf-8")

    monkeypatch.setattr("backend.app.services.projects.PROJECTS_DIR", projects_dir)

    recovered = recover_interrupted_projects()
    recovered_project = ProjectDocument.model_validate_json(project_path.read_text(encoding="utf-8"))

    assert recovered == 1
    assert recovered_project.status == ProjectStatus.failed
    assert INTERRUPTED_PROCESSING_ERROR in recovered_project.errors


def test_reconcile_job_runtime_state_marks_stale_running_job_failed(monkeypatch):
    stale_timestamp = (
        datetime.now(timezone.utc) - timedelta(seconds=JOB_STALE_SECONDS + 5)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    job = JobDocument(
        id="job-1",
        project_id="project-1",
        kind="pipeline",
        status=JobStatus.running,
        updated_at=stale_timestamp,
    )

    def fake_patch_job(job_id: str, **changes: object) -> JobDocument:
        assert job_id == "job-1"
        payload = job.model_dump()
        payload.update(changes)
        return JobDocument(**payload)

    monkeypatch.setattr("backend.app.services.projects.patch_job", fake_patch_job)

    resolved = reconcile_job_runtime_state(job)

    assert resolved is not None
    assert resolved.status == JobStatus.failed
    assert resolved.error == STALE_PROCESSING_ERROR
    assert resolved.message == STALE_PROCESSING_ERROR


def test_load_project_marks_stale_pipeline_failed(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "project-1"
    project_dir.mkdir(parents=True)
    project_path = project_dir / "project.json"
    project = ProjectDocument(
        id="project-1",
        title="Track",
        source_audio_path="source.mp3",
        source_audio_url="/storage/source.mp3",
        status=ProjectStatus.processing,
        pipeline_job_id="job-1",
    )
    project_path.write_text(project.model_dump_json(indent=2), encoding="utf-8")

    stale_timestamp = (
        datetime.now(timezone.utc) - timedelta(seconds=JOB_STALE_SECONDS + 5)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    stale_job = JobDocument(
        id="job-1",
        project_id="project-1",
        kind="pipeline",
        status=JobStatus.running,
        updated_at=stale_timestamp,
    )

    def fake_patch_job(job_id: str, **changes: object) -> JobDocument:
        payload = stale_job.model_dump()
        payload.update(changes)
        return JobDocument(**payload)

    monkeypatch.setattr("backend.app.services.projects.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("backend.app.services.projects.get_job", lambda job_id: stale_job)
    monkeypatch.setattr("backend.app.services.projects.patch_job", fake_patch_job)

    loaded = load_project("project-1")

    assert loaded.status == ProjectStatus.failed
    assert STALE_PROCESSING_ERROR in loaded.errors


def test_store_background_detects_image_kind(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.services.projects.PROJECTS_DIR", tmp_path / "projects")

    path, url, kind = store_background("project-1", "bg.png", b"fake")

    assert kind == "image"
    assert path.endswith(".png")
    assert url.startswith("/storage/projects/project-1/backgrounds/")


def test_store_background_normalizes_video_to_mp4(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.services.projects.PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr("backend.app.services.projects.configure_ffmpeg_runtime", lambda: None)

    def fake_run(command, capture_output, text, env):
        output_path = Path(command[-1])
        output_path.write_bytes(b"mp4")

        class Result:
            returncode = 0
            stderr = ""
            stdout = ""

        return Result()

    monkeypatch.setattr("backend.app.services.projects.subprocess.run", fake_run)

    path, url, kind = store_background("project-1", "bg.mov", b"fake-video")

    assert kind == "video"
    assert path.endswith(".mp4")
    assert Path(path).exists()
    assert url.endswith(".mp4")
