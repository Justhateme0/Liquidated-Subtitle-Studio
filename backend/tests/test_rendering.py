from pathlib import Path

from backend.app.services.rendering import (
    _build_mp4_command,
    _export_output_path,
    _ass_time,
    _to_ass_color,
    _typewriter_frames,
    generate_ass,
)
from backend.app.types import CaptionLine, ExportArtifact, ExportPreset, ProjectDocument, RenderStyle


def test_ass_time_formatting():
    assert _ass_time(0) == "0:00:00.00"
    assert _ass_time(65.43) == "0:01:05.43"


def test_color_conversion():
    assert _to_ass_color("#8ACE00") == "&H0000CE8A"


def test_typewriter_frames_reveal_text_progressively():
    frames = _typewriter_frames("TEST", 1.0, 2.0)

    assert len(frames) >= 2
    assert frames[0][2] == "T"
    assert frames[-1][2] == "TEST"
    assert frames[-1][1] == 2.0


def test_generate_ass_uses_centered_position_and_typewriter_events(tmp_path: Path, monkeypatch):
    project = ProjectDocument(
        id="project-1",
        title="Track",
        source_audio_path=str(tmp_path / "source.mp3"),
        source_audio_url="/storage/source.mp3",
        captions=[
            CaptionLine(
                id="caption-1",
                text="ABCD",
                start=0.0,
                end=1.2,
                position_x=540.0,
                position_y=540.0,
            )
        ],
        style=RenderStyle(position_x=540.0, position_y=540.0),
    )

    monkeypatch.setattr("backend.app.services.rendering.exports_dir", lambda _project_id: tmp_path)
    ass_path = generate_ass(project, ExportPreset.mp4_solid)
    ass_text = ass_path.read_text(encoding="utf-8")

    assert ass_path == tmp_path / "mp4_solid.ass"
    assert r"\pos(540,540)" in ass_text
    assert "Dialogue: 0,0:00:00.00" in ass_text
    assert "ABCD" in ass_text


def test_build_mp4_command_uses_uploaded_image_background(tmp_path: Path):
    background_path = tmp_path / "bg.png"
    background_path.write_bytes(b"fake")
    project = ProjectDocument(
        id="project-1",
        title="Track",
        source_audio_path="source.mp3",
        source_audio_url="/storage/source.mp3",
        style=RenderStyle(
            background_kind="image",
            background_file=str(background_path),
            background_asset_url="/storage/backgrounds/bg.png",
        ),
    )

    command = _build_mp4_command(
        project,
        output_path=Path("output.mp4"),
        ass_path=Path("captions.ass"),
        duration=12.5,
        fonts_dir=None,
    )

    assert "-loop" in command
    assert command[command.index("-loop") + 1] == "1"
    assert str(background_path) in command
    assert command[command.index("-map") + 1] == "0:v:0"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "1:a:0"


def test_build_mp4_command_uses_uploaded_video_background_without_video_audio(tmp_path: Path):
    background_path = tmp_path / "bg.mov"
    background_path.write_bytes(b"fake")
    project = ProjectDocument(
        id="project-1",
        title="Track",
        source_audio_path="source.mp3",
        source_audio_url="/storage/source.mp3",
        style=RenderStyle(
            background_kind="video",
            background_file=str(background_path),
            background_asset_url="/storage/backgrounds/bg.mov",
        ),
    )

    command = _build_mp4_command(
        project,
        output_path=Path("output.mp4"),
        ass_path=Path("captions.ass"),
        duration=12.5,
        fonts_dir=None,
    )

    assert "-stream_loop" in command
    assert command[command.index("-stream_loop") + 1] == "-1"
    assert str(background_path) in command
    assert command[command.index("-map") + 1] == "0:v:0"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "1:a:0"


def test_export_output_path_uses_job_id_to_avoid_stale_cached_files(tmp_path: Path, monkeypatch):
    project = ProjectDocument(
        id="project-1",
        title="Track",
        source_audio_path="source.mp3",
        source_audio_url="/storage/source.mp3",
        exports={
            ExportPreset.mp4_solid.value: ExportArtifact(
                preset=ExportPreset.mp4_solid,
                job_id="job-123",
            )
        },
    )

    monkeypatch.setattr("backend.app.services.rendering.exports_dir", lambda _project_id: tmp_path)

    assert _export_output_path(project, ExportPreset.mp4_solid) == tmp_path / "subtitles-solid-job-123.mp4"
