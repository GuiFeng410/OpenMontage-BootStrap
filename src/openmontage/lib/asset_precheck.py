"""Read-only facts scanner for uploaded commercial product images.

P0 hybrid preprocess: program reports hard facts + filename class hints only.
No vision API. User confirmation writes ``asset_ledger`` via the agent gate.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

_MAX_SVG_BYTES = 5 * 1024 * 1024
_PATH_CASE_INSENSITIVE = os.name == "nt"
_SVG_LENGTH_RE = re.compile(r"^\+?(?:\d+(?:\.\d*)?|\.\d+)(?:px)?$", re.IGNORECASE)
_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".bmp", ".tif", ".tiff", ".svg",
}

_ROLE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("hero", "main", "front", "主图", "正面"), "product_hero"),
    (("detail", "macro", "close", "细节", "微距"), "product_detail"),
    (("angle", "side", "back", "角度", "侧面", "背面"), "product_angle"),
    (("hand", "wear", "body", "佩戴", "手持", "上身"), "on_body"),
    (("pack", "box", "包装"), "packaging"),
    (("scene", "lifestyle", "场景", "氛围"), "lifestyle"),
)

# Duration band → (minimum images, recommended images, preferred classes)
_DURATION_BANDS: tuple[tuple[int, int, int, tuple[str, ...]], ...] = (
    (10, 1, 3, ("product_hero", "product_angle", "product_detail")),
    (30, 2, 6, ("product_hero", "product_angle", "product_detail", "on_body")),
    (60, 3, 10, ("product_hero", "product_angle", "product_detail", "on_body", "lifestyle")),
)

_ENTRY_METADATA_FIELDS = {
    "beat",
    "beats",
    "kind",
    "origin",
    "asset_source",
    "gap_fill",
    "provider",
    "model",
    "review_status",
    "decision_id",
    "selected",
    "label_zh",
    "note_zh",
}

_GENERATED_IMAGE_SOURCE_ALIASES = {
    "generated",
    "t2i",
    "text_to_image",
    "text-to-image",
    "i2i",
    "image_to_image",
    "image-to-image",
    "ai_generated",
    "ai-generated",
}
_GENERATED_CHAIN_STATUSES = {
    "generating",
    "ready",
    "review_pending",
    "approved",
    "rejected",
    "failed",
}
_GENERATED_CHAIN_FIELDS = {
    "planned_output",
    "planned_output_path",
    "output",
    "output_path",
    "candidate_output_path",
    "candidates",
    "candidate_paths",
    "provider",
    "model",
    "review_status",
    "decision_id",
    "retry_count",
    "retry_of",
    "max_retries",
}

_CLOSED_LEDGER_STATUSES = {"confirmed", "identity_anchor", "approved", "ready"}
_CLOSED_VIDEO_PLAN_STATUSES = {"assigned", "ready", "approved"}
_OPEN_VIDEO_PLAN_STATUSES = {
    "planned",
    "i2i_planned",
    "missing",
    "reuse_pending",
    "review_pending",
    "i2i_review_pending",
    "rejected",
    "failed",
}


def has_generation_chain_signal(
    entry: dict[str, Any],
    status: str,
    *,
    include_status: bool = True,
) -> bool:
    return (
        (include_status and status in _GENERATED_CHAIN_STATUSES)
        or any(field in entry for field in _GENERATED_CHAIN_FIELDS)
        or any(str(field).strip().lower().startswith("retry") for field in entry)
    )


def has_generated_image_source(entry: dict[str, Any]) -> bool:
    return any(
        str(entry.get(field) or "").strip().lower()
        in _GENERATED_IMAGE_SOURCE_ALIASES
        for field in ("origin", "asset_source", "gap_fill")
    )


def _expand_beat_ids(raw: Any) -> list[str]:
    """Expand beat references while preserving duplicates and order."""
    if raw is None:
        return []
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    expanded: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        for part in value.split(","):
            beat_id = part.strip()
            if beat_id:
                expanded.append(beat_id)
    return expanded


def normalize_beat_ids(raw: Any) -> list[str]:
    """Normalize legacy and current beat references without changing order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for beat_id in _expand_beat_ids(raw):
        if beat_id not in seen:
            seen.add(beat_id)
            normalized.append(beat_id)
    return normalized


def _entry_beat_ids(
    entry: dict[str, Any],
    *,
    location: str,
) -> tuple[list[str], dict[str, Any] | None]:
    has_legacy = "beat" in entry
    has_current = "beats" in entry
    legacy = normalize_beat_ids(entry.get("beat")) if has_legacy else []
    current = normalize_beat_ids(entry.get("beats")) if has_current else []
    conflict = None
    if has_legacy and has_current and legacy != current:
        conflict = {
            "location": location,
            "beat": legacy,
            "beats": current,
        }
    return (current if has_current else legacy), conflict


