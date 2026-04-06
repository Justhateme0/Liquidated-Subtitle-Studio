from __future__ import annotations

import contextlib
import importlib
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Callable

from ..config import DEMUCS_MODEL_NAME, TORCH_HOME_DIR, WHISPER_MODELS_DIR, ensure_directories
from .ffmpeg import ensure_ffmpeg

ProgressCallback = Callable[[str], None]


@contextlib.contextmanager
def ensure_standard_streams():
    sink = None
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    if sys.stdout is None or sys.stderr is None:
        sink = open(os.devnull, "w", encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = sink
        if sys.stderr is None:
            sys.stderr = sink

    try:
        yield
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        if sink is not None:
            sink.close()


def ensure_numpy_compat_aliases() -> None:
    # Frozen NumPy 2 bundles expose implementation modules under numpy._core,
    # while some torch-loaded checkpoints still reference the legacy numpy.core path.
    alias_targets = {
        "numpy.core": "numpy._core",
        "numpy.core._multiarray_umath": "numpy._core._multiarray_umath",
        "numpy.core.multiarray": "numpy._core.multiarray",
        "numpy.core.numeric": "numpy._core.numeric",
        "numpy.core.numerictypes": "numpy._core.numerictypes",
    }
    for alias, target in alias_targets.items():
        if alias in sys.modules:
            continue
        try:
            sys.modules[alias] = importlib.import_module(target)
        except Exception:
            continue


def cuda_available() -> bool:
    try:
        import torch
    except Exception:
        return False

    return bool(torch.cuda.is_available())


def runtime_environment(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    env["TORCH_HOME"] = str(TORCH_HOME_DIR)
    return env


def whisper_model_dir(model_size: str) -> Path:
    return WHISPER_MODELS_DIR / model_size


def resolve_whisper_model_source(model_size: str) -> str:
    local_dir = whisper_model_dir(model_size)
    if local_dir.exists():
        return str(local_dir)
    return model_size


def _download_whisper_model(
    model_size: str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> None:
    from faster_whisper.utils import download_model

    local_dir = whisper_model_dir(model_size)
    local_dir.parent.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback(f"Downloading faster-whisper model {model_size}")
    download_model(model_size, output_dir=str(local_dir))


def _prepare_demucs_model(
    model_name: str = DEMUCS_MODEL_NAME,
    *,
    progress_callback: ProgressCallback | None = None,
) -> None:
    import torch
    from demucs.pretrained import get_model

    ensure_numpy_compat_aliases()
    TORCH_HOME_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["TORCH_HOME"] = str(TORCH_HOME_DIR)
    torch.hub.set_dir(str(TORCH_HOME_DIR))
    if progress_callback:
        progress_callback(f"Downloading Demucs model {model_name}")
    with ensure_standard_streams():
        get_model(model_name)


def prepare_runtime_assets(
    *,
    whisper_model_sizes: Iterable[str],
    cuda_model_size: str | None = None,
    demucs_model: str = DEMUCS_MODEL_NAME,
    progress_callback: ProgressCallback | None = None,
) -> None:
    ensure_directories()
    ensure_ffmpeg()

    planned_models: list[str] = []
    seen: set[str] = set()
    for model_size in whisper_model_sizes:
        if model_size and model_size not in seen:
            seen.add(model_size)
            planned_models.append(model_size)

    if cuda_model_size and cuda_available() and cuda_model_size not in seen:
        planned_models.append(cuda_model_size)

    for model_size in planned_models:
        _download_whisper_model(model_size, progress_callback=progress_callback)

    _prepare_demucs_model(demucs_model, progress_callback=progress_callback)
