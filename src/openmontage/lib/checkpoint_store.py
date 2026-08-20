"""Checkpoint file store: lock, write, merge, read, and artifact transactions."""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from lib.checkpoint_validate import (
    ALL_KNOWN_STAGES,
    CheckpointValidationError,
    PROJECT_MARKER_FILENAME,
    STAGES,
    get_pipeline_stages,
    validate_checkpoint,
)
from lib.persistence.json_store import JsonStore


def _projects_dir():
    facade = sys.modules.get("lib.checkpoint")
    if facade is not None:
        current = getattr(facade, "PROJECTS_DIR", None)
        if current is not None:
            return current
    from lib.paths import PROJECTS_DIR

    return PROJECTS_DIR

HISTORY_DIRNAME = "history"

CHECKPOINT_LOCK_FILENAME = ".checkpoint.lock"

CHECKPOINT_LOCK_TIMEOUT_SECONDS = 10.0

CHECKPOINT_LOCK_POLL_SECONDS = 0.02


@contextmanager
def _project_checkpoint_lock(pipeline_dir: Path, project_id: str):
    """Serialize one project's checkpoint transaction with an OS-owned lock."""
    from lib.persistence.file_lock import CheckpointLockTimeout, project_checkpoint_lock

    try:
        with project_checkpoint_lock(
            pipeline_dir,
            project_id,
            timeout=CHECKPOINT_LOCK_TIMEOUT_SECONDS,
            poll_seconds=CHECKPOINT_LOCK_POLL_SECONDS,
            lock_filename=CHECKPOINT_LOCK_FILENAME,
        ):
            yield
    except CheckpointLockTimeout as exc:
        raise CheckpointValidationError(str(exc)) from exc

def _checkpoint_path(pipeline_dir: Path, project_id: str, stage: str) -> Path:
    return pipeline_dir / project_id / f"checkpoint_{stage}.json"

def init_project(
    project_id: str,
    *,
    title: str,
    pipeline_type: str,
    pipeline_dir: Optional[Path] = None,
    style_playbook: Optional[str] = None,
) -> Path:
    """Initialize a project workspace with the canonical layout + marker file.

    Creates projects/<project_id>/ with the standard subdirectories and writes
    project.json — the marker the Backlot board uses to render a project's
    identity and stage rail before the first checkpoint exists.

    Idempotent: re-running preserves the original created_at and merges fields.
    Returns the project directory.
    """
    base = pipeline_dir or _projects_dir()
    project_dir = base / project_id
    for sub in (
        "artifacts",
        "assets/images",
        "assets/video",
        "assets/audio",
        "assets/music",
        "assets/copy",
        "assets/subs",
        "assets/stock",
        "renders",
        "exports",
    ):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    marker_path = project_dir / PROJECT_MARKER_FILENAME
    try:
        loaded = JsonStore.read_object(marker_path, missing="empty")
    except (json.JSONDecodeError, OSError, ValueError):
        loaded = {}
    marker = dict(loaded or {})
    marker.setdefault("version", "1.0")
    marker.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    marker["project_id"] = project_id
    marker["title"] = title
    marker["pipeline_type"] = pipeline_type
    if style_playbook is not None:
        marker["style_playbook"] = style_playbook
    JsonStore.write_atomic(marker_path, marker)

    return project_dir

def _stage_requires_approval(pipeline_type: Optional[str], stage: str) -> Optional[bool]:
    """Read human_approval_default for a stage from its pipeline manifest.

    Returns None when the stage isn't declared in the manifest or no
    pipeline_type was given — the caller then falls back to the value the
    agent passed in.

    A *provided but unknown* pipeline_type raises: a typo must not silently
    disable gate enforcement (fail-closed, not fail-open). Other manifest
    load failures are logged and fall back — a corrupt manifest shouldn't
    strand an otherwise-valid run, but the degradation must be visible.
    """
    if not pipeline_type or pipeline_type == "unknown":
        return None
    from lib.pipeline_loader import get_stage_human_approval_default, load_pipeline_readonly
    try:
        manifest = load_pipeline_readonly(pipeline_type)
    except FileNotFoundError:
        raise CheckpointValidationError(
            f"Unknown pipeline_type {pipeline_type!r} — cannot resolve gate "
            f"policy for stage {stage!r}. Check the spelling against "
            f"product/pipelines/*.yaml."
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Gate policy unavailable for pipeline %r (%s) — falling back to "
            "the caller's human_approval_required flag.", pipeline_type, exc,
        )
        return None
    return get_stage_human_approval_default(manifest, stage)

