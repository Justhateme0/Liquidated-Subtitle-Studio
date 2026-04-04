from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
STORAGE_DIR = ROOT_DIR / "storage"
PROJECTS_DIR = STORAGE_DIR / "projects"
TOOLS_DIR = ROOT_DIR / "tools"
DB_PATH = STORAGE_DIR / "app.db"
FFMPEG_DIR = TOOLS_DIR / "ffmpeg"
FFMPEG_BIN = FFMPEG_DIR / "bin" / "ffmpeg.exe"
FFPROBE_BIN = FFMPEG_DIR / "bin" / "ffprobe.exe"

DEFAULT_CANVAS_WIDTH = 1080
DEFAULT_CANVAS_HEIGHT = 1080
DEFAULT_FONT_FAMILY = "Arial Narrow"
DEFAULT_BACKGROUND = "#8ACE00"
DEFAULT_TEXT = "#111111"
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
ALLOWED_FONT_EXTENSIONS = {".ttf", ".otf"}
ALLOWED_BACKGROUND_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_BACKGROUND_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
ALLOWED_BACKGROUND_EXTENSIONS = (
    ALLOWED_BACKGROUND_IMAGE_EXTENSIONS | ALLOWED_BACKGROUND_VIDEO_EXTENSIONS
)
FFMPEG_ARCHIVE_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-n7.1-latest-win64-gpl-shared-7.1.zip"
)


def ensure_directories() -> None:
    for path in (STORAGE_DIR, PROJECTS_DIR, TOOLS_DIR):
        path.mkdir(parents=True, exist_ok=True)
