"""Pure persistence contracts for staged Backlot production runs.

``production_run.json`` is the recoverable orchestration summary. It stores
references to checkpoints, artifacts, authorizations, and jobs, never copies of
their canonical payloads. ``artifacts/produce_job.json`` remains the projection
of the one current low-level task.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from lib.review_interrupt import COMMERCIAL_STAGE_ORDER, normalize_review_preset

RUN_FILENAME = "production_run.json"
PRODUCE_JOB_REL = Path("artifacts") / "produce_job.json"
RUN_VERSION = "1.0"
JOB_VERSION = "2.0"

ACTIVE_JOB_STATUSES = frozenset({"queued", "running"})
JOB_STATUSES = frozenset(
    {"queued", "running", "paused", "failed", "done", "skipped", "cancelled"}
)
STAGE_RESULT_STATUSES = frozenset(
    {
        "pending",
        "in_progress",
        "awaiting_human",
        "completed",
        "failed",
        "paused",
        "not_required",
    }
)
PRODUCTION_TIERS = frozenset({"light", "medium", "heavy"})

_ARTIFACT_STAGE_REFS = {
    "sample_review": ("artifacts/sample_reel.json",),
    "segment_build": ("artifacts/review_overview.json",),
    "draft_review": ("artifacts/full_draft_pro.json",),
    "final_compose": ("artifacts/final_review.json",),
}
_JOB_SUMMARY_FIELDS = (
    "job_key",
    "stage",
    "kind",
    "artifact_revision",
    "authorization_revision",
    "attempt",
    "provider",
    "model",
    "batch_id",
    "beat_ids",
    "expected_outputs",
    "status",
    "job_id",
    "cost_snapshot",
    "created_at",
    "updated_at",
)
_JOB_IDENTITY_FIELDS = (
    "stage",
    "kind",
    "artifact_revision",
    "provider",
    "model",
    "batch_id",
    "beat_ids",
    "expected_outputs",
)


class ProductionRunError(Exception):
    """Raised when run/job state cannot be interpreted without guessing."""


class ProductionRunConflictError(ProductionRunError):
    """Raised when one stable job key refers to incompatible task content."""


def _now_iso(now: str | None = None) -> str:
    if now is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if not isinstance(now, str) or not now.strip():
        raise ProductionRunError("now must be a non-empty ISO-8601 string")
    value = now.strip()
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ProductionRunError("now must be an ISO-8601 string") from exc
    if parsed.tzinfo is None:
        raise ProductionRunError("now must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _nonempty(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProductionRunError(f"{field} must be non-empty")
    return text


def _revision(value: Any, field: str, *, default: str | None = None) -> str:
    if value in (None, "") and default is not None:
        return default
    return _nonempty(value, field)


def _optional_revision(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return _revision(value, "authorization_revision")


def _string_list(raw: Any, field: str) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        values: Iterable[Any] = (raw,)
    elif isinstance(raw, (list, tuple)):
        values = raw
    else:
        raise ProductionRunError(f"{field} must be a list of strings")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _nonempty(value, field)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _relative_ref(value: Any, field: str) -> str:
    text = _nonempty(value, field).replace("\\", "/")
    path = Path(text)
    if path.is_absolute() or ".." in path.parts or ":" in text:
        raise ProductionRunError(f"{field} must be project-relative: {text!r}")
    return text


def _relative_refs(raw: Any, field: str) -> list[str]:
    return [_relative_ref(item, field) for item in _string_list(raw, field)]


def _read_json_strict(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionRunError(f"invalid JSON state: {path}") from exc
    if not isinstance(loaded, dict):
        raise ProductionRunError(f"JSON state must be an object: {path}")
    return loaded


def _read_json_for_migration(
    path: Path,
    warnings: list[str],
    *,
    warning_ref: str | None = None,
) -> dict[str, Any] | None:
    try:
        return _read_json_strict(path)
    except ProductionRunError:
        warnings.append(warning_ref or path.name)
        return None


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def production_run_path(project_dir: Path) -> Path:
    return Path(project_dir) / RUN_FILENAME


def produce_job_path(project_dir: Path) -> Path:
    return Path(project_dir) / PRODUCE_JOB_REL


def stable_job_key(
    project_id: str,
    run_revision: Any,
    stage: str,
    kind: str,
    artifact_revision: Any,
    batch_id: Any = "",
) -> str:
    """Return the v1 idempotency key frozen by the C0 contract."""

    stage_id = _nonempty(stage, "stage")
    if stage_id not in COMMERCIAL_STAGE_ORDER:
        raise ProductionRunError(f"unknown commercial stage: {stage_id}")
    identity = {
        "project_id": _nonempty(project_id, "project_id"),
        "run_revision": _revision(run_revision, "run_revision"),
        "stage": stage_id,
        "kind": _nonempty(kind, "kind"),
        "artifact_revision": _revision(artifact_revision, "artifact_revision"),
        "batch_id": str(batch_id or "").strip(),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "job_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_produce_job(
    data: dict[str, Any],
    *,
    project_id: str | None = None,
    run_revision: Any = "1",
    now: str | None = None,
) -> dict[str, Any]:
    """Normalize a legacy v1 or current v2 job into the v2 projection."""

    if not isinstance(data, dict):
        raise ProductionRunError("produce job must be an object")
    normalized_project_id = _nonempty(
        project_id or data.get("project_id"), "project_id"
    )
    if data.get("project_id") and data.get("project_id") != normalized_project_id:
        raise ProductionRunError("produce job project_id mismatch")

    source_version = str(data.get("version") or "1.0")
    is_legacy = not source_version.startswith("2")
    normalized_run_revision = _revision(
        data.get("run_revision"), "run_revision", default=str(run_revision)
    )
    stage = str(data.get("stage") or ("final_compose" if is_legacy else "")).strip()
    if stage not in COMMERCIAL_STAGE_ORDER:
        raise ProductionRunError(f"unknown commercial stage: {stage!r}")
    kind = str(data.get("kind") or ("final" if is_legacy else "")).strip()
    if not kind:
        raise ProductionRunError("kind must be non-empty")
    artifact_revision = _revision(
        data.get("artifact_revision"),
        "artifact_revision",
        default="legacy-v1" if is_legacy else None,
    )
    batch_id = str(data.get("batch_id") or "").strip()

    expected_raw = data.get("expected_outputs")
    if expected_raw in (None, "") and data.get("output_path"):
        expected_raw = [data["output_path"]]
    if expected_raw in (None, "") and is_legacy:
        expected_raw = ["renders/final.mp4"]
    expected_outputs = _relative_refs(expected_raw, "expected_outputs")

    attempt_raw = data.get("attempt", 1)
    if isinstance(attempt_raw, bool):
        raise ProductionRunError("attempt must be a positive integer")
    try:
        attempt = int(attempt_raw)
    except (TypeError, ValueError) as exc:
        raise ProductionRunError("attempt must be a positive integer") from exc
    if attempt < 1:
        raise ProductionRunError("attempt must be a positive integer")

    status = str(data.get("status") or "queued").strip().lower()
    if status not in JOB_STATUSES:
        raise ProductionRunError(f"unknown produce job status: {status!r}")
    timestamp = _now_iso(now)
    created_at = str(
        data.get("created_at")
        or data.get("started_at")
        or data.get("updated_at")
        or timestamp
    )
    updated_at = str(data.get("updated_at") or created_at)

    normalized = {
        **data,
        "version": JOB_VERSION,
        "project_id": normalized_project_id,
        "run_revision": normalized_run_revision,
        "stage": stage,
        "kind": kind,
        "artifact_revision": artifact_revision,
        "authorization_revision": _optional_revision(
            data.get("authorization_revision")
        ),
        "attempt": attempt,
        "provider": str(data.get("provider") or "").strip(),
        "model": str(data.get("model") or data.get("video_model") or "").strip(),
        "batch_id": batch_id,
        "beat_ids": _string_list(
            data["beat_ids"] if "beat_ids" in data else data.get("beat"),
            "beat_ids",
        ),
        "expected_outputs": expected_outputs,
        "status": status,
        "job_id": str(data.get("job_id") or "").strip(),
        "cost_snapshot": (
            dict(data["cost_snapshot"])
            if isinstance(data.get("cost_snapshot"), dict)
            else {}
        ),
        "created_at": created_at,
        "updated_at": updated_at,
    }
    computed_key = stable_job_key(
        normalized_project_id,
        normalized_run_revision,
        stage,
        kind,
        artifact_revision,
        batch_id,
    )
    supplied_key = str(data.get("job_key") or "").strip()
    if supplied_key and supplied_key != computed_key:
        raise ProductionRunConflictError("produce job_key does not match job identity")
    normalized["job_key"] = computed_key
    if is_legacy:
        normalized["migrated_from_version"] = source_version
    validate_produce_job(normalized)
    return normalized


def build_produce_job(
    *,
    project_id: str,
    run_revision: Any,
    stage: str,
    kind: str,
    artifact_revision: Any,
    authorization_revision: Any = None,
    attempt: int = 1,
    provider: str = "",
    model: str = "",
    batch_id: str = "",
    beat_ids: Iterable[str] = (),
    expected_outputs: Iterable[str] = (),
    status: str = "queued",
    job_id: str = "",
    cost_snapshot: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = _now_iso(now)
    return normalize_produce_job(
        {
            "version": JOB_VERSION,
            "project_id": project_id,
            "run_revision": run_revision,
            "stage": stage,
            "kind": kind,
            "artifact_revision": artifact_revision,
            "authorization_revision": authorization_revision,
            "attempt": attempt,
            "provider": provider,
            "model": model,
            "batch_id": batch_id,
            "beat_ids": list(beat_ids),
            "expected_outputs": list(expected_outputs),
            "status": status,
            "job_id": job_id,
            "cost_snapshot": dict(cost_snapshot or {}),
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        now=timestamp,
    )


def validate_produce_job(data: dict[str, Any]) -> None:
    required = set(_JOB_SUMMARY_FIELDS) | {"version", "project_id", "run_revision"}
    missing = sorted(required.difference(data))
    if missing:
        raise ProductionRunError(f"produce job missing fields: {', '.join(missing)}")
    if data.get("version") != JOB_VERSION:
        raise ProductionRunError(
            f"unsupported produce job version: {data.get('version')!r}"
        )
    expected = stable_job_key(
        data["project_id"],
        data["run_revision"],
        data["stage"],
        data["kind"],
        data["artifact_revision"],
        data["batch_id"],
    )
    if data.get("job_key") != expected:
        raise ProductionRunConflictError("produce job_key does not match job identity")
    if data.get("status") not in JOB_STATUSES:
        raise ProductionRunError(f"unknown produce job status: {data.get('status')!r}")
    attempt = data.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ProductionRunError("attempt must be a positive integer")
    if not isinstance(data.get("beat_ids"), list):
        raise ProductionRunError("beat_ids must be a list")
    expected_outputs = _relative_refs(
        data.get("expected_outputs"), "expected_outputs"
    )
    has_canonical_evidence = any(
        ref.startswith("artifacts/") and ref.endswith(".json")
        for ref in expected_outputs
    )
    if not data.get("migrated_from_version") and not has_canonical_evidence:
        raise ProductionRunError(
            "expected_outputs must include a canonical artifacts/*.json reference"
        )
    if not isinstance(data.get("cost_snapshot"), dict):
        raise ProductionRunError("cost_snapshot must be an object")
    _now_iso(str(data.get("created_at") or ""))
    _now_iso(str(data.get("updated_at") or ""))


def read_produce_job(
    project_dir: Path,
    *,
    run_revision: Any = "1",
) -> dict[str, Any] | None:
    stored = _read_json_strict(produce_job_path(project_dir))
    if stored is None:
        return None
    marker = _read_json_strict(Path(project_dir) / "project.json") or {}
    project_id = (
        marker.get("project_id")
        or stored.get("project_id")
        or Path(project_dir).name
    )
    return normalize_produce_job(
        stored, project_id=str(project_id), run_revision=run_revision
    )


def write_produce_job(project_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    marker = _read_json_strict(Path(project_dir) / "project.json") or {}
    project_id = (
        marker.get("project_id")
        or data.get("project_id")
        or Path(project_dir).name
    )
    normalized = normalize_produce_job(data, project_id=str(project_id))
    _atomic_write_json(produce_job_path(project_dir), normalized)
    return normalized


def new_production_run(
    *,
    project_id: str,
    run_revision: Any = "1",
    review_mode_preset: str | None = None,
    production_tier: str = "light",
    locked_provider: str = "",
    locked_model: str = "",
    source: str = "native",
    now: str | None = None,
) -> dict[str, Any]:
    review_mode = normalize_review_preset(review_mode_preset)
    if review_mode_preset and review_mode is None:
        raise ProductionRunError(f"unknown review_mode_preset: {review_mode_preset!r}")
    tier = str(production_tier or "light").strip().lower()
    if tier not in PRODUCTION_TIERS:
        raise ProductionRunError(f"unknown production_tier: {tier!r}")
    timestamp = _now_iso(now)
    run = {
        "version": RUN_VERSION,
        "project_id": _nonempty(project_id, "project_id"),
        "run_revision": _revision(run_revision, "run_revision"),
        "review_mode_preset": review_mode,
        "production_tier": tier,
        "locked_provider": str(locked_provider or "").strip(),
        "locked_model": str(locked_model or "").strip(),
        "stage_results": {},
        "authorization_refs": [],
        "job_keys": [],
        "task_summaries": [],
        "source": _nonempty(source, "source"),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    validate_production_run(run)
    return run


def validate_production_run(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ProductionRunError("production run must be an object")
    required = {
        "version",
        "project_id",
        "run_revision",
        "review_mode_preset",
        "production_tier",
        "locked_provider",
        "locked_model",
        "stage_results",
        "authorization_refs",
        "job_keys",
        "task_summaries",
        "created_at",
        "updated_at",
    }
    missing = sorted(required.difference(data))
    if missing:
        raise ProductionRunError(f"production run missing fields: {', '.join(missing)}")
    if data.get("version") != RUN_VERSION:
        raise ProductionRunError(
            f"unsupported production run version: {data.get('version')!r}"
        )
    _nonempty(data.get("project_id"), "project_id")
    _revision(data.get("run_revision"), "run_revision")
    review_mode = data.get("review_mode_preset")
    if review_mode is not None and normalize_review_preset(review_mode) is None:
        raise ProductionRunError(f"unknown review_mode_preset: {review_mode!r}")
    if data.get("production_tier") not in PRODUCTION_TIERS:
        raise ProductionRunError(
            f"unknown production_tier: {data.get('production_tier')!r}"
        )

    stage_results = data.get("stage_results")
    if not isinstance(stage_results, dict):
        raise ProductionRunError("stage_results must be an object")
    for stage, result in stage_results.items():
        if stage not in COMMERCIAL_STAGE_ORDER or not isinstance(result, dict):
            raise ProductionRunError(f"invalid stage result: {stage!r}")
        if result.get("status") not in STAGE_RESULT_STATUSES:
            raise ProductionRunError(
                f"invalid stage result status for {stage}: {result.get('status')!r}"
            )
        if result.get("status") == "not_required" and not str(
            result.get("reason") or ""
        ).strip():
            raise ProductionRunError(f"not_required stage {stage} needs a reason")
        _relative_refs(result.get("checkpoint_refs"), "checkpoint_refs")
        _relative_refs(result.get("evidence_refs"), "evidence_refs")

    refs = data.get("authorization_refs")
    if not isinstance(refs, list) or any(not isinstance(item, dict) for item in refs):
        raise ProductionRunError("authorization_refs must be a list of objects")
    for ref in refs:
        _revision(ref.get("authorization_revision"), "authorization_revision")
        _nonempty(ref.get("scope"), "scope")
        if not (ref.get("intent_ref") or ref.get("decision_ref")):
            raise ProductionRunError(
                "authorization ref needs intent_ref or decision_ref"
            )
        for field in ("intent_ref", "decision_ref"):
            if ref.get(field):
                _relative_ref(ref[field], field)
        _now_iso(str(ref.get("created_at") or ""))

    job_keys = data.get("job_keys")
    summaries = data.get("task_summaries")
    if not isinstance(job_keys, list) or any(
        not isinstance(key, str) for key in job_keys
    ):
        raise ProductionRunError("job_keys must be a list of strings")
    if len(job_keys) != len(set(job_keys)):
        raise ProductionRunError("job_keys must be unique")
    if not isinstance(summaries, list) or any(
        not isinstance(item, dict) for item in summaries
    ):
        raise ProductionRunError("task_summaries must be a list of objects")
    summary_keys = [str(item.get("job_key") or "") for item in summaries]
    if summary_keys != job_keys:
        raise ProductionRunError("job_keys must match task_summaries order")
    for summary in summaries:
        missing_summary = sorted(set(_JOB_SUMMARY_FIELDS).difference(summary))
        if missing_summary:
            raise ProductionRunError(
                f"task summary missing fields: {', '.join(missing_summary)}"
            )
        if summary.get("stage") not in COMMERCIAL_STAGE_ORDER:
            raise ProductionRunError(
                f"invalid task summary stage: {summary.get('stage')!r}"
            )
        if summary.get("status") not in JOB_STATUSES:
            raise ProductionRunError(
                f"invalid task summary status: {summary.get('status')!r}"
            )
        summary_outputs = _relative_refs(
            summary.get("expected_outputs"), "expected_outputs"
        )
        summary_has_evidence = any(
            ref.startswith("artifacts/") and ref.endswith(".json")
            for ref in summary_outputs
        )
        if not summary.get("migrated_from_version") and not summary_has_evidence:
            raise ProductionRunError(
                "task summary expected_outputs must include canonical evidence"
            )
        if not isinstance(summary.get("beat_ids"), list):
            raise ProductionRunError("task summary beat_ids must be a list")
        attempt = summary.get("attempt")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ProductionRunError("task summary attempt must be a positive integer")
        if not isinstance(summary.get("cost_snapshot"), dict):
            raise ProductionRunError("task summary cost_snapshot must be an object")
        expected_key = stable_job_key(
            data["project_id"],
            data["run_revision"],
            summary["stage"],
            summary["kind"],
            summary["artifact_revision"],
            summary["batch_id"],
        )
        if summary.get("job_key") != expected_key:
            raise ProductionRunConflictError(
                "task summary job_key does not match job identity"
            )
    _now_iso(str(data.get("created_at") or ""))
    _now_iso(str(data.get("updated_at") or ""))


def read_production_run(project_dir: Path) -> dict[str, Any] | None:
    run = _read_json_strict(production_run_path(project_dir))
    if run is not None:
        validate_production_run(run)
    return run


def write_production_run(project_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    validate_production_run(data)
    marker = _read_json_strict(Path(project_dir) / "project.json")
    if marker and marker.get("project_id") not in (None, data["project_id"]):
        raise ProductionRunError("production run project_id mismatch")
    body = json.loads(json.dumps(data, ensure_ascii=False))
    _atomic_write_json(production_run_path(project_dir), body)
    return body


def mark_stage_not_required(
    data: dict[str, Any],
    stage: str,
    reason: str,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    validate_production_run(data)
    if stage not in COMMERCIAL_STAGE_ORDER:
        raise ProductionRunError(f"unknown commercial stage: {stage!r}")
    updated = json.loads(json.dumps(data, ensure_ascii=False))
    updated["stage_results"][stage] = {
        "status": "not_required",
        "reason": _nonempty(reason, "reason"),
        "checkpoint_refs": [],
        "evidence_refs": [],
    }
    updated["updated_at"] = _now_iso(now)
    validate_production_run(updated)
    return updated


def record_stage_result(
    data: dict[str, Any],
    stage: str,
    status: str,
    *,
    checkpoint_refs: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    human_approved: bool | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Record only references to canonical stage facts in the run summary."""
    validate_production_run(data)
    if stage not in COMMERCIAL_STAGE_ORDER:
        raise ProductionRunError(f"unknown commercial stage: {stage!r}")
    if status not in STAGE_RESULT_STATUSES - {"not_required"}:
        raise ProductionRunError(f"invalid stage result status: {status!r}")
    result: dict[str, Any] = {
        "status": status,
        "checkpoint_refs": _relative_refs(checkpoint_refs, "checkpoint_refs"),
        "evidence_refs": _relative_refs(evidence_refs, "evidence_refs"),
    }
    if human_approved is not None:
        result["human_approved"] = bool(human_approved)
    updated = json.loads(json.dumps(data, ensure_ascii=False))
    updated["stage_results"][stage] = result
    updated["updated_at"] = _now_iso(now)
    validate_production_run(updated)
    return updated


