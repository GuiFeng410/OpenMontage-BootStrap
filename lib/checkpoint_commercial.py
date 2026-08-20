"""Commercial media file and image inventory validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from lib.asset_precheck import scan_user_images, validate_beat_assignment_matrix
from lib.checkpoint_validate import CheckpointValidationError, PROJECT_MARKER_FILENAME

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
