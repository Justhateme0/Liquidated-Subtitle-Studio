from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..config import FFMPEG_ARCHIVE_URL, FFMPEG_BIN, FFPROBE_BIN, FFMPEG_DIR, TOOLS_DIR

_DLL_HANDLES: list[object] = []


def ffmpeg_available() -> bool:
    return FFMPEG_BIN.exists() and FFPROBE_BIN.exists()


def ensure_ffmpeg() -> None:
    if ffmpeg_available():
        return

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(delete=False, suffix=".zip", dir=TOOLS_DIR) as archive:
        with urllib.request.urlopen(FFMPEG_ARCHIVE_URL) as response:
            archive.write(response.read())
        archive_path = Path(archive.name)

    extract_root = TOOLS_DIR / "_ffmpeg_extract"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as zip_file:
        zip_file.extractall(extract_root)

    extracted_bin = next(extract_root.rglob("ffmpeg.exe")).parent
    if FFMPEG_DIR.exists():
        shutil.rmtree(FFMPEG_DIR)
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(extracted_bin.parent, FFMPEG_DIR, dirs_exist_ok=True)

    archive_path.unlink(missing_ok=True)
    shutil.rmtree(extract_root, ignore_errors=True)


def configure_ffmpeg_runtime() -> None:
    ensure_ffmpeg()
    bin_dir = str(FFMPEG_BIN.parent.resolve())
    path_value = os.environ.get("PATH", "")
    if bin_dir not in path_value.split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + path_value

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        try:
            handle = add_dll_directory(bin_dir)
        except FileNotFoundError:
            return
        _DLL_HANDLES.append(handle)


def run_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
    configure_ffmpeg_runtime()
    return subprocess.run(command, capture_output=True, text=True, check=True)


def probe_duration(media_path: Path) -> float | None:
    if not media_path.exists():
        return None

    configure_ffmpeg_runtime()
    result = subprocess.run(
        [
            str(FFPROBE_BIN),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    duration = payload.get("format", {}).get("duration")
    return float(duration) if duration is not None else None
