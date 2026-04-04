from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..database import get_job
from ..services.projects import reconcile_job_runtime_state

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def read_job(job_id: str):
    job = reconcile_job_runtime_state(get_job(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
