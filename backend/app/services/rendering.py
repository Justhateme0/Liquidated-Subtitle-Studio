from __future__ import annotations

from math import floor
from pathlib import Path
from uuid import uuid4

from ..config import FFMPEG_BIN
from ..types import ExportArtifact, ExportPreset, JobStatus, ProjectDocument, RenderStyle
from .ffmpeg import probe_duration, run_ffmpeg
from .projects import exports_dir, replace_project, to_public_url

TYPEWRITER_MIN_STEP_SECONDS = 0.045
TYPEWRITER_MAX_REVEAL_SECONDS = 1.2
TYPEWRITER_REVEAL_RATIO = 0.68


def _ass_time(seconds: float) -> str:
    total_centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"


def _to_ass_color(hex_color: str) -> str:
    color = hex_color.strip().lstrip("#")
    if len(color) != 6:
        raise ValueError(f"Expected #RRGGBB color, got {hex_color!r}")
    red = color[0:2]
    green = color[2:4]
    blue = color[4:6]
    return f"&H00{blue}{green}{red}"


def _escape_ass_text(value: str) -> str:
    escaped = value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
    return escaped.replace("\n", r"\N")


def _event_tags(style: RenderStyle) -> str:
    return (
        r"{\an5"
        + rf"\pos({round(style.position_x)},{round(style.position_y)})"
        + rf"\fscx100\fscy{style.stretch_y:.0f}"
        + rf"\blur{style.blur:.1f}"
        + rf"\fsp{style.letter_spacing:.0f}"
        + "}"
    )


def _typewriter_frames(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    characters = list(text)
    duration = max(0.0, end - start)
    if len(characters) < 2 or duration < TYPEWRITER_MIN_STEP_SECONDS * 2:
        return [(start, end, text)]

    reveal_window = min(duration * TYPEWRITER_REVEAL_RATIO, TYPEWRITER_MAX_REVEAL_SECONDS)
    step_count = min(len(characters), max(2, int(reveal_window / TYPEWRITER_MIN_STEP_SECONDS)))
    if step_count < 2:
        return [(start, end, text)]

    frames: list[tuple[float, float, str]] = []
    for step_index in range(step_count):
        slice_start = start + (reveal_window * step_index / step_count)
        slice_end = end if step_index == step_count - 1 else start + (reveal_window * (step_index + 1) / step_count)
        visible_count = 1 + floor(((len(characters) - 1) * step_index) / (step_count - 1))
        visible_text = "".join(characters[:visible_count]).rstrip()
        if not visible_text:
            continue
        frames.append((slice_start, slice_end, visible_text))

    return frames or [(start, end, text)]


def generate_ass(project: ProjectDocument, preset: ExportPreset) -> Path:
    style = project.style
    output_path = exports_dir(project.id) / f"{preset.value}.ass"
    font_name = style.font_family or "Arial Narrow"
    primary = _to_ass_color(style.text_color)
    outline = _to_ass_color(style.background_color)
    events: list[str] = []

    for caption in project.captions:
        if caption.disabled or not caption.text.strip():
            continue
        text = caption.text.upper() if style.uppercase else caption.text
        line_style = style.model_copy(
            update={"position_x": caption.position_x, "position_y": caption.position_y}
        )
        for event_start, event_end, frame_text in _typewriter_frames(text, caption.start, caption.end):
            events.append(
                "Dialogue: 0,"
                f"{_ass_time(event_start)},{_ass_time(event_end)},Default,,0,0,0,,"
                f"{_event_tags(line_style)}{_escape_ass_text(frame_text)}"
            )

    script = "\n".join(
        [
            "[Script Info]",
            "Title: Brat Subtitle Export",
            "ScriptType: v4.00+",
            f"PlayResX: {style.canvas_width}",
            f"PlayResY: {style.canvas_height}",
            "",
            "[V4+ Styles]",
            (
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
                "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
                "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding"
            ),
            (
                "Style: Default,"
                f"{font_name},{style.font_size:.0f},{primary},{primary},{outline},&H00000000,"
                f"0,0,0,0,100,{style.stretch_y:.0f},{style.letter_spacing:.0f},0,"
                "1,0,0,2,10,10,10,1"
            ),
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
            *events,
            "",
        ]
    )
    output_path.write_text(script, encoding="utf-8")
    return output_path


def _duration_for_project(project: ProjectDocument) -> float:
    if project.audio_duration_seconds:
        return project.audio_duration_seconds
    if project.captions:
        return max(caption.end for caption in project.captions) + 0.75
    return 10.0


def _ass_filter(ass_path: Path, fonts_dir: str | None) -> str:
    escaped_ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
    if fonts_dir:
        escaped_fonts = fonts_dir.replace("\\", "/").replace(":", "\\:")
        return f"ass='{escaped_ass}':fontsdir='{escaped_fonts}'"
    return f"ass='{escaped_ass}'"


def _background_scale_filter(style: RenderStyle) -> str:
    return (
        f"scale={style.canvas_width}:{style.canvas_height}:force_original_aspect_ratio=increase,"
        f"crop={style.canvas_width}:{style.canvas_height},setsar=1"
    )


def _mp4_video_filter(style: RenderStyle, ass_path: Path, fonts_dir: str | None) -> str:
    return ",".join([_background_scale_filter(style), _ass_filter(ass_path, fonts_dir)])


def _build_mp4_command(
    project: ProjectDocument,
    *,
    output_path: Path,
    ass_path: Path,
    duration: float,
    fonts_dir: str | None,
) -> list[str]:
    style = project.style
    video_filter = _mp4_video_filter(style, ass_path, fonts_dir)
    background_media_path = Path(style.background_file) if style.background_file else None
    if background_media_path is not None and not background_media_path.exists():
        background_media_path = None

    if style.background_kind == "image" and background_media_path:
        return [
            str(FFMPEG_BIN),
            "-y",
            "-loop",
            "1",
            "-i",
            str(background_media_path),
            "-i",
            project.source_audio_path,
            "-t",
            str(duration),
            "-vf",
            video_filter,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ]

    if style.background_kind == "video" and background_media_path:
        return [
            str(FFMPEG_BIN),
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(background_media_path),
            "-i",
            project.source_audio_path,
            "-t",
            str(duration),
            "-vf",
            video_filter,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ]

    background = style.background_color.lstrip("#")
    return [
        str(FFMPEG_BIN),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=color=0x{background}:size={style.canvas_width}x{style.canvas_height}:duration={duration}",
        "-i",
        project.source_audio_path,
        "-vf",
        _ass_filter(ass_path, fonts_dir),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_path),
    ]


