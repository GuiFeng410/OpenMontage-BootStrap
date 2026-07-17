"""Sandbox-local job store for long-running compose/TTS batch work."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openmontage.mcp.common.errors import DoctorError
from openmontage.mcp.common.sandbox import require_projects_root


def _jobs_dir() -> Path:
    root = require_projects_root()
    path = root / ".openmontage_jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _job_path(job_id: str) -> Path:
    if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
        raise DoctorError(f"Invalid job_id: {job_id!r}", code="bad_request")
    return _jobs_dir() / f"{job_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(kind: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:16]
    job = {
        "job_id": job_id,
        "kind": kind,
        "status": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "meta": meta or {},
        "result": None,
        "error": None,
        "progress": 0.0,
    }
    _job_path(job_id).write_text(json.dumps(job, indent=2), encoding="utf-8")
    return job


def read_job(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    if not path.exists():
        raise DoctorError(f"Job not found: {job_id}", code="not_found")
    return json.loads(path.read_text(encoding="utf-8"))


def update_job(job_id: str, **fields: Any) -> dict[str, Any]:
    job = read_job(job_id)
    job.update(fields)
    job["updated_at"] = _now()
    _job_path(job_id).write_text(json.dumps(job, indent=2), encoding="utf-8")
    return job


def cancel_job(job_id: str) -> dict[str, Any]:
    job = read_job(job_id)
    if job.get("status") in {"succeeded", "failed", "cancelled"}:
        return job
    return update_job(job_id, status="cancelled", progress=1.0)


def start_background(job_id: str, worker: Callable[[str], None]) -> None:
    def _run() -> None:
        try:
            update_job(job_id, status="running", progress=0.05)
            if read_job(job_id).get("status") == "cancelled":
                return
            worker(job_id)
            current = read_job(job_id)
            if current.get("status") == "cancelled":
                return
            if current.get("status") != "failed":
                update_job(job_id, status="succeeded", progress=1.0)
        except Exception as exc:  # noqa: BLE001
            update_job(job_id, status="failed", error=str(exc), progress=1.0)

    threading.Thread(target=_run, name=f"om-job-{job_id}", daemon=True).start()