def _canonical_beat_ids(
    canonical_beat_ids: Any,
    segment_cards: dict[str, Any] | None,
    video_plan: dict[str, Any] | None,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    explicit_raw = _expand_beat_ids(canonical_beat_ids)
    card_rows = (segment_cards or {}).get("segments", [])
    conflicts: list[dict[str, Any]] = []
    for index, row in enumerate(card_rows):
        if not isinstance(row, dict):
            continue
        row_ids, row_conflict = _entry_beat_ids(
            row,
            location=f"segment_cards.segments[{index}]",
        )
        if row_conflict:
            conflicts.append({
                "source": "segment_cards",
                "reason": "segment_id_beat_mismatch",
                **row_conflict,
            })
    cards_raw = _expand_beat_ids([
        row.get("beat") or row.get("id")
        for row in card_rows
        if isinstance(row, dict)
    ])
    plan_doc = (
        video_plan.get("video_plan")
        if isinstance(video_plan, dict)
        and isinstance(video_plan.get("video_plan"), dict)
        else video_plan or {}
    )
    segment_rows = (
        plan_doc.get("segments")
        if isinstance(plan_doc.get("segments"), list)
        else []
    )
    beat_rows = (
        plan_doc.get("beats")
        if isinstance(plan_doc.get("beats"), list)
        else []
    )
    segment_ids: list[str] = []
    normalized_segment_rows: list[dict[str, Any]] = []
    for index, row in enumerate(segment_rows):
        if not isinstance(row, dict):
            continue
        row_id = normalize_beat_ids(row.get("id")) if "id" in row else []
        legacy = normalize_beat_ids(row.get("beat")) if "beat" in row else []
        if row_id and legacy and row_id != legacy:
            conflicts.append({
                "source": "video_plan",
                "reason": "segment_id_beat_mismatch",
                "location": f"video_plan.segments[{index}]",
                "id": row_id,
                "beat": legacy,
            })
        canonical_row_id = row_id or legacy
        segment_ids.extend(canonical_row_id)
        normalized_segment_rows.append({
            **{
                key: value
                for key, value in row.items()
                if key not in {"id", "beat"}
            },
            "id": canonical_row_id[0] if len(canonical_row_id) == 1 else canonical_row_id,
        })
    beat_ids: list[str] = []
    normalized_beat_rows: list[dict[str, Any]] = []
    for index, row in enumerate(beat_rows):
        if not isinstance(row, dict):
            continue
        row_id = normalize_beat_ids(row.get("id")) if "id" in row else []
        legacy = normalize_beat_ids(row.get("beat")) if "beat" in row else []
        if row_id and legacy and row_id != legacy:
            conflicts.append({
                "source": "video_plan",
                "reason": "segment_id_beat_mismatch",
                "location": f"video_plan.beats[{index}]",
                "id": row_id,
                "beat": legacy,
            })
        canonical_row_id = row_id or legacy
        beat_ids.extend(canonical_row_id)
        normalized_beat_rows.append({
            **{
                key: value
                for key, value in row.items()
                if key not in {"id", "beat"}
            },
            "id": canonical_row_id[0] if len(canonical_row_id) == 1 else canonical_row_id,
        })
    if (
        segment_rows
        and beat_rows
        and normalized_segment_rows != normalized_beat_rows
    ):
        conflicts.append({
            "source": "video_plan",
            "reason": "top_level_key_mismatch",
            "segments": normalized_segment_rows,
            "beats": normalized_beat_rows,
        })
    plan_rows = segment_rows if segment_rows else beat_rows
    plan_raw = _expand_beat_ids([
        row.get("id") or row.get("beat")
        for row in plan_rows
        if isinstance(row, dict)
    ])
    named_sources = [
        (name, raw_ids)
        for name, raw_ids in (
            ("explicit", explicit_raw),
            ("segment_cards", cards_raw),
            ("video_plan", plan_raw),
        )
        if raw_ids
    ]
    sources = [
        (name, normalize_beat_ids(raw_ids))
        for name, raw_ids in named_sources
    ]
    if not sources:
        return [], [], []

    canonical_name, canonical = sources[0]
    mismatches = [
        {
            "expected_source": canonical_name,
            "actual_source": name,
            "expected": canonical,
            "actual": ids,
        }
        for name, ids in sources[1:]
        if ids != canonical
    ]
    for name, raw_ids in named_sources:
        duplicates = [
            beat_id
            for beat_id, count in Counter(raw_ids).items()
            if count > 1
        ]
        if duplicates:
            conflicts.append({
                "source": name,
                "reason": "duplicate_ids",
                "beat_ids": duplicates,
            })
    conflicts.extend({
        "source": mismatch["actual_source"],
        "reason": "source_mismatch",
        "expected": mismatch["expected"],
        "actual": mismatch["actual"],
    } for mismatch in mismatches)
    return canonical, mismatches, conflicts


def _decision_matches_asset_scope(
    decision: dict[str, Any],
    path: str,
    beat_ids: list[str],
) -> bool:
    target_path = _path_comparison_key(path, None)
    target_beats = set(beat_ids)
    decision_path = _path_comparison_key(decision.get("asset_path"), None)
    decision_subject = _path_comparison_key(decision.get("subject"), None)
    decision_beats = set(normalize_beat_ids(decision.get("beat_ids")))
    if decision_path or decision_beats:
        return decision_path == target_path and decision_beats == target_beats
    return decision_subject == target_path


def _has_reuse_approval(
    decision_log: dict[str, Any] | None,
    path: str,
    beat_ids: list[str],
    project_id: str,
) -> bool:
    if (
        not isinstance(decision_log, dict)
        or not project_id
        or str(decision_log.get("project_id") or "").strip() != project_id
    ):
        return False
    decisions = (
        decision_log.get("decisions", [])
        if isinstance(decision_log.get("decisions"), list)
        else []
    )
    for decision in reversed(decisions):
        if (
            not isinstance(decision, dict)
            or decision.get("category") != "asset_decision"
            or not _decision_matches_asset_scope(decision, path, beat_ids)
        ):
            continue
        if (
            decision.get("stage") != "assets_gate"
            or _path_comparison_key(decision.get("subject"), None)
            != _path_comparison_key(path, None)
            or _path_comparison_key(decision.get("asset_path"), None)
            != _path_comparison_key(path, None)
            or set(normalize_beat_ids(decision.get("beat_ids"))) != set(beat_ids)
        ):
            return False
        options = decision.get("options_considered")
        selected = str(decision.get("selected") or "").strip()
        selected_option = next(
            (
                option
                for option in options
                if isinstance(option, dict) and option.get("option_id") == selected
            ),
            None,
        ) if isinstance(options, list) else None
        if (
            not decision.get("decision_id")
            or not selected_option
            or selected_option.get("action") != "reuse"
            or decision.get("user_approved") is not True
            or not str(decision.get("user_response_text") or "").strip()
        ):
            return False
        return True
    return False


def _project_local_path(project_dir: Path | None, raw_path: str) -> bool:
    if project_dir is None or not raw_path:
        return False
    root = project_dir.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate = candidate.resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _project_local_file(project_dir: Path | None, raw_path: str) -> bool:
    if not _project_local_path(project_dir, raw_path):
        return False
    root = project_dir.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate = candidate.resolve()
        return candidate.is_file() and candidate.stat().st_size > 0
    except OSError:
        return False


def _project_local_sha256(project_dir: Path | None, raw_path: str) -> str:
    if not _project_local_file(project_dir, raw_path):
        return ""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_dir.resolve() / candidate
    try:
        return _sha256(candidate.resolve())
    except OSError:
        return ""


def _has_generated_review_approval(
    decision_log: dict[str, Any] | None,
    *,
    decision_id: str,
    output_path: str,
    output_sha256: str,
    beat_ids: list[str],
    project_id: str,
) -> bool:
    if (
        not isinstance(decision_log, dict)
        or not project_id
        or str(decision_log.get("project_id") or "").strip() != project_id
    ):
        return False
    decisions = (
        decision_log.get("decisions", [])
        if isinstance(decision_log.get("decisions"), list)
        else []
    )
    matches = [
        decision
        for decision in decisions
        if (
            isinstance(decision, dict)
            and str(decision.get("decision_id") or "").strip() == decision_id
        )
    ]
    if len(matches) != 1:
        return False
    decision = matches[0]
    latest_for_scope = next(
        (
            item
            for item in reversed(decisions)
            if (
                isinstance(item, dict)
                and item.get("category") == "asset_decision"
                and _decision_matches_asset_scope(item, output_path, beat_ids)
            )
        ),
        None,
    )
    if latest_for_scope is not decision:
        return False
    selected = str(decision.get("selected") or "").strip()
    options = (
        decision.get("options_considered")
        if isinstance(decision.get("options_considered"), list)
        else []
    )
    selected_option = next(
        (
            option
            for option in options
            if (
                isinstance(option, dict)
                and str(option.get("option_id") or "").strip() == selected
            )
        ),
        None,
    )
    return all((
        decision.get("stage") == "assets_gate",
        decision.get("category") == "asset_decision",
        has_generated_image_source(decision),
        selected == "approved",
        selected_option is not None,
        decision.get("user_approved") is True,
        bool(str(decision.get("user_response_text") or "").strip()),
        _path_comparison_key(decision.get("asset_path"), None)
        == _path_comparison_key(output_path, None),
        _path_comparison_key(decision.get("subject"), None)
        == _path_comparison_key(output_path, None),
        bool(output_sha256),
        str(decision.get("asset_sha256") or "").strip().lower() == output_sha256,
        set(normalize_beat_ids(decision.get("beat_ids"))) == set(beat_ids),
    ))


def _generated_approval_evidence_issues(
    entry: dict[str, Any],
    *,
    output_path: str,
    beat_ids: list[str],
    project_id: str,
    decision_log: dict[str, Any] | None,
    project_dir: Path | None,
) -> list[str]:
    issues: list[str] = []
    candidate_paths = [
        str(path).strip()
        for path in entry.get("candidate_paths", [])
        if isinstance(path, str) and path.strip()
    ] if isinstance(entry.get("candidate_paths"), list) else []
    if not candidate_paths:
        issues.append("candidate_paths_missing")
    else:
        if output_path not in candidate_paths:
            issues.append("approved_output_not_candidate")
        if any(
            not _project_local_path(project_dir, candidate_path)
            for candidate_path in candidate_paths
        ):
            issues.append("candidate_path_unsafe")

    decision_id = str(entry.get("decision_id") or "").strip()
    output_sha256 = _project_local_sha256(project_dir, output_path)
    if not decision_id:
        issues.append("decision_id_missing")
    else:
        decisions = (
            decision_log.get("decisions", [])
            if isinstance(decision_log, dict)
            and isinstance(decision_log.get("decisions"), list)
            else []
        )
        matching = [
            decision
            for decision in decisions
            if (
                isinstance(decision, dict)
                and str(decision.get("decision_id") or "").strip() == decision_id
            )
        ]
        if len(matching) == 1:
            approved_sha256 = str(
                matching[0].get("asset_sha256") or ""
            ).strip().lower()
            if not approved_sha256:
                issues.append("approval_hash_missing")
            elif approved_sha256 != output_sha256:
                issues.append("approved_content_changed")
        if not _has_generated_review_approval(
            decision_log,
            decision_id=decision_id,
            output_path=output_path,
            output_sha256=output_sha256,
            beat_ids=beat_ids,
            project_id=project_id,
        ):
            issues.append("review_decision_invalid")
    return issues


def _normalize_asset_source(raw: Any) -> str:
    source = str(raw or "").strip().lower()
    if source in {"", "none"}:
        return ""
    if source in {"upload", "uploaded", "user", "user_upload"}:
        return "user_upload"
    if source in _GENERATED_IMAGE_SOURCE_ALIASES:
        return "generated"
    return source


def _path_comparison_key(raw_path: Any, project_dir: Path | None) -> str:
    value = str(raw_path or "").strip()
    if not value:
        return ""
    candidate = Path(value)
    if project_dir is not None and not candidate.is_absolute():
        candidate = project_dir / candidate
    try:
        normalized = candidate.resolve().as_posix()
    except (OSError, ValueError):
        normalized = candidate.as_posix()
    return normalized.casefold() if _PATH_CASE_INSENSITIVE else normalized


def validate_beat_assignment_matrix(
    *,
    project_id: str = "",
    canonical_beat_ids: Any = None,
    segment_cards: dict[str, Any] | None = None,
    video_plan: dict[str, Any] | None = None,
    ledger_entries: list[dict[str, Any]] | None = None,
    planned_entries: list[dict[str, Any]] | None = None,
    decision_log: dict[str, Any] | None = None,
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Classify the commercial beat-to-asset matrix and fail closed."""
    canonical, source_mismatches, canonical_source_conflicts = _canonical_beat_ids(
        canonical_beat_ids,
        segment_cards,
        video_plan,
    )
    canonical_set = set(canonical)
    assigned: dict[str, list[str]] = {}
    unused_assets: list[str] = []
    orphan_assignments: list[dict[str, Any]] = []
    unsafe_assignments: list[dict[str, str]] = []
    beat_reference_conflicts: list[dict[str, Any]] = []
    source_conflicts: list[dict[str, Any]] = []
    open_ledger_entries: list[dict[str, Any]] = []
    open_planned_entries: list[dict[str, Any]] = []
    planned_source_issues: list[dict[str, Any]] = []
    planned_output_issues: list[dict[str, Any]] = []
    candidate_selection_conflicts: list[dict[str, Any]] = []
    assignments_by_path: dict[str, list[str]] = {}
    assignment_sources: dict[str, set[str]] = {}
    root = Path(project_dir) if project_dir is not None else None
    i2i_review_pending: list[dict[str, str]] = []
    i2i_issues: list[dict[str, Any]] = []
    decision_log_issues: list[dict[str, str]] = []
    expected_decision_project_id = (
        str(project_id or "").strip()
        or (root.resolve().name if root is not None else "")
    )
    if isinstance(decision_log, dict) and decision_log and expected_decision_project_id:
        actual_decision_project_id = str(
            decision_log.get("project_id") or ""
        ).strip()
        if actual_decision_project_id != expected_decision_project_id:
            decision_log_issues.append({
                "reason": "project_id_mismatch",
                "expected_project_id": expected_decision_project_id,
                "actual_project_id": actual_decision_project_id,
            })

    def register_assignment(
        path: str,
        beat_ids: list[str],
        source: str = "",
    ) -> None:
        if root is not None and not _project_local_file(root, path):
            unsafe_assignments.append({
                "path": path,
                "reason": "missing_empty_or_outside_project",
            })
            return
        for beat_id in beat_ids:
            if beat_id not in canonical_set:
                continue
            paths = assigned.setdefault(beat_id, [])
            if path and path not in paths:
                paths.append(path)
            path_beats = assignments_by_path.setdefault(path, [])
            if path and beat_id not in path_beats:
                path_beats.append(beat_id)
            if source:
                assignment_sources.setdefault(beat_id, set()).add(source)

    for index, entry in enumerate(ledger_entries or []):
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or entry.get("output_path") or "").strip()
        status = str(entry.get("status") or "").strip().lower()
        beat_ids, beat_conflict = _entry_beat_ids(
            entry,
            location=f"entries[{index}]",
        )
        if beat_conflict:
            beat_reference_conflicts.append(beat_conflict)
        source_declarations = {
            field: _normalize_asset_source(entry.get(field))
            for field in ("origin", "asset_source", "gap_fill")
            if _normalize_asset_source(entry.get(field))
        }
        source_values = set(source_declarations.values())
        source_conflict = len(source_values) > 1
        kind = str(entry.get("kind") or "").strip().lower()
        is_actual_image = (
            kind == "image"
            or Path(path).suffix.lower() in _IMAGE_EXTENSIONS
        )
        has_non_status_generation_signal = has_generation_chain_signal(
            entry,
            status,
            include_status=False,
        )
        is_generated_image = (
            "generated" in source_values
            or (
                is_actual_image
                and (
                    has_non_status_generation_signal
                    or (
                        not source_values
                        and has_generation_chain_signal(
                            entry,
                            status,
                            include_status=entry.get("selected") is not False,
                        )
                    )
                )
            )
        )
        if source_conflict:
            source_conflicts.append({
                "location": f"entries[{index}]",
                "declarations": source_declarations,
            })

        compact = {"beat": beat_ids[0] if beat_ids else "", "path": path}
        actual_i2i_reasons: list[str] = []
        if source_conflict:
            actual_i2i_reasons.append("source_declaration_conflict")
        if is_generated_image:
            if not source_values:
                actual_i2i_reasons.append("source_declaration_missing")
            elif "generated" not in source_values:
                actual_i2i_reasons.append("generated_chain_source_mismatch")
            review_status = str(
                entry.get("review_status") or ""
            ).strip().lower()
            if review_status != "approved":
                i2i_review_pending.append(compact)
                actual_i2i_reasons.append("review_not_approved")
            if not str(entry.get("provider") or "").strip():
                actual_i2i_reasons.append("provider_missing")
            if not str(entry.get("model") or "").strip():
                actual_i2i_reasons.append("model_missing")
            if not _project_local_file(root, path):
                actual_i2i_reasons.append("output_missing_or_unsafe")
            if review_status == "approved":
                actual_i2i_reasons.extend(
                    _generated_approval_evidence_issues(
                        entry,
                        output_path=path,
                        beat_ids=beat_ids,
                        project_id=project_id,
                        decision_log=decision_log,
                        project_dir=root,
                    )
                )
            if actual_i2i_reasons:
                i2i_issues.append({
                    **compact,
                    "reasons": actual_i2i_reasons,
                })

        if (
            entry.get("selected") is False
            and not is_generated_image
            and status in {"", *_CLOSED_LEDGER_STATUSES, "rejected"}
        ):
            if path and path not in unused_assets:
                unused_assets.append(path)
            continue
        if status and status not in _CLOSED_LEDGER_STATUSES:
            open_ledger_entries.append({
                "location": f"entries[{index}]",
                "path": path,
                "beat_ids": beat_ids,
                "status": status,
            })
            continue
        if entry.get("selected") is False:
            if path and path not in unused_assets:
                unused_assets.append(path)
            continue
        if not beat_ids:
            if path and path not in unused_assets:
                unused_assets.append(path)
            continue
        valid_ids = [beat_id for beat_id in beat_ids if beat_id in canonical_set]
        orphan_ids = [beat_id for beat_id in beat_ids if beat_id not in canonical_set]
        if orphan_ids:
            orphan_assignments.append({"path": path, "beat_ids": orphan_ids})
        if (
            beat_conflict
            or source_conflict
            or (is_generated_image and actual_i2i_reasons)
        ):
            continue
        source = next(iter(source_values), "user_upload")
        register_assignment(path, valid_ids, source)

    for index, entry in enumerate(planned_entries or []):
        if not isinstance(entry, dict):
            continue
        beat_ids, beat_conflict = _entry_beat_ids(
            entry,
            location=f"planned_entries[{index}]",
        )
        if beat_conflict:
            beat_reference_conflicts.append(beat_conflict)
        source_declarations = {
            field: _normalize_asset_source(entry.get(field))
            for field in ("origin", "asset_source", "gap_fill")
            if _normalize_asset_source(entry.get(field))
        }
        source_values = set(source_declarations.values())
        kind = str(entry.get("kind") or "").strip().lower()
        status = str(entry.get("status") or "").strip().lower()
        is_planned_image = kind == "image"
        has_generation_signal = has_generation_chain_signal(entry, status)
        is_generated_chain = is_planned_image and (
            "generated" in source_values or has_generation_signal
        )
        source_conflict = len(source_values) > 1
        if source_conflict:
            source_conflicts.append({
                "location": f"planned_entries[{index}]",
                "declarations": source_declarations,
            })
        if is_planned_image and not source_values:
            planned_source_issues.append({
                "location": f"planned_entries[{index}]",
                "beat_ids": beat_ids,
                "reason": "source_declaration_missing",
            })

        output_path = str(entry.get("output_path") or "").strip()
        candidate_output_path = str(
            entry.get("candidate_output_path") or ""
        ).strip()
        candidate_paths = [
            str(path).strip()
            for path in entry.get("candidate_paths", [])
            if isinstance(path, str) and path.strip()
        ] if isinstance(entry.get("candidate_paths"), list) else []
        candidate_conflict_reasons: list[str] = []
        if (
            output_path
            and candidate_output_path
            and output_path != candidate_output_path
        ):
            candidate_conflict_reasons.append("selected_outputs_disagree")
        path = output_path or candidate_output_path
        if candidate_paths:
            if path and path not in candidate_paths:
                candidate_conflict_reasons.append("selected_output_not_candidate")
            elif not path and len(set(candidate_paths)) != 1:
                candidate_conflict_reasons.append("candidate_not_selected")
            elif not path:
                path = candidate_paths[0]
        if candidate_conflict_reasons:
            candidate_selection_conflicts.append({
                "location": f"planned_entries[{index}]",
                "reasons": candidate_conflict_reasons,
            })

        compact = {"beat": beat_ids[0] if beat_ids else "", "path": path}
        orphan_ids = [beat_id for beat_id in beat_ids if beat_id not in canonical_set]
        if orphan_ids:
            orphan_assignments.append({"path": path, "beat_ids": orphan_ids})

        review_status = str(entry.get("review_status") or "").strip().lower()
        closed_status = status in {"ready", "approved"}
        generated_approved = status == "approved"
        review_open = review_status in {
            "pending",
            "review_pending",
            "rejected",
        }
        if (
            not closed_status
            or review_open
            or (is_generated_chain and not generated_approved)
        ):
            open_planned_entries.append({
                **compact,
                "status": status,
                "review_status": review_status,
            })

        reasons: list[str] = []
        if is_generated_chain and not source_values:
            reasons.append("source_declaration_missing")
        elif is_generated_chain and source_values != {"generated"}:
            reasons.append("generated_chain_source_mismatch")
        if source_conflict:
            reasons.append("source_declaration_conflict")
        if beat_conflict:
            reasons.append("beat_reference_conflict")
        if candidate_conflict_reasons:
            reasons.append("candidate_selection_conflict")
        if is_generated_chain and not generated_approved:
            reasons.append("status_not_approved")
        if is_generated_chain and review_status != "approved":
            i2i_review_pending.append(compact)
            reasons.append("review_not_approved")
        if is_generated_chain and not str(entry.get("provider") or "").strip():
            reasons.append("provider_missing")
        if is_generated_chain and not str(entry.get("model") or "").strip():
            reasons.append("model_missing")
        if is_generated_chain and generated_approved:
            if not output_path:
                reasons.append("output_path_missing")
            elif not _project_local_file(root, output_path):
                reasons.append("output_missing_or_unsafe")
            reasons.extend(
                _generated_approval_evidence_issues(
                    entry,
                    output_path=output_path,
                    beat_ids=beat_ids,
                    project_id=project_id,
                    decision_log=decision_log,
                    project_dir=root,
                )
            )
        if is_generated_chain and reasons:
            i2i_issues.append({**compact, "reasons": reasons})
        if (
            not closed_status
            or review_open
            or source_conflict
            or (is_planned_image and not source_values)
            or beat_conflict
            or candidate_conflict_reasons
            or (is_generated_chain and reasons)
        ):
            continue
        if not path or (root is not None and not _project_local_file(root, path)):
            planned_output_issues.append({
                **compact,
                "reason": "output_missing_or_unsafe",
            })
            continue
        register_assignment(
            path,
            [beat_id for beat_id in beat_ids if beat_id in canonical_set],
            next(iter(source_values), "generated"),
        )

    reuse_groups = [
        {"path": path, "beat_ids": beat_ids}
        for path, beat_ids in assignments_by_path.items()
        if len(beat_ids) > 1
    ]
    reuse_pending = [
        group
        for group in reuse_groups
        if not _has_reuse_approval(
            decision_log,
            group["path"],
            group["beat_ids"],
            project_id,
        )
    ]
    assignment_conflicts = [
        {"beat_id": beat_id, "paths": paths}
        for beat_id, paths in assigned.items()
        if len(paths) > 1
    ]
    missing = [beat_id for beat_id in canonical if not assigned.get(beat_id)]
    reuse_pending_beats = {
        beat_id
        for group in reuse_pending
        for beat_id in group["beat_ids"]
    }
    i2i_pending_beats = {
        beat_id
        for issue in i2i_issues
        for beat_id in normalize_beat_ids(issue.get("beat"))
    }
    beat_statuses: dict[str, str] = {}
    for beat_id in canonical:
        if beat_id in missing:
            status = "missing"
        elif beat_id in i2i_pending_beats:
            status = "i2i_review_pending"
        elif beat_id in reuse_pending_beats:
            status = "reuse_pending"
        else:
            status = "assigned"
        beat_statuses[beat_id] = status
    approved_references = {
        beat_id: paths[0]
        for beat_id, paths in assigned.items()
        if len(paths) == 1 and beat_statuses.get(beat_id) == "assigned"
    }

    video_plan_conflicts: list[dict[str, Any]] = []
    plan_doc = (
        video_plan.get("video_plan")
        if isinstance(video_plan, dict)
        and isinstance(video_plan.get("video_plan"), dict)
        else video_plan or {}
    )
    plan_rows = (
        plan_doc.get("segments")
        if isinstance(plan_doc.get("segments"), list)
        else plan_doc.get("beats")
        if isinstance(plan_doc.get("beats"), list)
        else []
    )
    for index, row in enumerate(plan_rows):
        if not isinstance(row, dict):
            continue
        row_id = normalize_beat_ids(
            row.get("id") if "id" in row else row.get("beat")
        )
        if len(row_id) != 1 or row_id[0] not in canonical_set:
            continue
        beat_id = row_id[0]
        plan_status = str(row.get("assignment_status") or "").strip().lower()
        matrix_status = beat_statuses.get(beat_id, "")
        if plan_status and plan_status not in _CLOSED_VIDEO_PLAN_STATUSES:
            video_plan_conflicts.append({
                "location": f"video_plan[{index}]",
                "beat_id": beat_id,
                "reason": (
                    "open_assignment_status"
                    if plan_status in _OPEN_VIDEO_PLAN_STATUSES
                    else "unknown_assignment_status"
                ),
                "assignment_status": plan_status,
                "matrix_status": matrix_status,
            })
        elif (
            plan_status in _CLOSED_VIDEO_PLAN_STATUSES
            and matrix_status != "assigned"
        ):
            video_plan_conflicts.append({
                "location": f"video_plan[{index}]",
                "beat_id": beat_id,
                "reason": "closed_status_without_closed_matrix",
                "assignment_status": plan_status,
                "matrix_status": matrix_status,
            })

        plan_sources = {
            field: _normalize_asset_source(row.get(field))
            for field in ("origin", "source", "asset_source", "gap_fill")
            if _normalize_asset_source(row.get(field))
        }
        declared_sources = set(plan_sources.values())
        if len(declared_sources) > 1:
            video_plan_conflicts.append({
                "location": f"video_plan[{index}]",
                "beat_id": beat_id,
                "reason": "source_declaration_conflict",
                "declarations": plan_sources,
            })
        elif declared_sources:
            declared_source = next(iter(declared_sources))
            matrix_sources = assignment_sources.get(beat_id, set())
            if declared_source not in matrix_sources:
                video_plan_conflicts.append({
                    "location": f"video_plan[{index}]",
                    "beat_id": beat_id,
                    "reason": "source_matrix_mismatch",
                    "declared_source": declared_source,
                    "matrix_sources": sorted(matrix_sources),
                })

        declared_references = [
            str(row.get(field) or "").strip()
            for field in ("ref", "ref_image")
            if str(row.get(field) or "").strip()
        ]
        distinct_reference_keys = {
            _path_comparison_key(reference, root)
            for reference in declared_references
        }
        if len(distinct_reference_keys) > 1:
            video_plan_conflicts.append({
                "location": f"video_plan[{index}]",
                "beat_id": beat_id,
                "reason": "reference_declaration_conflict",
                "declared_references": declared_references,
            })
        elif declared_references:
            approved_path = approved_references.get(beat_id)
            if (
                approved_path
                and (
                    _path_comparison_key(declared_references[0], root)
                    != _path_comparison_key(approved_path, root)
                )
            ):
                video_plan_conflicts.append({
                    "location": f"video_plan[{index}]",
                    "beat_id": beat_id,
                    "reason": "reference_matrix_mismatch",
                    "declared_references": declared_references,
                    "approved_path": approved_path,
                })

    ready = not any(
        (
            not canonical,
            source_mismatches,
            canonical_source_conflicts,
            missing,
            orphan_assignments,
            reuse_pending,
            assignment_conflicts,
            unsafe_assignments,
            beat_reference_conflicts,
            source_conflicts,
            open_ledger_entries,
            open_planned_entries,
            planned_source_issues,
            planned_output_issues,
            candidate_selection_conflicts,
            i2i_issues,
            video_plan_conflicts,
            decision_log_issues,
        )
    )
    return {
        "canonical_beat_ids": canonical,
        "assigned": assigned,
        "missing": missing,
        "unused_assets": unused_assets,
        "reuse_groups": reuse_groups,
        "orphan_assignments": orphan_assignments,
        "reuse_pending": reuse_pending,
        "assignment_conflicts": assignment_conflicts,
        "unsafe_assignments": unsafe_assignments,
        "beat_reference_conflicts": beat_reference_conflicts,
        "source_conflicts": source_conflicts,
        "open_ledger_entries": open_ledger_entries,
        "open_planned_entries": open_planned_entries,
        "planned_source_issues": planned_source_issues,
        "planned_output_issues": planned_output_issues,
        "candidate_selection_conflicts": candidate_selection_conflicts,
        "i2i_review_pending": i2i_review_pending,
        "i2i_issues": i2i_issues,
        "video_plan_conflicts": video_plan_conflicts,
        "decision_log_issues": decision_log_issues,
        "beat_statuses": beat_statuses,
        "approved_references": approved_references,
        "beats": [
            {
                "beat_id": beat_id,
                "status": beat_statuses[beat_id],
                "paths": assigned.get(beat_id, []),
            }
            for beat_id in canonical
        ],
        "canonical_source_mismatches": source_mismatches,
        "canonical_source_conflicts": canonical_source_conflicts,
        "ready": ready,
        # Compatibility aliases used by the first contract tests.
        "unused": unused_assets,
        "orphan": orphan_assignments,
    }


def _suggested_class(filename: str) -> str:
    folded = filename.lower()
    for hints, role in _ROLE_HINTS:
        if any(hint.lower() in folded for hint in hints):
            return role
    return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _svg_length(raw: Any) -> float | None:
    value = str(raw or "").strip()
    if not value or not _SVG_LENGTH_RE.fullmatch(value):
        return None
    number = value[:-2] if value.lower().endswith("px") else value
    try:
        parsed = float(number)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _svg_image_facts(path: Path) -> tuple[int, int, list[str]] | None:
    try:
        if path.stat().st_size > _MAX_SVG_BYTES:
            return (1, 1, ["svg_too_large"])
    except OSError:
        return None
    try:
        with path.open("rb") as stream:
            payload = stream.read(_MAX_SVG_BYTES + 1)
    except OSError:
        return None
    if len(payload) > _MAX_SVG_BYTES:
        return (1, 1, ["svg_too_large"])
    folded = payload.lower().replace(b"\x00", b"")
    if b"<!doctype" in folded or b"<!entity" in folded:
        return (1, 1, ["unsafe_svg_declaration"])
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, ValueError):
        return None
    tag = root.tag if isinstance(root.tag, str) else ""
    namespace = ""
    local_name = tag
    if tag.startswith("{") and "}" in tag:
        namespace, local_name = tag[1:].split("}", 1)
    if (
        local_name.lower() != "svg"
        or namespace not in {"", "http://www.w3.org/2000/svg"}
    ):
        return None

    width = _svg_length(root.attrib.get("width"))
    height = _svg_length(root.attrib.get("height"))
    view_box = str(
        root.attrib.get("viewBox")
        or root.attrib.get("viewbox")
        or ""
    ).strip()
    if view_box:
        parts = [part for part in re.split(r"[\s,]+", view_box) if part]
        if len(parts) == 4:
            try:
                view_width = float(parts[2])
                view_height = float(parts[3])
            except ValueError:
                view_width = view_height = 0
            if math.isfinite(view_width) and view_width > 0:
                width = width or view_width
            if math.isfinite(view_height) and view_height > 0:
                height = height or view_height

    issues: list[str] = []
    if width is None or height is None:
        issues.append("svg_dimensions_missing")
    return (
        max(1, round(width or 1)),
        max(1, round(height or 1)),
        issues,
    )


def scan_user_images(project_dir: str | Path, *, min_dimension: int = 640) -> dict[str, Any]:
    """Return image facts and filename-only role suggestions without writing files."""
    project_path = Path(project_dir).resolve()
    images_dir = project_path / "assets" / "images"
    entries: list[dict[str, Any]] = []
    by_digest: dict[str, dict[str, Any]] = {}

    if images_dir.is_dir():
        images_root = images_dir.resolve()
        for path in sorted(
            images_dir.rglob("*"),
            key=lambda item: item.as_posix().lower(),
        ):
            try:
                resolved = path.resolve()
                resolved.relative_to(images_root)
            except (OSError, ValueError):
                continue
            if not resolved.is_file():
                continue
            image_issues: list[str] = []
            if resolved.suffix.lower() == ".svg":
                svg_facts = _svg_image_facts(resolved)
                if svg_facts is None:
                    continue
                width, height, image_issues = svg_facts
            else:
                try:
                    with Image.open(resolved) as image:
                        width, height = image.size
                        image.verify()
                except (OSError, UnidentifiedImageError):
                    continue

            digest = "" if "svg_too_large" in image_issues else _sha256(resolved)
            issues = list(image_issues)
            if width < min_dimension or height < min_dimension:
                issues.append("resolution_too_small")
            entry: dict[str, Any] = {
                "file": resolved.name,
                "path": resolved.relative_to(project_path).as_posix(),
                "width": width,
                "height": height,
                "bytes": resolved.stat().st_size,
                "sha256": digest,
                "suggested_class": _suggested_class(resolved.stem),
                "user_class": "",
                "status": "pending_user_confirmation",
                "issues": issues,
            }
            if digest:
                original = by_digest.get(digest)
                if original:
                    entry["duplicate_of"] = original["file"]
                else:
                    by_digest[digest] = entry
            entries.append(entry)

    low_resolution_count = sum(bool(entry["issues"]) for entry in entries)
    duplicate_group_count = sum(1 for entry in entries if entry.get("duplicate_of"))
    has_unclassified_image = any(not entry["suggested_class"] for entry in entries)
    counts = Counter(
        entry["suggested_class"] or "unclassified" for entry in entries
    )
    return {
        "version": "1.0",
        "source_dir": "assets/images",
        "entries": entries,
        "summary": {
            "total_images": len(entries),
            "low_resolution_count": low_resolution_count,
            "duplicate_group_count": duplicate_group_count,
            "counts_by_suggested_class": dict(counts),
            "needs_user_attention": (
                not entries
                or has_unclassified_image
                or bool(low_resolution_count or duplicate_group_count)
            ),
        },
    }


def duration_profile(duration_seconds: int | float) -> dict[str, Any]:
    """Return minimum / recommended image counts for a commercial duration."""
    seconds = max(0, int(duration_seconds or 0))
    if seconds <= 10:
        minimum, recommended, classes = 1, 3, _DURATION_BANDS[0][3]
        profile = "10s"
    elif seconds <= 30:
        minimum, recommended, classes = 2, 6, _DURATION_BANDS[1][3]
        profile = "30s"
    else:
        minimum, recommended, classes = 3, 10, _DURATION_BANDS[2][3]
        profile = "60s"
    return {
        "duration_profile": profile,
        "duration_seconds": seconds,
        "minimum_image_count": minimum,
        "recommended_image_count": recommended,
        "preferred_asset_classes": list(classes),
    }


def build_asset_requirements(
    *,
    duration_seconds: int | float,
    confirmed_classes: list[str],
    gap_fill: str = "none",
    user_confirmed_shortage: bool = False,
) -> dict[str, Any]:
    """Build ``asset_requirements`` after user confirms classes (no vision)."""
    profile = duration_profile(duration_seconds)
    counts = Counter(c for c in confirmed_classes if c)
    available = sum(counts.values())
    preferred = list(profile["preferred_asset_classes"])
    missing = [c for c in preferred if counts.get(c, 0) < 1]
    has_hero = counts.get("product_hero", 0) > 0

    if not has_hero:
        status_zh = "等待用户选择"
        warning = "缺少商品主图或核心参考，须补图、图生图或改为概念片后再出表 3。"
    elif available < int(profile["minimum_image_count"]):
        status_zh = "降级继续"
        warning = "图片数量低于最低可运行建议，商品一致性与镜头丰富度可能下降。"
    elif missing or available < int(profile["recommended_image_count"]):
        status_zh = "降级继续"
        warning = "图片数量或类型低于建议，商品一致性与镜头丰富度可能下降。"
    else:
        status_zh = "就绪"
        warning = ""

    return {
        **profile,
        "available_image_count": available,
        "available_asset_classes": sorted(counts.keys()),
        "missing_asset_classes": missing,
        "counts_by_class": dict(counts),
        "status": status_zh,
        "fallback": gap_fill,
        "quality_warning": warning,
        "user_confirmed_shortage": bool(user_confirmed_shortage),
    }


def build_asset_ledger(
    *,
    project_id: str,
    precheck: dict[str, Any],
    user_classes: dict[str, str],
    duration_seconds: int | float = 0,
    gap_fill: str = "none",
    identity_anchor_path: str = "",
    confirmed_at: str = "",
    entry_metadata: dict[str, dict[str, Any]] | None = None,
    planned_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge scan facts with user-confirmed classes into ``asset_ledger``."""
    metadata_by_path = entry_metadata if isinstance(entry_metadata, dict) else {}
    entries_out: list[dict[str, Any]] = []
    confirmed: list[str] = []
    for entry in precheck.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        user_class = str(
            user_classes.get(path)
            or user_classes.get(str(entry.get("file") or ""))
            or entry.get("user_class")
            or entry.get("suggested_class")
            or ""
        ).strip()
        if not user_class:
            continue
        is_anchor = bool(
            identity_anchor_path
            and (path == identity_anchor_path or entry.get("file") == identity_anchor_path)
        )
        row = deepcopy(entry)
        metadata = (
            metadata_by_path.get(path)
            or metadata_by_path.get(str(entry.get("file") or ""))
            or {}
        )
        if isinstance(metadata, dict):
            for key in _ENTRY_METADATA_FIELDS:
                if key in metadata:
                    row[key] = deepcopy(metadata[key])
        beat_ids = normalize_beat_ids(
            row.get("beats") if "beats" in row else row.get("beat")
        )
        if beat_ids:
            row["beats"] = beat_ids
            row.pop("beat", None)
        row = {
            **row,
            "user_class": user_class,
            "status": "identity_anchor" if is_anchor else "confirmed",
            "is_identity_anchor": is_anchor,
        }
        entries_out.append(row)
        confirmed.append(user_class)

    requirements = build_asset_requirements(
        duration_seconds=duration_seconds,
        confirmed_classes=confirmed,
        gap_fill=gap_fill,
        user_confirmed_shortage=gap_fill != "none",
    )
    ledger = {
        "version": "1.0",
        "project_id": project_id,
        "confirmed_at": confirmed_at,
        "gap_fill": gap_fill,
        "entries": entries_out,
        "summary": {
            "available_image_count": len(entries_out),
            "counts_by_class": dict(Counter(confirmed)),
            "missing_asset_classes": requirements.get("missing_asset_classes") or [],
            "status_zh": requirements.get("status") or "等待用户选择",
            "quality_warning": requirements.get("quality_warning") or "",
        },
        "asset_requirements": requirements,
    }
    if planned_entries is not None:
        normalized_planned: list[dict[str, Any]] = []
        for entry in planned_entries:
            if not isinstance(entry, dict):
                continue
            row = deepcopy(entry)
            beat_ids = normalize_beat_ids(
                row.get("beats") if "beats" in row else row.get("beat")
            )
            if beat_ids:
                row["beats"] = beat_ids
                row.pop("beat", None)
            normalized_planned.append(row)
        ledger["planned_entries"] = normalized_planned
    return ledger
