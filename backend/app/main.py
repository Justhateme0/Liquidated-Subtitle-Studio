from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import STORAGE_DIR, ensure_directories
from .database import fail_incomplete_jobs, init_db
from .routers.jobs import router as jobs_router
from .routers.projects import router as projects_router
from .services.ffmpeg import configure_ffmpeg_runtime
from .services.projects import recover_interrupted_projects

ensure_directories()
init_db()

app = FastAPI(title="Brat Subtitle Studio", version="0.1.0")

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


@app.get("/")
def root():
    return {
        "name": "Brat Subtitle Studio API",
        "status": "ok",
        "frontend": "http://127.0.0.1:5173",
        "health": "/api/health",
        "docs": "/docs",
    }


app.include_router(projects_router)
app.include_router(jobs_router)
app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")