def add_authorization_ref(
    data: dict[str, Any],
    *,
    authorization_revision: Any,
    scope: str,
    intent_ref: str = "",
    decision_ref: str = "",
    now: str | None = None,
) -> dict[str, Any]:
    validate_production_run(data)
    ref = {
        "authorization_revision": _revision(
            authorization_revision, "authorization_revision"
        ),
        "scope": _nonempty(scope, "scope"),
        "intent_ref": _relative_ref(intent_ref, "intent_ref") if intent_ref else "",
        "decision_ref": (
            _relative_ref(decision_ref, "decision_ref") if decision_ref else ""
        ),
        "created_at": _now_iso(now),
    }
    if not (ref["intent_ref"] or ref["decision_ref"]):
        raise ProductionRunError("authorization ref needs intent_ref or decision_ref")
    updated = json.loads(json.dumps(data, ensure_ascii=False))
    existing = next(
        (
            item
            for item in updated["authorization_refs"]
            if item.get("authorization_revision") == ref["authorization_revision"]
        ),
        None,
    )
    if existing is not None:
        immutable_fields = ("scope", "intent_ref", "decision_ref")
        if any(existing.get(field) != ref.get(field) for field in immutable_fields):
            raise ProductionRunConflictError(
                "authorization revision already refers to different evidence"
            )
    if existing is None:
        updated["authorization_refs"].append(ref)
        updated["updated_at"] = ref["created_at"]
    validate_production_run(updated)
    return updated


