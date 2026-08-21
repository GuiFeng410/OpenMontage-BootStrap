"""Produce job JSON store. Delegates to board_production_run + JsonStore."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lib.board_production_run as production_run
from lib.board_advance import write_board_stop_overlay
from lib.persistence.json_store import JsonStore


def _projects_root(projects_dir: Path | None = None) -> Path:
    if projects_dir is not None:
        return Path(projects_dir)
    facade = sys.modules.get("lib.board_produce")
    if facade is not None:
        current = getattr(facade, "PROJECTS_DIR", None)
        if current is not None:
            return Path(current)
    from lib.paths import PROJECTS_DIR

    return Path(PROJECTS_DIR)

JOB_NAME = "produce_job.json"

OUTPUT_REL = "renders/final.mp4"

STATUS_QUEUED = "queued"

STATUS_RUNNING = "running"

STATUS_PAUSED = "paused"

STATUS_FAILED = "failed"

STATUS_DONE = "done"

STATUS_SKIPPED = "skipped"

class ProduceJobError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "produce_job",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.extra = extra or {}

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _project_dir(project_id: str, projects_dir: Path | None = None) -> Path:
    return _projects_root(projects_dir) / project_id

def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}

def _write_json(path: Path, data: dict[str, Any]) -> None:
    JsonStore.write_atomic(path, data, replace_retries=3)

def _locked_artifact_revision(project: Path) -> str:
    marker = _read_json(project / "project.json")
    profile = marker.get("production_profile") if isinstance(marker, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    identity = {
        "production_profile": {
            key: profile.get(key)
            for key in (
                "production_tier",
                "review_mode_preset",
                "review_mode",
                "provider",
                "video_channel",
                "video_model",
                "model",
                "resolution",
            )
        },
        "artifacts": {
            name: _read_json(project / "artifacts" / f"{name}.json")
            for name in (
                "brief",
                "video_plan",
                "segment_cards",
                "asset_ledger",
                "asset_precheck",
            )
        },
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def job_path(project_id: str, *, projects_dir: Path | None = None) -> Path:
    return production_run.produce_job_path(_project_dir(project_id, projects_dir))

def read_job(project_id: str, *, projects_dir: Path | None = None) -> dict[str, Any] | None:
    project = _project_dir(project_id, projects_dir)
    try:
        run = production_run.read_production_run(project)
        run_revision = run.get("run_revision") if run else "1"
        return production_run.read_produce_job(
            project,
            run_revision=run_revision,
        )
    except production_run.ProductionRunError as exc:
        return {
            "version": production_run.JOB_VERSION,
            "project_id": project_id,
            "status": STATUS_PAUSED,
            "code": "run_state_invalid",
            "friendly_zh": "生产状态文件无效，已暂停且不会自动重试。请先修复状态文件。",
            "error": str(exc),
        }

def busy_project_ids(*, projects_dir: Path | None = None) -> list[str]:
    root = _projects_root(projects_dir)
    if not root.is_dir():
        return []
    busy: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        job = read_job(entry.name, projects_dir=root) or {}
        if str(job.get("status") or "") in {STATUS_QUEUED, STATUS_RUNNING}:
            busy.append(entry.name)
    return busy

def write_job(
    project_id: str,
    payload: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    run, _created = production_run.load_or_initialize_production_run(
        project,
        persist=True,
    )
    existing = production_run.read_produce_job(
        project,
        run_revision=run["run_revision"],
    ) or {}
    prior_job_id = str(existing.get("job_id") or "").strip()
    if existing and any(
        field in payload and payload.get(field) != existing.get(field)
        for field in ("stage", "kind", "artifact_revision", "batch_id")
    ):
        existing = {}
    authorization_refs = run.get("authorization_refs") or []
    latest_authorization = (
        authorization_refs[-1]
        if authorization_refs and isinstance(authorization_refs[-1], dict)
        else {}
    )
    body = {
        **existing,
        "version": production_run.JOB_VERSION,
        "project_id": project_id,
        "run_revision": run["run_revision"],
        "stage": existing.get("stage") or "final_compose",
        "kind": existing.get("kind") or "final",
        "artifact_revision": (
            existing.get("artifact_revision") or _locked_artifact_revision(project)
        ),
        "authorization_revision": existing.get("authorization_revision")
        or latest_authorization.get("authorization_revision"),
        "attempt": existing.get("attempt") or 1,
        "provider": existing.get("provider") or run.get("locked_provider") or "",
        "model": existing.get("model") or run.get("locked_model") or "",
        "batch_id": existing.get("batch_id") or "",
        "beat_ids": existing.get("beat_ids") or [],
        "expected_outputs": existing.get("expected_outputs")
        or [OUTPUT_REL, "artifacts/edit_decisions.json"],
        "cost_snapshot": existing.get("cost_snapshot") or {},
        "created_at": existing.get("created_at") or _now(),
        **payload,
        "updated_at": _now(),
    }
    if not str(body.get("job_id") or "").strip() and prior_job_id:
        body["job_id"] = prior_job_id
    written = production_run.write_produce_job(project, body)
    updated_run = production_run.register_job_summary(run, written)
    production_run.write_production_run(project, updated_run)
    return written

def _has_final(project_id: str, *, projects_dir: Path | None = None) -> bool:
    path = _project_dir(project_id, projects_dir) / OUTPUT_REL
    return path.is_file() and path.stat().st_size > 0

def _profile(marker: dict[str, Any]) -> dict[str, Any]:
    raw = marker.get("production_profile") if isinstance(marker, dict) else {}
    return raw if isinstance(raw, dict) else {}

def _tier(profile: dict[str, Any]) -> str:
    value = str(profile.get("production_tier") or "light").strip().lower()
    if value in {"light", "medium", "heavy"}:
        return value
    return "light"

def _refresh_overlay(
    project_id: str,
    friendly_zh: str,
    *,
    projects_dir: Path | None = None,
    paused: bool = False,
) -> None:
    marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    stage = str(stop.get("stage") or "delivery_signoff")
    write_board_stop_overlay(project_id, stage, projects_dir=projects_dir)
    marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    if not stop:
        return
    stop["producing_wait"] = not paused
    stop["paused"] = bool(paused)
    stop["needs_user_decision"] = bool(paused)
    stop["decision_title_zh"] = "已暂停" if paused else "制作中"
    stop["decision_prompt_zh"] = friendly_zh
    stop["decision_options"] = []
    marker["board_stop"] = stop
    _write_json(_project_dir(project_id, projects_dir) / "project.json", marker)

def _fail_job(
    project_id: str,
    *,
    projects_dir: Path | None,
    engine: str,
    tier: str,
    code: str,
    friendly_zh: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": STATUS_FAILED,
        "engine": engine,
        "tier": tier,
        "code": code,
        "friendly_zh": friendly_zh,
    }
    if extra:
        payload.update(extra)
    try:
        job = write_job(project_id, payload, projects_dir=projects_dir)
    except (production_run.ProductionRunError, OSError) as exc:
        job = {
            "version": production_run.JOB_VERSION,
            "project_id": project_id,
            **payload,
            "code": "run_state_invalid",
            "error": str(exc),
            "friendly_zh": "生产状态无法安全写入，已暂停且不会启动或重试任务。",
        }
    _refresh_overlay(project_id, friendly_zh, projects_dir=projects_dir, paused=True)
    return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}


def clear_retry_exhausted_for_manual_retry(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Archive a frozen failed job so the same channel/model can be retried from the board.

    Does not switch providers. Caller should rebind the unique runner afterward.
    """
    pid = str(project_id or "").strip()
    if not pid:
        raise ProduceJobError("缺少 project_id", code="bad_project")
    project = _project_dir(pid, projects_dir)
    job_path = production_run.produce_job_path(project)
    raw = _read_json(job_path) if job_path.is_file() else {}
    existing = read_job(pid, projects_dir=projects_dir) or {}
    # Prefer raw disk fields: a corrupt/normalized paused projection must not
    # block clearing an on-disk retry_exhausted freeze.
    status = str(raw.get("status") or existing.get("status") or "")
    exhausted = bool(raw.get("retry_exhausted") or existing.get("retry_exhausted"))
    if status != STATUS_FAILED and not exhausted:
        raise ProduceJobError(
            "当前没有「重试耗尽」的失败任务，无需再重试。",
            code="retry_not_needed",
        )
    if not isinstance(existing, dict) or not existing.get("provider"):
        existing = {**existing, **raw}
    history = project / "history"
    history.mkdir(parents=True, exist_ok=True)
    stamp = _now().replace(":", "").replace("+", "Z")
    archived = ""
    if job_path.is_file():
        dest = history / f"produce_job_failed_{stamp}.json"
        dest.write_text(job_path.read_text(encoding="utf-8"), encoding="utf-8")
        job_path.unlink()
        archived = str(dest.relative_to(project)).replace("\\", "/")
    marker_path = project / "project.json"
    marker = _read_json(marker_path)
    profile = dict(marker.get("production_profile") or {})
    profile["production_start_requested_at"] = _now()
    profile["runner_start_pending"] = True
    marker["production_profile"] = profile
    wait_zh = (
        "已清除上次冻结，将按同一渠道同一模型再试。"
        "请留在本页；不会自动换渠道。"
    )
    marker["board_stop"] = {
        "stage": str((marker.get("board_stop") or {}).get("stage") or "delivery_signoff"),
        "needs_user_decision": False,
        "producing_wait": True,
        "paused": False,
        "decision_title_zh": "制作中",
        "decision_prompt_zh": wait_zh,
        "decision_options": [],
    }
    _write_json(marker_path, marker)
    from lib.project_export import write_runner_status

    write_runner_status(
        pid,
        {
            "phase": "producing",
            "runner_alive": False,
            "retry_exhausted": False,
            "stop_runner": False,
            "friendly_zh": wait_zh,
        },
    )
    return {
        "ok": True,
        "project_id": pid,
        "archived_job": archived,
        "provider": existing.get("provider"),
        "model": existing.get("model"),
        "friendly_zh": wait_zh,
        "spawn_runner": True,
    }
