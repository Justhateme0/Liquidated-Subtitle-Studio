from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import ALLOWED_AUDIO_EXTENSIONS, ALLOWED_BACKGROUND_EXTENSIONS, ALLOWED_FONT_EXTENSIONS
from ..types import CreateProjectResponse, ExportArtifact, ExportPreset, JobDocument, JobStatus, ProjectDocument, StartExportRequest, UpdateCaptionsRequest, UpdateStyleRequest
from ..services.pipeline import start_export_job, start_pipeline_job
from ..services.projects import create_project, load_project, replace_project, store_background, store_font

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=CreateProjectResponse)
async def create_project_endpoint(file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    project = create_project(file.filename or f"track{extension}", payload)
    job = JobDocument(
        id=uuid4().hex,
        project_id=project.id,
        kind="pipeline",
        status=JobStatus.queued,
        message="Queued for audio processing",
    )
    project.pipeline_job_id = job.id
    replace_project(project)
    start_pipeline_job(project, job)
    return CreateProjectResponse(project=project, job=job)


@router.get("/{project_id}", response_model=ProjectDocument)
def read_project(project_id: str):
    return _require_project(project_id)


@router.patch("/{project_id}/captions", response_model=ProjectDocument)
def update_captions(project_id: str, request: UpdateCaptionsRequest):
    project = _require_project(project_id)
    project.captions = request.captions
    return replace_project(project)


@router.patch("/{project_id}/style", response_model=ProjectDocument)
def update_style(project_id: str, request: UpdateStyleRequest):
    project = _require_project(project_id)
    project.style = request.style
    return replace_project(project)


@router.post("/{project_id}/fonts", response_model=ProjectDocument)
async def upload_font(project_id: str, file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_FONT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only TTF and OTF fonts are supported")

    project = _require_project(project_id)
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded font is empty")

    font_path, font_url = store_font(project_id, file.filename or f"font{extension}", payload)
    project.style.font_file = font_path
    project.style.font_asset_url = font_url
    project.style.font_family = Path(file.filename or "Custom Font").stem
    return replace_project(project)


@router.post("/{project_id}/background", response_model=ProjectDocument)
async def upload_background(project_id: str, file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_BACKGROUND_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only image and video backgrounds are supported")

    project = _require_project(project_id)
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded background is empty")

    background_path, background_url, background_kind = store_background(
        project_id,
        file.filename or f"background{extension}",
        payload,
    )
    project.style.background_file = background_path
    project.style.background_asset_url = background_url
    project.style.background_kind = background_kind
    return replace_project(project)


@router.post("/{project_id}/exports")
def start_export(project_id: str, request: StartExportRequest):
    project = _require_project(project_id)
    if not project.captions:
        raise HTTPException(status_code=400, detail="Project has no captions to export")

    job = JobDocument(
        id=uuid4().hex,
        project_id=project.id,
        kind="export",
        status=JobStatus.queued,
        message=f"Queued {request.preset.value} export",
        payload={"preset": request.preset.value},
    )
    artifact = project.exports.get(request.preset.value) or ExportArtifact(preset=request.preset)
    artifact.job_id = job.id
    artifact.status = JobStatus.queued
    artifact.output_url = None
    artifact.file_path = None
    project.exports[request.preset.value] = artifact
    replace_project(project)
    start_export_job(project.id, job, request.preset)
    return job


@router.get("/{project_id}/exports/{preset}/download")
def download_export(project_id: str, preset: ExportPreset):
    project = _require_project(project_id)
    artifact = project.exports.get(preset.value)
    if artifact is None or not artifact.file_path:
        raise HTTPException(status_code=404, detail="Export file was not found")

    export_path = Path(artifact.file_path)
    if not export_path.exists():
        raise HTTPException(status_code=404, detail="Export file is missing on disk")

    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", project.title).strip(" .") or "export"
    suffix = export_path.suffix.lower()
    preset_suffix = "alpha" if preset is ExportPreset.alpha_mov else "solid"
    filename = f"{safe_title}-{preset_suffix}{suffix}"
    return FileResponse(export_path, filename=filename)


def _require_project(project_id: str) -> ProjectDocument:
    try:
        return load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