def _enforce_commercial_stage_order(
    pipeline_dir: Path,
    project_id: str,
    pipeline_type: Optional[str],
    stage: str,
    status: str,
) -> None:
    """Require every prior commercial stage's current checkpoint to be completed."""
    if pipeline_type != "bootstrap-commercial" or status not in {
        "in_progress",
        "awaiting_human",
        "completed",
        "failed",
    }:
        return

    stages = get_pipeline_stages(pipeline_type)
    prior_stages = stages[: stages.index(stage)]

    confirm_stages: set[str] | None = None
    marker_path = pipeline_dir / project_id / PROJECT_MARKER_FILENAME
    try:
        from lib.review_interrupt import confirm_stop_ids, normalize_review_preset

        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        profile = (
            marker.get("production_profile")
            if isinstance(marker, dict)
            else {}
        )
        if not isinstance(profile, dict):
            profile = {}
        preset = normalize_review_preset(
            profile.get("review_mode_preset") or profile.get("review_mode")
        )
        if preset:
            confirm_stages = set(confirm_stop_ids(preset))
    except (OSError, json.JSONDecodeError, UnicodeError, ValueError):
        confirm_stages = None

    if confirm_stages is not None:
        prior_stages = [name for name in prior_stages if name in confirm_stages]

    incomplete: list[str] = []
    for prior_stage in prior_stages:
        path = _checkpoint_path(pipeline_dir, project_id, prior_stage)
        try:
            with open(path, encoding="utf-8") as f:
                prior = json.load(f)
        except (OSError, json.JSONDecodeError):
            prior = None
        if not isinstance(prior, dict) or prior.get("status") != "completed":
            incomplete.append(prior_stage)

    if incomplete:
        raise CheckpointValidationError(
            f"商品片阶段顺序违规：写入阶段 {stage!r} 的 {status!r} 状态前，"
            f"未完成前序阶段：{', '.join(incomplete)}。"
        )

def _required_inline_manifest_outputs(
    pipeline_type: Optional[str],
    stage: str,
    status: str,
    artifacts: dict[str, Any],
) -> set[str]:
    """Return required manifest outputs supplied as inline JSON objects."""
    if (
        pipeline_type in {None, "", "unknown"}
        or status not in {"completed", "awaiting_human"}
    ):
        return set()
    from lib.pipeline_loader import load_pipeline_readonly

    manifest = load_pipeline_readonly(pipeline_type)
    stage_def = next(
        (item for item in manifest.get("stages", []) if item.get("name") == stage),
        {},
    )
    return {
        name
        for name in stage_def.get("produces", [])
        if isinstance(artifacts.get(name), dict)
    }

def _archive_superseded_checkpoint(path: Path, stage: str) -> Optional[Path]:
    """Copy an existing checkpoint into history/ before it is overwritten.

    Preserves the full run record: stage re-runs (script v1 → v2) and gate
    transitions (awaiting_human → completed) remain reconstructable. Repeated
    in_progress refreshes are NOT archived — they are partial-progress
    heartbeats, not versions.

    Archiving is best-effort and must never crash a checkpoint write: the
    Backlot watcher may hold the file open (Windows denies renames of open
    files), so we copy rather than move, and swallow archival I/O failures.
    """
    if not path.exists():
        return None
    try:
        with open(path) as f:
            existing = json.load(f)
    except (json.JSONDecodeError, OSError):
        existing = {}
    if existing.get("status") == "in_progress":
        return None

    try:
        import shutil
        stamp = str(existing.get("timestamp", ""))
        safe_stamp = "".join(c for c in stamp if c.isalnum()) or f"{path.stat().st_mtime_ns}"
        history_dir = path.parent / HISTORY_DIRNAME
        history_dir.mkdir(parents=True, exist_ok=True)
        target = history_dir / f"checkpoint_{stage}_{safe_stamp}.json"
        if target.exists():
            target = history_dir / f"checkpoint_{stage}_{safe_stamp}_{path.stat().st_mtime_ns}.json"
        shutil.copyfile(path, target)
        return target
    except OSError:
        import logging
        logging.getLogger(__name__).warning(
            "Could not archive superseded checkpoint %s to history/", path
        )
        return None

