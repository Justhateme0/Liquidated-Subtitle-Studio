from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, APP_VERSION, FRONTEND_DIST_DIR, STORAGE_DIR, ensure_directories
from .database import fail_incomplete_jobs, init_db
from .routers.jobs import router as jobs_router
from .routers.projects import router as projects_router
from .services.ffmpeg import configure_ffmpeg_runtime
from .services.projects import recover_interrupted_projects

ensure_directories()
init_db()

app = FastAPI(title=APP_NAME, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_directories()
    init_db()
    fail_incomplete_jobs()
    recover_interrupted_projects()
    configure_ffmpeg_runtime()


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}


app.include_router(projects_router)
app.include_router(jobs_router)
app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")

_RESERVED_FRONTEND_PREFIXES = ("api", "docs", "redoc", "openapi.json", "storage")


def _frontend_index_path() -> Path:
    return FRONTEND_DIST_DIR / "index.html"


def _frontend_available() -> bool:
    return _frontend_index_path().exists()


if _frontend_available():
    _frontend_root = FRONTEND_DIST_DIR.resolve()
    _frontend_index = _frontend_index_path()

    @app.get("/", include_in_schema=False)
    def frontend_root():
        return FileResponse(_frontend_index)


    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_catchall(full_path: str):
        if any(
            full_path == prefix or full_path.startswith(f"{prefix}/")
            for prefix in _RESERVED_FRONTEND_PREFIXES
        ):
            raise HTTPException(status_code=404, detail="Not found")

        requested_path = (_frontend_root / full_path).resolve()
        if requested_path.is_file():
            try:
                requested_path.relative_to(_frontend_root)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Not found") from exc
            return FileResponse(requested_path)

        return FileResponse(_frontend_index)
else:
    @app.get("/")
    def root():
        return {
            "name": f"{APP_NAME} API",
            "status": "ok",
            "frontend": "http://127.0.0.1:5173",
            "health": "/api/health",
            "docs": "/docs",
        }
