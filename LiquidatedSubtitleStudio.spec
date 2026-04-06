# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH)
frontend_dist = project_root / "frontend" / "dist"
ffmpeg_dir = project_root / "tools" / "ffmpeg"
icon_path = project_root / "icon" / "icon.ico"

datas = collect_data_files("webview")
datas.extend(collect_data_files("demucs"))
if frontend_dist.exists():
    datas.append((str(frontend_dist), "frontend/dist"))
if ffmpeg_dir.exists():
    datas.append((str(ffmpeg_dir), "tools/ffmpeg"))

hiddenimports = collect_submodules("webview") + [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    ["desktop_app.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LiquidatedSubtitleStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LiquidatedSubtitleStudio",
)