def _decision_log_path(pipeline_dir: Path, project_id: str) -> Path:
    return pipeline_dir / project_id / "decision_log.json"

def _resolve_checkpoint_pipeline_type(
    pipeline_dir: Path,
    project_id: str,
    supplied_pipeline_type: Optional[str],
) -> Optional[str]:
    """Make a known project marker authoritative for checkpoint writes."""
    marker_path = pipeline_dir / project_id / PROJECT_MARKER_FILENAME
    marker_pipeline_type: Optional[str] = None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        candidate = (
            str(marker.get("pipeline_type") or "").strip()
            if isinstance(marker, dict)
            else ""
        )
        if candidate and candidate != "unknown":
            from lib.pipeline_loader import load_pipeline_readonly

            load_pipeline_readonly(candidate)
            marker_pipeline_type = candidate
    except (OSError, json.JSONDecodeError, FileNotFoundError, ValueError):
        marker_pipeline_type = None

    supplied = str(supplied_pipeline_type or "").strip()
    if marker_pipeline_type:
        if supplied in {"", "unknown"}:
            return marker_pipeline_type
        if supplied != marker_pipeline_type:
            raise CheckpointValidationError(
                f"pipeline_type {supplied!r} conflicts with authoritative "
                f"project marker pipeline_type {marker_pipeline_type!r}"
            )
        return marker_pipeline_type
    return supplied_pipeline_type or None

def _merge_decision_log(
    pipeline_dir: Path, project_id: str, new_log: dict[str, Any]
) -> int:
    """Append new decisions to the project-level decision log.

    Each stage may produce decisions. This function merges them into a
    single cumulative file so reviewers and the bench can inspect the
    full audit trail.
    """
    with _project_checkpoint_lock(pipeline_dir, project_id):
        path = _decision_log_path(pipeline_dir, project_id)
        existing = _read_decision_log(path, project_id)
        merged = _merge_decision_log_data(
            existing,
            new_log,
            project_id,
        )
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            _best_effort_unlink(temporary)
        return len(merged["decisions"]) - len(existing.get("decisions") or [])

def _read_decision_log(path: Path, project_id: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": "1.0",
            "project_id": project_id,
            "decisions": [],
        }
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise CheckpointValidationError(
            "Existing project decision_log.json is unreadable"
        ) from exc
    if not isinstance(existing, dict) or not isinstance(
        existing.get("decisions"), list
    ):
        raise CheckpointValidationError(
            "Existing project decision_log.json must contain decisions"
        )
    return existing