def _export_output_path(project: ProjectDocument, preset: ExportPreset) -> Path:
    artifact = project.exports.get(preset.value)
    token = artifact.job_id if artifact and artifact.job_id else uuid4().hex
    if preset is ExportPreset.alpha_mov:
        return exports_dir(project.id) / f"subtitles-alpha-{token}.mov"
    return exports_dir(project.id) / f"subtitles-solid-{token}.mp4"


def render_export(project: ProjectDocument, preset: ExportPreset) -> ProjectDocument:
    style = project.style
    duration = _duration_for_project(project)
    export_folder = exports_dir(project.id)
    export_folder.mkdir(parents=True, exist_ok=True)
    ass_path = generate_ass(project, preset)

    fonts_dir = str(Path(style.font_file).parent) if style.font_file else None
    output_path = _export_output_path(project, preset)
    if preset is ExportPreset.alpha_mov:
        command = [
            str(FFMPEG_BIN),
            "-y",
            "-f",
            "lavfi",
            "-i",
            (
                f"color=color=black@0.0:size={style.canvas_width}x{style.canvas_height}:"
                f"duration={duration},format=rgba"
            ),
            "-vf",
            _ass_filter(ass_path, fonts_dir),
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4",
            "-pix_fmt",
            "yuva444p10le",
            str(output_path),
        ]
    else:
        command = _build_mp4_command(
            project,
            output_path=output_path,
            ass_path=ass_path,
            duration=duration,
            fonts_dir=fonts_dir,
        )

    run_ffmpeg(command)
    project.audio_duration_seconds = project.audio_duration_seconds or probe_duration(
        Path(project.source_audio_path)
    )
    artifact = project.exports.get(preset.value) or ExportArtifact(preset=preset)
    artifact.status = JobStatus.completed
    artifact.output_url = to_public_url(output_path)
    artifact.file_path = str(output_path)
    project.exports[preset.value] = artifact
    replace_project(project)
    return project
