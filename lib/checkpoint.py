"""Checkpoint writer/reader for pipeline state persistence.

Each stage writes a checkpoint after completion. The orchestrator uses
checkpoints to resume pipelines and to present state at human checkpoints.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

import jsonschema

from schemas.artifacts import ARTIFACT_NAMES, validate_artifact
from lib.asset_precheck import scan_user_images, validate_beat_assignment_matrix

# All known stages across all pipelines (used only for artifact name lookup).
ALL_KNOWN_STAGES = frozenset([
    "research", "proposal", "idea", "script", "scene_plan",
    "assets", "edit", "compose", "publish",
])

# Backward-compatible alias — existing code / tests that import STAGES still work.
# New code should use get_pipeline_stages(pipeline_type) instead.
STAGES = ["research", "proposal", "idea", "script", "scene_plan",
          "assets", "edit", "compose", "publish"]

CANONICAL_STAGE_ARTIFACTS = {
    "research": "research_brief",
    "proposal": "proposal_packet",
    "idea": "brief",
    "script": "script",
    "scene_plan": "scene_plan",
    "assets": "asset_manifest",
    "edit": "edit_decisions",
    "compose": "render_report",
    "publish": "publish_log",
}

# Additional artifacts that may be produced alongside canonical ones.
# These are not stage-defining but are required by governance contracts.
SUPPLEMENTARY_ARTIFACTS = {
    "source_media_review",  # Required before first planning stage when user media exists
    "final_review",         # Required by compose stage before presenting to user
    "video_analysis_brief", # Reference-video grounding artifact carried alongside stages
}

_COMMERCIAL_MEDIA_REQUIREMENTS = {
    "sample_review": ("sample_reel", "path"),
    "draft_review": ("full_draft_pro", "path"),
    "final_compose": ("final_review", "output_path"),
    "delivery_signoff": ("final_review", "output_path"),
}
_COMMERCIAL_REVIEW_VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".webm", ".mov", ".m4v", ".mkv"}
)
_LEDGER_IMAGE_PATH_FIELDS = frozenset({
    "path",
    "actual",
    "actual_path",
    "planned",
    "planned_path",
    "planned_output",
    "planned_output_path",
    "source",
    "source_path",
    "input_path",
    "candidate",
    "candidate_path",
    "candidate_output_path",
    "output",
    "output_path",
    "ref",
    "ref_image",
})
_LEDGER_IMAGE_PATH_COLLECTION_FIELDS = frozenset({
    "actuals",
    "actual_paths",
    "planned_paths",
    "source_paths",
    "sources",
    "candidate_paths",
    "candidates",
    "output_paths",
    "outputs",
})


def get_pipeline_stages(pipeline_type: str | None) -> list[str]:
    """Return the ordered stage list for a specific pipeline.

    Falls back to STAGES (deterministic canonical order) when pipeline_type
    is not provided or the manifest cannot be loaded.

    Previous versions used a set intersection here, which produced
    nondeterministic ordering. The fallback now uses a stable list.
    """
    if pipeline_type is None:
        # Deterministic canonical fallback — sorted to ensure stable ordering
        import logging
        logging.getLogger(__name__).warning(
            "get_pipeline_stages called without pipeline_type — "
            "using canonical fallback order. Pass pipeline_type for correctness."
        )
        return list(STAGES)

    try:
        from lib.pipeline_loader import load_pipeline_readonly, get_stage_order
        manifest = load_pipeline_readonly(pipeline_type)
        return get_stage_order(manifest)
    except (FileNotFoundError, Exception):
        # Graceful fallback: return all known stages in canonical order
        return list(STAGES)

from lib.resources import get_resources

CHECKPOINT_SCHEMA_PATH = get_resources().checkpoint_schema()

# Canonical project root. Checkpoints, artifacts, and the project marker all
# live under PROJECTS_DIR/<project_id>/ — this is the location the Backlot
# board watches. Callers may still pass a different pipeline_dir (tests do),
# but production runs should use the default.
from lib.paths import PROJECTS_DIR  # noqa: E402  (single source of truth)

PROJECT_MARKER_FILENAME = "project.json"
HISTORY_DIRNAME = "history"
CHECKPOINT_LOCK_FILENAME = ".checkpoint.lock"
CHECKPOINT_LOCK_TIMEOUT_SECONDS = 10.0
CHECKPOINT_LOCK_POLL_SECONDS = 0.02


class CheckpointValidationError(ValueError):
    """Raised when a checkpoint or its canonical artifacts are invalid."""


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


@lru_cache(maxsize=1)
def _load_checkpoint_schema() -> dict[str, Any]:
    with open(CHECKPOINT_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _validate_artifacts_for_stage(
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    project_dir: Optional[Path] = None,
) -> None:
    # Valid stages come from the pipeline manifest (get_pipeline_stages), which
    # can declare stages beyond the 9 canonical ones (e.g. character-animation's
    # `character_design`/`rig_plan`, screen-demo's `real_capture`). Those have no
    # canonical artifact, so look it up defensively — a missing entry means the
    # stage simply has no required artifact, not a crash.
    required_artifact = CANONICAL_STAGE_ARTIFACTS.get(stage)
    if (
        required_artifact is not None
        and status in {"completed", "awaiting_human"}
        and required_artifact not in artifacts
    ):
        raise CheckpointValidationError(
            f"Stage {stage!r} with status {status!r} must include "
            f"canonical artifact {required_artifact!r}"
        )

    for artifact_name, artifact_data in artifacts.items():
        if artifact_name not in ARTIFACT_NAMES:
            continue
        if isinstance(artifact_data, str):
            if project_dir is None:
                raise CheckpointValidationError(
                    f"Artifact {artifact_name!r} uses a path reference but no project directory was provided"
                )
            ref = Path(artifact_data)
            if not ref.is_absolute():
                ref = project_dir / ref
            try:
                ref = ref.resolve()
                ref.relative_to(project_dir.resolve())
            except (OSError, ValueError) as exc:
                raise CheckpointValidationError(
                    f"Artifact {artifact_name!r} path must stay inside the project directory"
                ) from exc
            try:
                with open(ref, encoding="utf-8") as f:
                    artifact_data = json.load(f)
            except (OSError, json.JSONDecodeError, UnicodeError) as exc:
                raise CheckpointValidationError(
                    f"Artifact {artifact_name!r} path could not be read as UTF-8 JSON: {ref}"
                ) from exc
        if not isinstance(artifact_data, dict):
            raise CheckpointValidationError(
                f"Artifact {artifact_name!r} must be a JSON object or project-local JSON path"
            )
        try:
            validate_artifact(artifact_name, artifact_data)
        except Exception as exc:
            raise CheckpointValidationError(
                f"Artifact {artifact_name!r} failed schema validation: {exc}"
            ) from exc


def _validate_commercial_media_file(
    pipeline_type: Any,
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    project_dir: Optional[Path],
    *,
    minimal_plan_signoff: bool = False,
) -> None:
    """Ensure reviewable commercial media exists inside the current project."""
    del minimal_plan_signoff  # Plan/15: no video-less delivery signoff
    requirement = _COMMERCIAL_MEDIA_REQUIREMENTS.get(stage)
    if (
        pipeline_type != "bootstrap-commercial"
        or status not in {"awaiting_human", "completed"}
        or requirement is None
    ):
        return
    if project_dir is None:
        raise CheckpointValidationError(
            f"商品片媒体阶段 {stage!r} 校验需要当前项目目录"
        )

    artifact_name, path_key = requirement
    artifact = artifacts.get(artifact_name)
    if isinstance(artifact, str):
        artifact_ref = Path(artifact)
        if not artifact_ref.is_absolute():
            artifact_ref = project_dir / artifact_ref
        try:
            artifact_ref = artifact_ref.resolve()
            artifact_ref.relative_to(project_dir.resolve())
            artifact = json.loads(artifact_ref.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
            raise CheckpointValidationError(
                f"商品片媒体工件 {artifact_name!r} 无法从当前项目读取"
            ) from exc
    if not isinstance(artifact, dict):
        raise CheckpointValidationError(
            f"商品片媒体工件 {artifact_name!r} 必须提供"
        )

    raw_path = artifact.get(path_key)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise CheckpointValidationError(
            f"商品片媒体工件 {artifact_name!r} 的 {path_key!r} 必须为非空路径"
        )
    media_path = Path(raw_path)
    if not media_path.is_absolute():
        media_path = project_dir / media_path
    try:
        resolved_project = project_dir.resolve()
        media_path = media_path.resolve()
        media_path.relative_to(resolved_project)
    except (OSError, ValueError) as exc:
        raise CheckpointValidationError(
            f"商品片媒体路径必须位于当前项目目录：{raw_path}"
        ) from exc
    if not media_path.exists():
        raise CheckpointValidationError(
            f"商品片媒体文件不存在：{media_path}"
        )
    if not media_path.is_file():
        raise CheckpointValidationError(
            f"商品片媒体路径必须指向实际文件：{media_path}"
        )
    if (
        media_path.suffix.lower() not in _COMMERCIAL_REVIEW_VIDEO_EXTENSIONS
        or media_path.stat().st_size <= 0
    ):
        raise CheckpointValidationError(
            f"商品片媒体不可评审：必须是非空视频文件（{media_path.name}）"
        )


_COMMERCIAL_ASSIGNMENT_ARTIFACT_FILES = {
    "segment_cards": ("artifacts/segment_cards.json",),
    "video_plan": ("artifacts/video_plan.json",),
    "asset_ledger": ("artifacts/asset_ledger.json",),
    "decision_log": ("decision_log.json", "artifacts/decision_log.json"),
}


def _read_project_local_json_object(
    artifact_name: str,
    artifacts: dict[str, Any],
    project_dir: Path,
) -> dict[str, Any]:
    """Read an inline or canonical project-local JSON artifact."""
    inline_or_ref = artifacts.get(artifact_name)
    if isinstance(inline_or_ref, dict):
        return inline_or_ref

    raw_refs: tuple[str, ...]
    if isinstance(inline_or_ref, str) and inline_or_ref.strip():
        raw_refs = (inline_or_ref.strip(),)
    else:
        raw_refs = _COMMERCIAL_ASSIGNMENT_ARTIFACT_FILES[artifact_name]

    project_root = project_dir.resolve()
    last_error: Exception | None = None
    for raw_ref in raw_refs:
        ref = Path(raw_ref)
        if not ref.is_absolute():
            ref = project_root / ref
        try:
            resolved = ref.resolve()
            resolved.relative_to(project_root)
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
            last_error = exc
            continue
        if not isinstance(payload, dict):
            last_error = TypeError("JSON root is not an object")
            continue
        return payload

    raise CheckpointValidationError(
        f"商品片素材门禁无法读取项目内工件 {artifact_name!r}"
    ) from last_error


def _read_all_project_decision_logs(
    artifacts: dict[str, Any],
    project_dir: Path,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    inline_or_ref = artifacts.get("decision_log")
    if isinstance(inline_or_ref, dict):
        payloads.append(inline_or_ref)

    project_root = project_dir.resolve()
    raw_refs: list[str] = []
    if isinstance(inline_or_ref, str) and inline_or_ref.strip():
        raw_refs.append(inline_or_ref.strip())
    raw_refs.extend(_COMMERCIAL_ASSIGNMENT_ARTIFACT_FILES["decision_log"])
    seen_paths: set[Path] = set()
    for raw_ref in raw_refs:
        try:
            candidate = Path(raw_ref)
            if not candidate.is_absolute():
                candidate = project_root / candidate
            candidate = candidate.resolve()
            candidate.relative_to(project_root)
        except (OSError, ValueError) as exc:
            raise CheckpointValidationError(
                "商品片 assets_gate decision_log 必须位于当前项目内"
            ) from exc
        if candidate in seen_paths:
            continue
        seen_paths.add(candidate)
        if not candidate.exists():
            if isinstance(inline_or_ref, str) and raw_ref == inline_or_ref.strip():
                raise CheckpointValidationError(
                    f"商品片素材门禁无法读取项目内工件 'decision_log': {raw_ref}"
                )
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            raise CheckpointValidationError(
                f"商品片素材门禁无法读取项目内工件 'decision_log': {raw_ref}"
            ) from exc
        if not isinstance(payload, dict):
            raise CheckpointValidationError(
                "商品片素材门禁工件 'decision_log' JSON root 必须是对象"
            )
        payloads.append(payload)
    return payloads


def _merge_project_decision_logs(
    payloads: list[dict[str, Any]],
    project_id: str,
) -> dict[str, Any]:
    """Choose the longest prefix-compatible append-only decision history."""
    if not payloads:
        return {}

    histories: list[tuple[list[str], list[dict[str, Any]]]] = []
    decisions_by_id: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        if str(payload.get("project_id") or "").strip() != project_id:
            raise CheckpointValidationError(
                "商品片 assets_gate decision_log project_id 与当前项目不一致"
            )
        rows = [
            row
            for row in payload.get("decisions", [])
            if isinstance(row, dict)
        ]
        ids = [str(row.get("decision_id") or "").strip() for row in rows]
        if len(set(ids)) != len(ids):
            raise CheckpointValidationError(
                "商品片 assets_gate decision_log 含重复 decision_id"
            )
        for decision_id, row in zip(ids, rows):
            previous = decisions_by_id.get(decision_id)
            if previous is not None and previous != row:
                raise CheckpointValidationError(
                    "商品片 assets_gate 多份 decision_log 的同一 decision_id 内容不一致"
                )
            decisions_by_id[decision_id] = row
        histories.append((ids, rows))

    canonical_ids, canonical_rows = max(
        histories,
        key=lambda history: len(history[0]),
    )
    for ids, _rows in histories:
        if canonical_ids[:len(ids)] != ids:
            raise CheckpointValidationError(
                "商品片 assets_gate 多份 decision_log 不是同一追加历史，拒绝猜测最新审批"
            )

    return {
        "version": "1.0",
        "project_id": project_id,
        "decisions": canonical_rows,
    }


def _project_image_inventory_key(project_dir: Path, raw_path: Any) -> str | None:
    value = str(raw_path or "").strip().replace("\\", "/")
    if not value:
        return None
    candidate = Path(value)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.parts[:2] != ("assets", "images")
    ):
        return None
    project_root = project_dir.resolve()
    images_root = (project_root / "assets" / "images").resolve()
    try:
        resolved = (project_root / candidate).resolve()
        resolved.relative_to(images_root)
        return resolved.as_posix().casefold()
    except (OSError, ValueError):
        return None


def _ledger_image_inventory_keys(
    project_dir: Path,
    ledger: dict[str, Any],
) -> set[str]:
    accounted: set[str] = set()

    def collect(raw: Any) -> None:
        if isinstance(raw, str):
            key = _project_image_inventory_key(project_dir, raw)
            if key:
                accounted.add(key)
        elif isinstance(raw, list):
            for item in raw:
                collect(item)
        elif isinstance(raw, dict):
            for field, value in raw.items():
                if (
                    field in _LEDGER_IMAGE_PATH_FIELDS
                    or field in _LEDGER_IMAGE_PATH_COLLECTION_FIELDS
                ):
                    collect(value)

    for collection in ("entries", "planned_entries"):
        rows = ledger.get(collection)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for field, value in row.items():
                if (
                    field in _LEDGER_IMAGE_PATH_FIELDS
                    or field in _LEDGER_IMAGE_PATH_COLLECTION_FIELDS
                ):
                    collect(value)
    return accounted


def _validate_commercial_image_inventory(
    project_dir: Path,
    ledger: dict[str, Any],
) -> None:
    project_root = project_dir.resolve()
    actual: dict[str, str] = {}
    inventory = scan_user_images(project_root, min_dimension=1)
    unsafe_svg_paths: list[str] = []
    oversized_svg_paths: list[str] = []
    for image in inventory.get("entries") or []:
        if not isinstance(image, dict):
            continue
        relative_path = str(image.get("path") or "")
        issues = image.get("issues") or []
        if (
            isinstance(issues, list)
            and "unsafe_svg_declaration" in issues
            and relative_path
        ):
            unsafe_svg_paths.append(relative_path)
        if (
            isinstance(issues, list)
            and "svg_too_large" in issues
            and relative_path
        ):
            oversized_svg_paths.append(relative_path)
        key = _project_image_inventory_key(project_root, relative_path)
        if key:
            actual[key] = relative_path
    if unsafe_svg_paths:
        raise CheckpointValidationError(
            "商品片 assets_gate 发现危险 SVG，禁止完成："
            f"{sorted(unsafe_svg_paths)}"
        )
    if oversized_svg_paths:
        raise CheckpointValidationError(
            "商品片 assets_gate 发现过大 SVG，禁止完成："
            f"{sorted(oversized_svg_paths)}"
        )

    accounted = _ledger_image_inventory_keys(project_root, ledger)
    untracked = sorted(actual[key] for key in actual.keys() - accounted)
    if untracked:
        raise CheckpointValidationError(
            f"商品片 assets_gate 存在未登记真实图片：{untracked}"
        )
    invalid_references = sorted(
        key for key in accounted - actual.keys()
    )
    if invalid_references:
        raise CheckpointValidationError(
            "商品片 assets_gate 账本引用不是有效图片内容："
            f"{invalid_references}"
        )

    unexplained_unused: list[str] = []
    for index, entry in enumerate(ledger.get("entries") or []):
        if not isinstance(entry, dict) or entry.get("selected") is not False:
            continue
        reason = str(entry.get("reason") or "").strip()
        note = str(entry.get("note_zh") or "").strip()
        if not reason and not note:
            unexplained_unused.append(
                str(entry.get("path") or f"entries[{index}]")
            )
    if unexplained_unused:
        raise CheckpointValidationError(
            "商品片 assets_gate 未使用实际素材必须说明原因："
            f"{unexplained_unused}"
        )


def _validate_commercial_asset_assignment_gate(
    project_id: Any,
    pipeline_type: Any,
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    project_dir: Optional[Path],
) -> None:
    """Reject every open beat assignment before the commercial assets gate closes."""
    if (
        pipeline_type != "bootstrap-commercial"
        or stage != "assets_gate"
        or status != "completed"
    ):
        return
    if project_dir is None:
        raise CheckpointValidationError(
            "商品片 assets_gate 完成校验需要当前项目目录"
        )

    marker_path = project_dir.resolve() / PROJECT_MARKER_FILENAME
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise CheckpointValidationError(
            "商品片 assets_gate 完成校验无法读取当前项目 project.json"
        ) from exc
    marker_project_id = (
        str(marker.get("project_id") or "").strip()
        if isinstance(marker, dict)
        else ""
    )
    checkpoint_project_id = str(project_id or "").strip()
    if (
        not marker_project_id
        or marker_project_id != project_dir.resolve().name
        or marker_project_id != checkpoint_project_id
    ):
        raise CheckpointValidationError(
            "商品片 assets_gate 项目标识必须与当前项目目录及 project.json 一致"
        )

    loaded = {
        name: _read_project_local_json_object(name, artifacts, project_dir)
        for name in ("segment_cards", "video_plan", "asset_ledger")
    }
    decision_logs = _read_all_project_decision_logs(artifacts, project_dir)
    loaded["decision_log"] = {}
    for name, payload in loaded.items():
        if name == "decision_log":
            continue
        try:
            validate_artifact(name, payload)
        except Exception as exc:
            raise CheckpointValidationError(
                f"商品片素材门禁工件 {name!r} schema 校验失败：{exc}"
            ) from exc

    ledger = loaded["asset_ledger"]
    for decision_log in decision_logs:
        try:
            validate_artifact("decision_log", decision_log)
        except Exception as exc:
            raise CheckpointValidationError(
                "商品片素材门禁工件 'decision_log' schema 校验失败："
                f"{exc}"
            ) from exc
        decision_project_id = str(decision_log.get("project_id") or "").strip()
        if decision_project_id != marker_project_id:
            raise CheckpointValidationError(
                "商品片 assets_gate decision_log project_id "
                "必须与当前项目 project.json 及目录身份一致"
            )
    loaded["decision_log"] = _merge_project_decision_logs(
        decision_logs,
        marker_project_id,
    )
    _validate_commercial_image_inventory(project_dir, ledger)
    result = validate_beat_assignment_matrix(
        project_id=marker_project_id,
        segment_cards=loaded["segment_cards"],
        video_plan=loaded["video_plan"],
        ledger_entries=ledger.get("entries"),
        planned_entries=ledger.get("planned_entries"),
        decision_log=loaded["decision_log"],
        project_dir=project_dir,
    )
    if result["ready"]:
        return

    issues: list[str] = []
    if not result["canonical_beat_ids"]:
        issues.append("missing canonical beats")
    if result["canonical_source_mismatches"]:
        issues.append(
            f"beat source mismatch={result['canonical_source_mismatches']}"
        )
    if result["canonical_source_conflicts"]:
        issues.append(
            f"canonical conflicts={result['canonical_source_conflicts']}"
        )
    if result["missing"]:
        issues.append(f"missing={result['missing']}")
    if result["orphan_assignments"]:
        issues.append(f"orphan={result['orphan_assignments']}")
    if result["reuse_pending"]:
        issues.append(f"reuse_pending={result['reuse_pending']}")
    if result["assignment_conflicts"]:
        issues.append(f"assignment_conflicts={result['assignment_conflicts']}")
    if result["unsafe_assignments"]:
        issues.append(f"unsafe_paths={result['unsafe_assignments']}")
    if result["beat_reference_conflicts"]:
        issues.append(
            f"beat_reference_conflicts={result['beat_reference_conflicts']}"
        )
    if result["source_conflicts"]:
        issues.append(f"source_conflicts={result['source_conflicts']}")
    if result["open_ledger_entries"]:
        issues.append(f"open_ledger={result['open_ledger_entries']}")
    if result["open_planned_entries"]:
        issues.append(f"open_planned={result['open_planned_entries']}")
    if result["planned_source_issues"]:
        issues.append(
            f"planned_source_issues={result['planned_source_issues']}"
        )
    if result["planned_output_issues"]:
        issues.append(
            f"planned_output_issues={result['planned_output_issues']}"
        )
    if result["candidate_selection_conflicts"]:
        issues.append(
            "candidate_selection_conflicts="
            f"{result['candidate_selection_conflicts']}"
        )
    if result["i2i_issues"]:
        issues.append(f"i2i_review={result['i2i_issues']}")
    if result["video_plan_conflicts"]:
        issues.append(f"video_plan_conflicts={result['video_plan_conflicts']}")
    if result["decision_log_issues"]:
        issues.append(f"decision_log_issues={result['decision_log_issues']}")
    raise CheckpointValidationError(
        "商品片 assets_gate 素材分配未闭环：" + "; ".join(issues)
    )


def validate_checkpoint(
    checkpoint: dict[str, Any],
    *,
    project_dir: Optional[Path] = None,
    enforce_pipeline_outputs: bool = False,
) -> None:
    """Validate checkpoint structure and canonical artifact payloads.

    Uses pipeline_type (if present) to resolve the valid stage list.
    Falls back to ALL_KNOWN_STAGES when pipeline_type is absent.
    """
    stage = checkpoint.get("stage")
    status = checkpoint.get("status")
    artifacts = checkpoint.get("artifacts")
    pipeline_type = checkpoint.get("pipeline_type")

    valid_stages = (
        set(get_pipeline_stages(pipeline_type)) if pipeline_type
        else ALL_KNOWN_STAGES
    )

    if not isinstance(stage, str) or stage not in valid_stages:
        raise CheckpointValidationError(
            f"Invalid stage: {stage!r} for pipeline {pipeline_type!r}. "
            f"Valid stages: {sorted(valid_stages)}"
        )
    if not isinstance(status, str):
        raise CheckpointValidationError(f"Invalid status: {status!r}")
    if not isinstance(artifacts, dict):
        raise CheckpointValidationError("Checkpoint artifacts must be a dictionary")

    if (
        enforce_pipeline_outputs
        and pipeline_type not in {None, "", "unknown"}
        and status in {"completed", "awaiting_human"}
    ):
        from lib.pipeline_loader import load_pipeline_readonly

        manifest = load_pipeline_readonly(pipeline_type)
        stage_def = next(
            (item for item in manifest.get("stages", []) if item.get("name") == stage),
            {},
        )
        missing = [name for name in stage_def.get("produces", []) if name not in artifacts]
        if missing:
            raise CheckpointValidationError(
                f"Stage {stage!r} must include manifest outputs: {missing}"
            )

    _validate_artifacts_for_stage(stage, status, artifacts, project_dir)
    _validate_commercial_media_file(
        pipeline_type,
        stage,
        status,
        artifacts,
        project_dir,
    )
    _validate_commercial_asset_assignment_gate(
        checkpoint.get("project_id"),
        pipeline_type,
        stage,
        status,
        artifacts,
        project_dir,
    )

    try:
        jsonschema.validate(instance=checkpoint, schema=_load_checkpoint_schema())
    except jsonschema.ValidationError as exc:
        raise CheckpointValidationError(f"Checkpoint failed schema validation: {exc.message}") from exc


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
    base = pipeline_dir or PROJECTS_DIR
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
    marker: dict[str, Any] = {}
    if marker_path.exists():
        try:
            with open(marker_path) as f:
                marker = json.load(f)
        except (json.JSONDecodeError, OSError):
            marker = {}

    marker.setdefault("version", "1.0")
    marker.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    marker["project_id"] = project_id
    marker["title"] = title
    marker["pipeline_type"] = pipeline_type
    if style_playbook is not None:
        marker["style_playbook"] = style_playbook

    with open(marker_path, "w") as f:
        json.dump(marker, f, indent=2)

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
            f"pipeline_defs/*.yaml."
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


# Filenames for board-visible commercial / shared evidence (mirrors Backlot).
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
