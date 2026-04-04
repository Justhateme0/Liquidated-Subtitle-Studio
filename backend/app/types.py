from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .config import (
    DEFAULT_BACKGROUND,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    DEFAULT_FONT_FAMILY,
    DEFAULT_TEXT,
)


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class ProjectStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    ready = "ready"
    exporting = "exporting"
    failed = "failed"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ExportPreset(StrEnum):
    alpha_mov = "alpha_mov"
    mp4_solid = "mp4_solid"


class TranscriptWord(BaseModel):
    id: str
    text: str
    start: float
    end: float
    confidence: float | None = None


class CaptionLine(BaseModel):
    id: str
    text: str
    start: float
    end: float
    position_x: float = DEFAULT_CANVAS_WIDTH / 2
    position_y: float = DEFAULT_CANVAS_HEIGHT / 2
    disabled: bool = False


class ExportArtifact(BaseModel):
    preset: ExportPreset
    status: JobStatus = JobStatus.queued
    output_url: str | None = None
    file_path: str | None = None
    job_id: str | None = None
    created_at: str = Field(default_factory=now_iso)


class RenderStyle(BaseModel):
    font_family: str = DEFAULT_FONT_FAMILY
    font_file: str | None = None
    font_asset_url: str | None = None
    background_kind: Literal["color", "image", "video"] = "color"
    background_file: str | None = None
    background_asset_url: str | None = None
    font_size: float = 86.0
    text_color: str = DEFAULT_TEXT
    background_color: str = DEFAULT_BACKGROUND
    blur: float = 0.8
    stretch_y: float = 145.0
    uppercase: bool = False
    position_x: float = DEFAULT_CANVAS_WIDTH / 2
    position_y: float = DEFAULT_CANVAS_HEIGHT / 2
    canvas_width: int = DEFAULT_CANVAS_WIDTH
    canvas_height: int = DEFAULT_CANVAS_HEIGHT
    line_gap: float = 10.0
    letter_spacing: float = 0.0
    alignment: Literal["bottom_center"] = "bottom_center"


class ProjectDocument(BaseModel):
    id: str
    status: ProjectStatus = ProjectStatus.queued
    title: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    source_audio_path: str
    source_audio_url: str
    vocal_audio_path: str | None = None
    vocal_audio_url: str | None = None
    audio_duration_seconds: float | None = None
    transcript_words: list[TranscriptWord] = Field(default_factory=list)
    captions: list[CaptionLine] = Field(default_factory=list)
    style: RenderStyle = Field(default_factory=RenderStyle)
    exports: dict[str, ExportArtifact] = Field(default_factory=dict)
    pipeline_job_id: str | None = None
    errors: list[str] = Field(default_factory=list)


class JobDocument(BaseModel):
    id: str
    project_id: str
    kind: Literal["pipeline", "export"]
    status: JobStatus = JobStatus.queued
    progress: float = 0.0
    message: str = "Queued"
    payload: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    error: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class CreateProjectResponse(BaseModel):
    project: ProjectDocument
    job: JobDocument


class UpdateCaptionsRequest(BaseModel):
    captions: list[CaptionLine]


class UpdateStyleRequest(BaseModel):
    style: RenderStyle


class StartExportRequest(BaseModel):
    preset: ExportPreset