def _merge_decision_log_data(
    existing: dict[str, Any],
    new_log: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    """Pure append-only merge with decision_id deduplication."""
    merged = {
        **existing,
        "version": str(existing.get("version") or "1.0"),
        "project_id": str(existing.get("project_id") or project_id),
        "decisions": list(existing.get("decisions") or []),
    }
    existing_by_id = {
        decision.get("decision_id"): decision
        for decision in merged["decisions"]
        if isinstance(decision, dict) and decision.get("decision_id")
    }
    for decision in new_log.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        decision_id = decision.get("decision_id")
        previous = existing_by_id.get(decision_id)
        if previous is not None:
            if previous != decision:
                raise CheckpointValidationError(
                    "decision_id conflicts with an existing append-only decision"
                )
            continue
        merged["decisions"].append(decision)
        existing_by_id[decision_id] = decision
    return merged

def write_checkpoint(
    pipeline_dir: Path,
    project_id: str,
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    *,
    pipeline_type: Optional[str] = None,
    style_playbook: Optional[str] = None,
    checkpoint_policy: str = "guided",
    human_approval_required: bool = False,
    human_approved: bool = False,
    review: Optional[dict] = None,
    cost_snapshot: Optional[dict] = None,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Path:
    """Write one fully serialized, rollback-safe project checkpoint."""
    with _project_checkpoint_lock(pipeline_dir, project_id):
        return _write_checkpoint_locked(
            pipeline_dir,
            project_id,
            stage,
            status,
            artifacts,
            pipeline_type=pipeline_type,
            style_playbook=style_playbook,
            checkpoint_policy=checkpoint_policy,
            human_approval_required=human_approval_required,
            human_approved=human_approved,
            review=review,
            cost_snapshot=cost_snapshot,
            error=error,
            metadata=metadata,
        )

def merge_write_checkpoint(
    pipeline_dir: Path,
    project_id: str,
    stage: str,
    status: str,
    artifacts_patch: dict[str, Any],
    *,
    pipeline_type: Optional[str] = None,
    style_playbook: Optional[str] = None,
    checkpoint_policy: str = "guided",
    human_approval_required: bool = False,
    human_approved: bool = False,
    review: Optional[dict] = None,
    cost_snapshot_patch: Optional[dict] = None,
    error: Optional[str] = None,
    metadata_patch: Optional[dict] = None,
    metadata_remove_keys: tuple[str, ...] = (),
    project_marker_builder: Optional[
        Callable[[dict[str, Any]], Optional[dict[str, Any]]]
    ] = None,
) -> tuple[Path, dict[str, Any], Optional[dict[str, Any]]]:
    """Merge a partial checkpoint update and commit it under one project lock."""
    with _project_checkpoint_lock(pipeline_dir, project_id):
        current = read_checkpoint(pipeline_dir, project_id, stage)
        current = current if isinstance(current, dict) else {}
        artifacts = merge_checkpoint_artifacts(
            current.get("artifacts"),
            artifacts_patch,
        )
        metadata = {
            **(
                current.get("metadata")
                if isinstance(current.get("metadata"), dict)
                else {}
            )
        }
        for key in metadata_remove_keys:
            metadata.pop(key, None)
        metadata.update(metadata_patch or {})
        current_cost = (
            current.get("cost_snapshot")
            if isinstance(current.get("cost_snapshot"), dict)
            else {}
        )
        cost_snapshot = {**current_cost, **(cost_snapshot_patch or {})}
        effective_pipeline_type = (
            pipeline_type
            or str(current.get("pipeline_type") or "")
            or None
        )
        effective_style_playbook = (
            style_playbook
            if style_playbook is not None
            else current.get("style_playbook")
        )
        project_marker = (
            project_marker_builder(artifacts)
            if project_marker_builder is not None
            else None
        )
        path = _write_checkpoint_locked(
            pipeline_dir,
            project_id,
            stage,
            status,
            artifacts,
            pipeline_type=effective_pipeline_type,
            style_playbook=effective_style_playbook,
            checkpoint_policy=checkpoint_policy,
            human_approval_required=human_approval_required,
            human_approved=human_approved,
            review=review,
            cost_snapshot=cost_snapshot or None,
            error=error,
            metadata=metadata or None,
            project_marker=project_marker,
        )
        written = read_checkpoint(pipeline_dir, project_id, stage)
        if written is None:
            raise CheckpointValidationError(
                f"Checkpoint {stage!r} disappeared after commit"
            )
        return path, written, project_marker

def _write_checkpoint_locked(
    pipeline_dir: Path,
    project_id: str,
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    *,
    pipeline_type: Optional[str] = None,
    style_playbook: Optional[str] = None,
    checkpoint_policy: str = "guided",
    human_approval_required: bool = False,
    human_approved: bool = False,
    review: Optional[dict] = None,
    cost_snapshot: Optional[dict] = None,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
    project_marker: Optional[dict[str, Any]] = None,
) -> Path:
    """Write a checkpoint file for a pipeline stage."""
    pipeline_type = _resolve_checkpoint_pipeline_type(
        pipeline_dir,
        project_id,
        pipeline_type,
    )

    valid_stages = (
        set(get_pipeline_stages(pipeline_type)) if pipeline_type
        else ALL_KNOWN_STAGES
    )
    if stage not in valid_stages:
        raise ValueError(
            f"Invalid stage: {stage!r} for pipeline {pipeline_type!r}. "
            f"Valid stages: {sorted(valid_stages)}"
        )
    _enforce_commercial_stage_order(
        pipeline_dir,
        project_id,
        pipeline_type,
        stage,
        status,
    )

    # --- Gate enforcement (GI-4) ---
    # The pipeline manifest is the binding source of truth for whether a stage
    # gates on human approval; a caller may gate MORE strictly (e.g. a
    # manual_all checkpoint policy) but never less. A gated stage can only be
    # written "completed" with explicit evidence of approval
    # (human_approved=True). Skipping a gate is a hard error.
    #
    # Enforcement happens at write time only: pre-existing checkpoints written
    # before gating (or by hand) still read as completed — deliberate
    # back-compat so in-flight and legacy projects keep resuming.
    manifest_gate = _stage_requires_approval(pipeline_type, stage)
    gated = bool(manifest_gate) or human_approval_required
    if gated:
        human_approval_required = True
        if status == "completed" and not human_approved:
            gate_source = (
                f"human_approval_default: true in the {pipeline_type!r} manifest"
                if manifest_gate
                else "human_approval_required=True was passed by the caller"
            )
            raise CheckpointValidationError(
                f"GATE VIOLATION: stage {stage!r} requires human approval "
                f"({gate_source}) but status='completed' was written without "
                f"human_approved=True. Correct protocol: write "
                f"status='awaiting_human', present the artifact summary to the "
                f"user, END YOUR TURN, and only after the user approves "
                f"re-write with status='completed', human_approved=True."
            )

    artifacts = dict(artifacts)
    merged_decision_log: Optional[dict[str, Any]] = None
    if isinstance(artifacts.get("decision_log"), dict):
        merged_decision_log = _merge_decision_log_data(
            _read_decision_log(
                _decision_log_path(pipeline_dir, project_id),
                project_id,
            ),
            artifacts["decision_log"],
            project_id,
        )
        artifacts["decision_log"] = merged_decision_log
        log_ref = str(_decision_log_path(pipeline_dir, project_id))
        for artifact_key in ("proposal_packet", "render_report"):
            if artifact_key in artifacts and isinstance(artifacts[artifact_key], dict):
                plan_or_top = artifacts[artifact_key]
                if artifact_key == "proposal_packet":
                    plan = plan_or_top.get("production_plan")
                    if isinstance(plan, dict):
                        plan["decision_log_ref"] = log_ref
                else:
                    plan_or_top["decision_log_ref"] = log_ref

    checkpoint = {
        "version": "1.0",
        "project_id": project_id,
        "pipeline_type": pipeline_type or "unknown",
        "stage": stage,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checkpoint_policy": checkpoint_policy,
        "human_approval_required": human_approval_required,
        "human_approved": human_approved,
        "artifacts": artifacts,
    }
    if style_playbook is not None:
        checkpoint["style_playbook"] = style_playbook
    if review is not None:
        checkpoint["review"] = review
    if cost_snapshot is not None:
        checkpoint["cost_snapshot"] = cost_snapshot
    if error is not None:
        checkpoint["error"] = error
    if metadata is not None:
        checkpoint["metadata"] = metadata

    validate_checkpoint(
        checkpoint,
        project_dir=pipeline_dir / project_id,
        enforce_pipeline_outputs=True,
    )

    path = _checkpoint_path(pipeline_dir, project_id, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    project_root = pipeline_dir / project_id
    required_inline = _required_inline_manifest_outputs(
        pipeline_type,
        stage,
        status,
        artifacts,
    )
    transactional_inline = set(required_inline)
    if merged_decision_log is not None:
        transactional_inline.add("decision_log")
    required_transaction: list[dict[str, Any]] = []
    if transactional_inline or project_marker is not None:
        try:
            required_transaction = _prepare_required_artifacts(
                project_root,
                {name: artifacts[name] for name in transactional_inline},
                root_decision_log=merged_decision_log,
                project_marker=project_marker,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise CheckpointValidationError(
                "required manifest artifacts failed to materialize: "
                f"{sorted(transactional_inline)}"
            ) from exc
    # Serialize to a temp file first so a mid-write failure (disk full,
    # unserializable metadata) can never leave the stage with a truncated
    # current checkpoint; then archive the superseded file and swap in the
    # new one atomically.
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2)
    except Exception:
        _cleanup_required_artifact_transaction(required_transaction)
        _best_effort_unlink(tmp_path)
        raise

    try:
        _commit_required_artifacts(required_transaction)
    except (OSError, CheckpointValidationError) as exc:
        _best_effort_unlink(tmp_path)
        if isinstance(exc, CheckpointValidationError):
            raise
        raise CheckpointValidationError(
            "required manifest artifacts failed to materialize: "
            f"{sorted(transactional_inline)}"
        ) from exc

    # Preserve run history: a superseded completed/awaiting_human checkpoint
    # is copied to history/ (stage versioning, gate audit trail, replay).
    archived_path = _archive_superseded_checkpoint(path, stage)
    try:
        os.replace(tmp_path, path)
    except OSError as exc:
        rollback_error: Optional[CheckpointValidationError] = None
        try:
            _rollback_required_artifacts(required_transaction)
        except CheckpointValidationError as rollback_exc:
            rollback_error = rollback_exc
        _best_effort_unlink(tmp_path)
        if archived_path is not None:
            _best_effort_unlink(archived_path)
        if rollback_error is not None:
            raise CheckpointValidationError(
                f"Checkpoint {stage!r} failed to commit and artifact rollback "
                f"was incomplete: {rollback_error}"
            ) from exc
        raise CheckpointValidationError(
            f"Checkpoint {stage!r} failed to commit; prior state was restored"
        ) from exc
    _finalize_required_artifacts(required_transaction)

    _materialize_artifacts(
        project_root,
        {
            name: value
            for name, value in artifacts.items()
            if name not in transactional_inline
        },
    )

    return path

_MATERIALIZE_ARTIFACT_FILES = {
    "brief": "brief.json",
    "video_plan": "video_plan.json",
    "asset_precheck": "asset_precheck.json",
    "asset_ledger": "asset_ledger.json",
    "asset_vision": "asset_vision.json",
    "segment_cards": "segment_cards.json",
    "review_overview": "review_overview.json",
    "sample_reel": "sample_reel.json",
    "full_draft_pro": "full_draft_pro.json",
    "cost_log": "cost_log.json",
    "decision_log": "decision_log.json",
    "batch01_review": "batch01_review.json",
    "batch02_review": "batch02_review.json",
}

def _artifact_materialization_filename(name: str) -> Optional[str]:
    filename = _MATERIALIZE_ARTIFACT_FILES.get(name)
    if filename:
        return filename
    if name.replace("_", "").isalnum():
        return f"{name}.json"
    return None

def _prepare_required_artifacts(
    project_dir: Path,
    artifacts: dict[str, dict[str, Any]],
    *,
    root_decision_log: Optional[dict[str, Any]] = None,
    project_marker: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Serialize all required inline artifacts before touching current files."""
    if (
        not artifacts
        and root_decision_log is None
        and project_marker is None
    ):
        return []
    art_dir = project_dir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    transaction: list[dict[str, Any]] = []

    def prepare_entry(name: str, target: Path, payload: dict[str, Any]) -> None:
        token = uuid4().hex
        entry = {
            "name": name,
            "target": target,
            "temp": target.parent / f".{target.name}.{token}.tmp",
            "rollback_temp": (
                target.parent / f".{target.name}.{token}.rollback.tmp"
            ),
            "original_bytes": target.read_bytes() if target.exists() else None,
            "installed": False,
        }
        transaction.append(entry)
        entry["temp"].write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    try:
        for name in sorted(artifacts):
            filename = _artifact_materialization_filename(name)
            if filename is None:
                raise ValueError(f"Unsafe artifact name: {name!r}")
            prepare_entry(
                name,
                art_dir / filename,
                artifacts[name],
            )
        if root_decision_log is not None:
            prepare_entry(
                "root_decision_log",
                project_dir / "decision_log.json",
                root_decision_log,
            )
        if project_marker is not None:
            prepare_entry(
                "project_marker",
                project_dir / PROJECT_MARKER_FILENAME,
                project_marker,
            )
    except Exception:
        _cleanup_required_artifact_transaction(transaction)
        raise
    return transaction

def _commit_required_artifacts(transaction: list[dict[str, Any]]) -> None:
    """Replace required artifact targets, rolling all of them back on failure."""
    try:
        for entry in transaction:
            target = entry["target"]
            os.replace(entry["temp"], target)
            entry["installed"] = True
    except OSError as exc:
        try:
            _rollback_required_artifacts(transaction)
        except CheckpointValidationError as rollback_exc:
            raise CheckpointValidationError(
                "required manifest artifacts failed to materialize and rollback "
                f"was incomplete: {rollback_exc}"
            ) from exc
        raise CheckpointValidationError(
            "required manifest artifacts failed to materialize"
        ) from exc

def _rollback_required_artifacts(transaction: list[dict[str, Any]]) -> None:
    """Restore every required artifact target to its pre-call state."""
    errors: list[str] = []
    for entry in reversed(transaction):
        target = entry["target"]
        try:
            if entry["installed"]:
                original_bytes = entry["original_bytes"]
                if original_bytes is None:
                    target.unlink(missing_ok=True)
                else:
                    rollback_temp = entry["rollback_temp"]
                    rollback_temp.write_bytes(original_bytes)
                    os.replace(rollback_temp, target)
        except OSError as exc:
            errors.append(f"{entry['name']}: {exc}")
        finally:
            _best_effort_unlink(entry["temp"])
            _best_effort_unlink(entry["rollback_temp"])
    if errors:
        raise CheckpointValidationError("; ".join(errors))

def _best_effort_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

def _cleanup_required_artifact_transaction(
    transaction: list[dict[str, Any]],
) -> None:
    """Remove prepared files, restoring targets if commit had started."""
    if any(entry["installed"] for entry in transaction):
        _rollback_required_artifacts(transaction)
        return
    for entry in transaction:
        _best_effort_unlink(entry["temp"])
        _best_effort_unlink(entry["rollback_temp"])

def _finalize_required_artifacts(transaction: list[dict[str, Any]]) -> None:
    """Best-effort cleanup after a successful commit; never reverse success."""
    for entry in transaction:
        _best_effort_unlink(entry["temp"])
        _best_effort_unlink(entry["rollback_temp"])

def _materialize_artifacts(project_dir: Path, artifacts: dict[str, Any]) -> list[str]:
    """Write inline dict artifacts to artifacts/<name>.json. Skip path strings."""
    if not isinstance(artifacts, dict) or not artifacts:
        return []
    art_dir = project_dir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, value in artifacts.items():
        if not isinstance(value, dict):
            continue
        filename = _artifact_materialization_filename(name)
        if filename is None:
            continue
        target = art_dir / filename
        try:
            target.write_text(
                json.dumps(value, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written.append(name)
        except OSError:
            continue
    return written

def merge_checkpoint_artifacts(
    current_artifacts: dict[str, Any] | None,
    supplied_artifacts: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge stage artifacts so a partial write cannot drop prior evidence keys."""
    base = dict(current_artifacts or {})
    for key, value in (supplied_artifacts or {}).items():
        if value is None:
            continue
        base[key] = value
    return base

def read_checkpoint(
    pipeline_dir: Path, project_id: str, stage: str
) -> Optional[dict[str, Any]]:
    """Read a checkpoint file. Returns None if not found."""
    path = _checkpoint_path(pipeline_dir, project_id, stage)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        checkpoint = json.load(f)
    validate_checkpoint(checkpoint, project_dir=pipeline_dir / project_id)
    return checkpoint

def get_latest_checkpoint(
    pipeline_dir: Path, project_id: str
) -> Optional[dict[str, Any]]:
    """Find the most recent checkpoint for a project (by file mtime)."""
    project_dir = pipeline_dir / project_id
    if not project_dir.exists():
        return None

    checkpoints = sorted(
        project_dir.glob("checkpoint_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not checkpoints:
        return None

    with open(checkpoints[0], encoding="utf-8") as f:
        checkpoint = json.load(f)
    validate_checkpoint(checkpoint, project_dir=pipeline_dir / project_id)
    return checkpoint

def get_completed_stages(
    pipeline_dir: Path, project_id: str, pipeline_type: str | None = None
) -> list[str]:
    """Return list of stages that have a completed checkpoint.

    When pipeline_type is provided, only checks stages defined in that
    pipeline's manifest — preventing false positives from leftover
    checkpoints of a different pipeline type.
    """
    stages_to_check = get_pipeline_stages(pipeline_type)
    completed = []
    for stage in stages_to_check:
        cp = read_checkpoint(pipeline_dir, project_id, stage)
        if cp and cp.get("status") == "completed":
            completed.append(stage)
    return completed

def get_next_stage(
    pipeline_dir: Path, project_id: str, pipeline_type: str | None = None
) -> Optional[str]:
    """Determine the next stage to run based on completed checkpoints.

    Uses pipeline-specific stage order so that pipelines with different
    stage sequences (e.g. cinematic vs explainer) progress correctly.
    """
    stages = get_pipeline_stages(pipeline_type) if pipeline_type else STAGES
    completed = set(get_completed_stages(pipeline_dir, project_id, pipeline_type))
    for stage in stages:
        if stage not in completed:
            return stage
    return None