def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
    summary = {field: job[field] for field in _JOB_SUMMARY_FIELDS}
    if job.get("migrated_from_version"):
        summary["migrated_from_version"] = job["migrated_from_version"]
    return summary


def register_job_summary(
    data: dict[str, Any],
    job: dict[str, Any],
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Insert/update a compact job projection, rejecting key-content clashes."""

    validate_production_run(data)
    validate_produce_job(job)
    if (
        job["project_id"] != data["project_id"]
        or job["run_revision"] != data["run_revision"]
    ):
        raise ProductionRunConflictError("job does not belong to this production run")
    summary = _job_summary(job)
    updated = json.loads(json.dumps(data, ensure_ascii=False))
    try:
        index = updated["job_keys"].index(job["job_key"])
    except ValueError:
        updated["job_keys"].append(job["job_key"])
        updated["task_summaries"].append(summary)
    else:
        existing = updated["task_summaries"][index]
        if any(
            existing.get(field) != summary.get(field)
            for field in _JOB_IDENTITY_FIELDS
        ):
            raise ProductionRunConflictError(
                "stable job key already refers to different task content"
            )
        existing_attempt = int(existing.get("attempt") or 0)
        next_attempt = int(summary.get("attempt") or 0)
        authorization_changed = existing.get(
            "authorization_revision"
        ) != summary.get("authorization_revision")
        if next_attempt < existing_attempt:
            raise ProductionRunConflictError(
                "stale attempt cannot replace a newer job summary"
            )
        if authorization_changed and next_attempt <= existing_attempt:
            raise ProductionRunConflictError(
                "authorization revision may change only on a later attempt"
            )
        updated["task_summaries"][index] = summary
    updated["updated_at"] = _now_iso(now)
    validate_production_run(updated)
    return updated


def _checkpoint_result(checkpoint: dict[str, Any], ref: str) -> dict[str, Any] | None:
    status = str(checkpoint.get("status") or "").strip()
    if status not in STAGE_RESULT_STATUSES - {"not_required", "paused"}:
        return None
    result: dict[str, Any] = {
        "status": status,
        "checkpoint_refs": [ref],
        "evidence_refs": [],
    }
    if "human_approved" in checkpoint:
        result["human_approved"] = bool(checkpoint.get("human_approved"))
    return result


def initialize_legacy_production_run(
    project_dir: Path,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Build, but do not persist, a run summary for an old project."""

    project_dir = Path(project_dir)
    marker = _read_json_strict(project_dir / "project.json")
    if marker is None:
        raise ProductionRunError(
            f"missing project marker: {project_dir / 'project.json'}"
        )
    project_id = str(marker.get("project_id") or project_dir.name)
    profile = marker.get("production_profile")
    if not isinstance(profile, dict):
        profile = {}
    run = new_production_run(
        project_id=project_id,
        run_revision=profile.get("run_revision") or marker.get("run_revision") or "1",
        review_mode_preset=(
            profile.get("review_mode_preset") or profile.get("review_mode") or None
        ),
        production_tier=str(profile.get("production_tier") or "light"),
        locked_provider=str(
            profile.get("provider") or profile.get("video_channel") or ""
        ),
        locked_model=str(profile.get("video_model") or profile.get("model") or ""),
        source="legacy_lazy_init",
        now=now,
    )
    warnings: list[str] = []

    if run["review_mode_preset"] == "minimal":
        for stage in ("sample_review", "draft_review"):
            run = mark_stage_not_required(
                run, stage, "minimal_review_policy", now=now
            )

    for stage in COMMERCIAL_STAGE_ORDER:
        rel = f"checkpoint_{stage}.json"
        checkpoint = _read_json_for_migration(
            project_dir / rel, warnings, warning_ref=rel
        )
        if checkpoint is None:
            continue
        result = _checkpoint_result(checkpoint, rel)
        if result is not None:
            run["stage_results"][stage] = result

    for stage, refs in _ARTIFACT_STAGE_REFS.items():
        present = [ref for ref in refs if (project_dir / ref).is_file()]
        if not present:
            continue
        result = run["stage_results"].setdefault(
            stage,
            {"status": "pending", "checkpoint_refs": [], "evidence_refs": []},
        )
        result["evidence_refs"] = sorted(
            set(result.get("evidence_refs") or []).union(present)
        )

    final_path = project_dir / "renders" / "final.mp4"
    if final_path.is_file() and final_path.stat().st_size > 0:
        final = run["stage_results"].setdefault(
            "final_compose",
            {"status": "completed", "checkpoint_refs": [], "evidence_refs": []},
        )
        final["status"] = "completed"
        final["evidence_refs"] = sorted(
            set(final.get("evidence_refs") or []).union({"renders/final.mp4"})
        )
        run["legacy_final_detected"] = True

    job_stored = _read_json_for_migration(
        produce_job_path(project_dir),
        warnings,
        warning_ref=PRODUCE_JOB_REL.as_posix(),
    )
    if job_stored is not None:
        try:
            job = normalize_produce_job(
                job_stored,
                project_id=project_id,
                run_revision=run["run_revision"],
                now=now,
            )
            run = register_job_summary(run, job, now=now)
        except ProductionRunError:
            warnings.append(PRODUCE_JOB_REL.as_posix())

    if warnings:
        run["migration_warnings"] = sorted(set(warnings))
    run["updated_at"] = _now_iso(now)
    validate_production_run(run)
    return run


def load_or_initialize_production_run(
    project_dir: Path,
    *,
    persist: bool = False,
    now: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Load a run or lazily initialize one; caller explicitly controls writing."""

    existing = read_production_run(project_dir)
    if existing is not None:
        return existing, False
    initialized = initialize_legacy_production_run(project_dir, now=now)
    if persist:
        write_production_run(project_dir, initialized)
    return initialized, True


def expected_outputs_complete(
    project_dir: Path,
    expected_outputs: Iterable[str],
) -> tuple[bool, list[str]]:
    refs = _relative_refs(list(expected_outputs), "expected_outputs")
    if not refs:
        return False, []
    missing: list[str] = []
    root = Path(project_dir)
    for ref in refs:
        path = root / ref
        try:
            ready = path.is_file() and path.stat().st_size > 0
        except OSError:
            ready = False
        if not ready:
            missing.append(ref)
    return not missing, missing


def reconcile_orphaned_job(
    data: dict[str, Any],
    project_dir: Path,
    *,
    background_job_exists: bool,
    now: str | None = None,
) -> dict[str, Any]:
    """Converge a lost queued/running job without ever retrying it."""

    job = normalize_produce_job(data, now=now)
    if job["status"] not in ACTIVE_JOB_STATUSES or background_job_exists:
        return job
    complete, missing = expected_outputs_complete(
        project_dir, job["expected_outputs"]
    )
    updated = dict(job)
    timestamp = _now_iso(now)
    updated["updated_at"] = timestamp
    updated["recovered_without_retry"] = True
    if complete:
        updated["status"] = "done"
        updated["orphaned"] = False
        updated["recovery_code"] = "expected_outputs_complete"
        updated["finished_at"] = timestamp
        updated.pop("missing_outputs", None)
    else:
        updated["status"] = "paused"
        updated["orphaned"] = True
        updated["code"] = "orphaned"
        updated["recovery_code"] = "background_job_missing"
        updated["missing_outputs"] = missing
        updated["paused_at"] = timestamp
    validate_produce_job(updated)
    return updated
