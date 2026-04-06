from pathlib import Path

from backend.app.config import DEMUCS_MODEL_NAME
from backend.app.services.runtime_setup import (
    ensure_numpy_compat_aliases,
    ensure_standard_streams,
    prepare_runtime_assets,
    resolve_whisper_model_source,
    runtime_environment,
)


def test_runtime_environment_sets_torch_home(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.app.services.runtime_setup.TORCH_HOME_DIR", tmp_path / "torch")

    env = runtime_environment({"PATH": "demo"})

    assert env["PATH"] == "demo"
    assert env["TORCH_HOME"] == str(tmp_path / "torch")


def test_resolve_whisper_model_source_prefers_local_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.app.services.runtime_setup.WHISPER_MODELS_DIR", tmp_path / "whisper")
    local_model_dir = tmp_path / "whisper" / "medium"
    local_model_dir.mkdir(parents=True)

    assert resolve_whisper_model_source("medium") == str(local_model_dir)
    assert resolve_whisper_model_source("small") == "small"


def test_ensure_standard_streams_provides_sink_when_stdout_is_missing(monkeypatch):
    monkeypatch.setattr("backend.app.services.runtime_setup.sys.stdout", None)
    monkeypatch.setattr("backend.app.services.runtime_setup.sys.stderr", None)

    with ensure_standard_streams():
        import sys

        assert hasattr(sys.stdout, "write")
        assert hasattr(sys.stderr, "write")


def test_ensure_numpy_compat_aliases_registers_legacy_numpy_core_paths():
    ensure_numpy_compat_aliases()

    import sys

    assert "numpy.core" in sys.modules
    assert "numpy.core.multiarray" in sys.modules


def test_prepare_runtime_assets_downloads_unique_models_and_optional_cuda(monkeypatch):
    events: list[str] = []

    monkeypatch.setattr("backend.app.services.runtime_setup.ensure_directories", lambda: events.append("dirs"))
    monkeypatch.setattr("backend.app.services.runtime_setup.ensure_ffmpeg", lambda: events.append("ffmpeg"))
    monkeypatch.setattr(
        "backend.app.services.runtime_setup._download_whisper_model",
        lambda model_size, progress_callback=None: events.append(f"whisper:{model_size}"),
    )
    monkeypatch.setattr(
        "backend.app.services.runtime_setup._prepare_demucs_model",
        lambda model_name=DEMUCS_MODEL_NAME, progress_callback=None: events.append(f"demucs:{model_name}"),
    )
    monkeypatch.setattr("backend.app.services.runtime_setup.cuda_available", lambda: True)

    prepare_runtime_assets(
        whisper_model_sizes=("medium", "small", "medium"),
        cuda_model_size="large-v3",
    )

    assert events == [
        "dirs",
        "ffmpeg",
        "whisper:medium",
        "whisper:small",
        "whisper:large-v3",
        f"demucs:{DEMUCS_MODEL_NAME}",
    ]
