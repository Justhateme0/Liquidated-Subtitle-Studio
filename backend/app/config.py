from __future__ import annotations

import os
import sys
from pathlib import Path

APP_SLUG = "LiquidatedSubtitleStudio"
APP_NAME = "Liquidated Subtitle Studio"
LEGACY_APP_NAMES = ("Brat Subtitle Studio",)
APP_VERSION = "1.0.0"
WHISPER_CUDA_MODEL_SIZE = "large-v3"
WHISPER_CPU_PRIMARY_MODEL_SIZE = "medium"
WHISPER_CPU_FALLBACK_MODEL_SIZE = "small"
DEMUCS_MODEL_NAME = "htdemucs"


def _bundle_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[2]


def _data_root() -> Path:
    if not getattr(sys, "frozen", False):
        return BUNDLE_ROOT
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    current_root = local_app_data / APP_NAME
    if current_root.exists():
        return current_root

    for legacy_name in LEGACY_APP_NAMES:
        legacy_root = local_app_data / legacy_name
        if not legacy_root.exists():
            continue
        try:
            legacy_root.rename(current_root)
            return current_root
        except OSError:
            return legacy_root

    return current_root


BUNDLE_ROOT = _bundle_root()
DATA_ROOT = _data_root()
ROOT_DIR = BUNDLE_ROOT
BACKEND_DIR = BUNDLE_ROOT / "backend"
FRONTEND_DIST_DIR = BUNDLE_ROOT / "frontend" / "dist"
STORAGE_DIR = DATA_ROOT / "storage"
PROJECTS_DIR = STORAGE_DIR / "projects"
MODELS_DIR = DATA_ROOT / "models"
WHISPER_MODELS_DIR = MODELS_DIR / "whisper"
TORCH_HOME_DIR = MODELS_DIR / "torch"
WEBVIEW_STORAGE_DIR = DATA_ROOT / "webview"
LOG_FILE = DATA_ROOT / "desktop.log"
BUNDLED_TOOLS_DIR = BUNDLE_ROOT / "tools"
USER_TOOLS_DIR = DATA_ROOT / "tools"
TOOLS_DIR = (
    BUNDLED_TOOLS_DIR
    if (BUNDLED_TOOLS_DIR / "ffmpeg" / "bin" / "ffmpeg.exe").exists()
    else USER_TOOLS_DIR
)
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
    for path in (
        DATA_ROOT,
        STORAGE_DIR,
        PROJECTS_DIR,
        MODELS_DIR,
        WHISPER_MODELS_DIR,
        TORCH_HOME_DIR,
        WEBVIEW_STORAGE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
    if TOOLS_DIR == USER_TOOLS_DIR:
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
