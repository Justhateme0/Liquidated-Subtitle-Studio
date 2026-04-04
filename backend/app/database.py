from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import DB_PATH
from .types import JobDocument, ProjectDocument, now_iso


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                project_json_path TEXT NOT NULL,
                source_audio_path TEXT NOT NULL,
                vocal_audio_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def upsert_project(project: ProjectDocument, project_json_path: Path) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, status, title, project_json_path, source_audio_path,
                vocal_audio_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                title = excluded.title,
                project_json_path = excluded.project_json_path,
                source_audio_path = excluded.source_audio_path,
                vocal_audio_path = excluded.vocal_audio_path,
                updated_at = excluded.updated_at
            """,
            (
                project.id,
                project.status.value,
                project.title,
                str(project_json_path),
                project.source_audio_path,
                project.vocal_audio_path,
                project.created_at,
                project.updated_at,
            ),
        )
        connection.commit()


def get_project_row(project_id: str) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()


def upsert_job(job: JobDocument) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                id, project_id, kind, status, progress, message, payload_json,
                result_json, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                progress = excluded.progress,
                message = excluded.message,
                payload_json = excluded.payload_json,
                result_json = excluded.result_json,
                error = excluded.error,
                updated_at = excluded.updated_at
            """,
            (
                job.id,
                job.project_id,
                job.kind,
                job.status.value,
                job.progress,
                job.message,
                json.dumps(job.payload, ensure_ascii=False),
                json.dumps(job.result, ensure_ascii=False),
                job.error,
                job.created_at,
                job.updated_at,
            ),
        )
        connection.commit()


def get_job(job_id: str) -> JobDocument | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        return None
    return JobDocument(
        id=row["id"],
        project_id=row["project_id"],
        kind=row["kind"],
        status=row["status"],
        progress=row["progress"],
        message=row["message"],
        payload=json.loads(row["payload_json"]),
        result=json.loads(row["result_json"]),
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def patch_job(job_id: str, **changes: object) -> JobDocument:
    current = get_job(job_id)
    if current is None:
        raise KeyError(f"Job {job_id} was not found")
    data = current.model_dump()
    data.update(changes)
    data["updated_at"] = now_iso()
    job = JobDocument(**data)
    upsert_job(job)
    return job


def fail_incomplete_jobs(reason: str = "Interrupted by backend restart") -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status = ?, progress = ?, message = ?, error = ?, updated_at = ?
            WHERE status IN (?, ?)
            """,
            (
                "failed",
                100,
                reason,
                reason,
                now_iso(),
                "queued",
                "running",
            ),
        )
        connection.commit()
        return cursor.rowcount or 0
