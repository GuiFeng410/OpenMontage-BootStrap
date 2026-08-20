"""Commercial-only read model for Backlot board state."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from backlot.read_models.common import (
    COMMERCIAL_STAGE_LABELS_ZH,
    MEDIA_IMAGE_EXT,
    MEDIA_VIDEO_EXT,
    canonical_video_candidate,
    canonical_video_path,
    rel,
    resolve_asset_path,
)
from lib.asset_precheck import (
    has_generated_image_source,
    has_generation_chain_signal,
    normalize_beat_ids,
    validate_beat_assignment_matrix,
)
from lib.board_advance import strip_recommend
from lib.experiment_budget import format_motion_mix_zh
from lib.library_create import COMMERCIAL_VIDEO_MODELS

ROLE_LABELS_ZH = {
    "product_identity_anchor": "身份基准",
    "product_angle": "角度图",
    "product_hero": "主图（仅运镜）",
    "product_detail": "细节图",
    "on_body": "佩戴图",
    "hand": "手持图",
}

_DECISION_CATEGORY_ZH = {
    "brief_selection": "方案选择",
    "review_mode_selection": "评审模式",
    "production_tier_selection": "制作档位",
    "candidate_mode_selection": "候选策略",
    "motion_mix_selection": "画面构成",
    "asset_decision": "素材决定",
    "stage_review_decision": "阶段裁定",
    "delivery_signoff": "交付确认",
    "approval_policy": "审批策略",
}


def _is_generated_image_entry(entry: dict[str, Any]) -> bool:
    path = str(
        entry.get("path")
        or entry.get("output_path")
        or entry.get("candidate_output_path")
        or ""
    ).replace("\\", "/")
    is_image = (
        str(entry.get("kind") or "").strip().lower() == "image"
        or Path(path).suffix.lower() in MEDIA_IMAGE_EXT
    )
    status = str(entry.get("status") or "").strip().lower()
    has_explicit_source = any(
        str(entry.get(field) or "").strip().lower() not in {"", "none"}
        for field in ("origin", "asset_source", "gap_fill")
    )
    return (
        has_generated_image_source(entry)
        or (
            is_image
            and (
                has_generation_chain_signal(
                    entry,
                    status,
                    include_status=False,
                )
                or (
                    not has_explicit_source
                    and has_generation_chain_signal(
                        entry,
                        status,
                        include_status=entry.get("selected") is not False,
                    )
                )
            )
        )
    )


def _commercial_decisions_summary(decision_log: dict[str, Any]) -> list[dict[str, Any]]:
    """Latest decision per category+subject for commercial board rail."""
    rows = decision_log.get("decisions") if isinstance(decision_log, dict) else None
    if not isinstance(rows, list):
        return []
    current: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        cat = str(raw.get("category") or "decision")
        subject = str(raw.get("subject") or "")
        key = f"{cat}::{subject}"
        selected = raw.get("selected")
        label = selected
        for opt in raw.get("options_considered") or []:
            if not isinstance(opt, dict):
                continue
            if (opt.get("option_id") or opt.get("label")) == selected:
                label = opt.get("label") or opt.get("label_zh") or selected
                break
        if key not in current:
            order.append(key)
        current[key] = {
            "category": cat,
            "category_zh": _DECISION_CATEGORY_ZH.get(cat, cat),
            "subject": subject,
            "selected": selected,
            "selected_label_zh": label,
            "reason": raw.get("reason") or "",
            "user_response_text": raw.get("user_response_text") or "",
        }
    return [current[k] for k in order]
def _resolve_commercial_asset(project_dir: Path, raw: str) -> Optional[str]:
    """Resolve a beat asset filename to a project-relative media path."""
    if not raw:
        return None
    if "/" in raw or "\\" in raw or Path(raw).is_absolute():
        resolved = resolve_asset_path(project_dir, raw)
        candidates = [resolved] if resolved is not None else []
    else:
        candidates = [
            project_dir / "assets" / "video" / raw,
            project_dir / "assets" / "video" / "stills" / raw,
            project_dir / "renders" / raw,
            project_dir / raw,
        ]
    for candidate in candidates:
        try:
            if candidate is None or not candidate.is_file():
                continue
            candidate.resolve().relative_to(project_dir.resolve())
            return rel(project_dir, candidate)
        except (OSError, ValueError):
            continue
    return None


def _resolve_commercial_media(
    project_dir: Path,
    raw: str,
    asset_dir: str,
    allowed_extensions: set[str],
) -> Optional[str]:
    """Resolve an allowed media file within the current project's asset dir."""
    if not raw:
        return None
    media_dir = (project_dir / "assets" / asset_dir).resolve()
    candidate = Path(raw)
    if ".." in candidate.parts:
        return None
    if candidate.is_absolute():
        path = candidate
    else:
        parts = candidate.parts
        if parts and parts[0] == "projects":
            if len(parts) < 3 or parts[1] != project_dir.name:
                return None
            path = project_dir / Path(*parts[2:])
        else:
            path = project_dir / candidate
    try:
        resolved = path.resolve()
        resolved.relative_to(media_dir)
        if (
            resolved.is_file()
            and resolved.suffix.lower() in allowed_extensions
        ):
            return rel(project_dir, resolved)
    except (OSError, ValueError):
        pass
    return None


def _resolve_commercial_image(project_dir: Path, raw: str) -> Optional[str]:
    """Resolve only allowed image files below ``assets/images``."""
    return _resolve_commercial_media(
        project_dir,
        raw,
        "images",
        MEDIA_IMAGE_EXT,
    )


def _resolve_commercial_video(project_dir: Path, raw: str) -> Optional[str]:
    """Resolve only allowed video files below ``assets/video``."""
    return _resolve_commercial_media(
        project_dir,
        raw,
        "video",
        MEDIA_VIDEO_EXT,
    )


def _resolve_commercial_stage_video(project_dir: Path, raw: Any) -> Optional[str]:
    """Resolve a non-empty, project-relative stage clip below ``assets/video``."""
    path_text = str(raw or "").strip()
    if not path_text or re.match(r"^[A-Za-z]:[\\/]", path_text):
        return None
    normalized = path_text.replace("\\", "/")
    candidate = Path(normalized)
    if candidate.is_absolute() or candidate.parts[:2] != ("assets", "video"):
        return None
    resolved = _resolve_commercial_video(project_dir, normalized)
    if resolved is None:
        return None
    try:
        if (project_dir / resolved).stat().st_size <= 0:
            return None
    except OSError:
        return None
    return resolved


def _brief_image_rows(raw_images: Any) -> list[tuple[str, dict[str, Any]]]:
    """Normalize legacy brief image maps, direct paths, and path lists."""
    rows: list[tuple[str, dict[str, Any]]] = []

    def add(raw: Any, fallback_name: str = "") -> None:
        if isinstance(raw, str):
            path = raw.strip()
            if path:
                rows.append((fallback_name or Path(path).name, {"path": path}))
        elif isinstance(raw, dict):
            path = raw.get("path")
            if isinstance(path, str) and path.strip():
                rows.append((
                    fallback_name or Path(path).name,
                    deepcopy(raw),
                ))

    if isinstance(raw_images, str):
        add(raw_images)
    elif isinstance(raw_images, list):
        for raw in raw_images:
            add(raw)
    elif isinstance(raw_images, dict):
        if isinstance(raw_images.get("path"), str):
            add(raw_images)
        else:
            for filename, raw in raw_images.items():
                add(raw, str(filename))
    return rows


def _parse_time_span(raw: str) -> tuple[Optional[float], Optional[float]]:
    """Parse '00:00-00:04' or '0-4' into start/end seconds."""
    if not raw or not isinstance(raw, str):
        return None, None
    parts = raw.replace("–", "-").split("-")
    if len(parts) != 2:
        return None, None

    def to_sec(token: str) -> Optional[float]:
        token = token.strip()
        if not token:
            return None
        if ":" in token:
            bits = token.split(":")
            try:
                if len(bits) == 2:
                    return int(bits[0]) * 60 + float(bits[1])
                if len(bits) == 3:
                    return int(bits[0]) * 3600 + int(bits[1]) * 60 + float(bits[2])
            except ValueError:
                return None
        try:
            return float(token)
        except ValueError:
            return None

    return to_sec(parts[0]), to_sec(parts[1])


def _stage_awaits_decision(stage: dict[str, Any] | None) -> bool:
    if not isinstance(stage, dict):
        return False
    status = str(stage.get("status") or "pending")
    if status == "completed":
        return False
    if status == "awaiting_human":
        return True
    return (stage.get("metadata") or {}).get("needs_user_decision") is True


def _first_decision_stage(stages: list[dict]) -> dict[str, Any] | None:
    awaiting = next((s for s in stages if s.get("status") == "awaiting_human"), None)
    if awaiting is not None:
        return awaiting
    return next((s for s in stages if _stage_awaits_decision(s)), None)


def _commercial_card_mode(stages: list[dict]) -> str:
    """plan | assets | produce — drives segment card field set."""
    by_name = {s.get("name"): s for s in stages}
    awaiting = _first_decision_stage(stages)
    if awaiting:
        name = awaiting.get("name")
        if name == "brief_locked":
            return "plan"
        if name == "assets_gate":
            return "assets"
        return "produce"
    order = [
        "brief_locked", "assets_gate", "sample_review", "segment_build",
        "draft_review", "final_compose", "delivery_signoff",
    ]
    # Farthest incomplete stage; if all done → produce (show results).
    for name in order:
        st = by_name.get(name) or {}
        status = st.get("status") or "pending"
        if status in ("pending", "in_progress", "failed"):
            if name == "brief_locked":
                return "plan"
            if name == "assets_gate":
                return "assets"
            return "produce"
    return "produce"


def build_commercial_board(
    project_dir: Path,
    marker: dict[str, Any],
    artifacts: dict[str, dict],
    stages: list[dict],
    media: dict[str, list],
    cost: Optional[dict],
    legacy_checkpoints: list[dict],
) -> dict[str, Any]:
    """Chinese evidence panel for bootstrap-commercial (P1 + P1.1)."""
    profile = marker.get("production_profile") or {}
    brief = artifacts.get("brief") or {}
    budget = brief.get("budget") or {}
    overview_doc = artifacts.get("review_overview") or {}
    segment_doc = artifacts.get("segment_cards") or {}
    video_plan = artifacts.get("video_plan") or {}
    ledger_doc = artifacts.get("asset_ledger") or {}
    precheck_doc = artifacts.get("asset_precheck") or {}
    review_mode = profile.get("review_mode") or overview_doc.get("review_mode") or "normal"
    from lib.review_interrupt import (
        confirm_stop_ids,
        normalize_review_preset,
        review_mode_zh as interrupt_mode_zh,
        user_progress,
    )
    review_preset = normalize_review_preset(profile.get("review_mode_preset"))
    confirm_ids = list(confirm_stop_ids(review_preset))
    progress = user_progress(stages, review_preset)
    usd_cny = float(profile.get("usd_cny_rate") or budget.get("usd_cny_rate") or 7.2)
    card_mode = _commercial_card_mode(stages)
    show_preview = card_mode == "produce"
    show_players = show_preview

    images: list[dict[str, Any]] = []
    image_paths_seen: set[str] = set()
    brief_images_by_beat: dict[str, str] = {}
    brief_image_candidates: list[str] = []

    def append_uploaded_image(filename: str, meta: dict[str, Any]) -> None:
        role = meta.get("role") or meta.get("user_class") or meta.get(
            "suggested_class"
        ) or ""
        rel = str(meta.get("path") or "")
        resolved = _resolve_commercial_image(project_dir, rel)
        identity = resolved or rel
        if not identity or identity in image_paths_seen:
            return
        image_paths_seen.add(identity)
        for beat_id in normalize_beat_ids(
            meta.get("beats") if "beats" in meta else meta.get("beat")
        ):
            if resolved:
                brief_images_by_beat.setdefault(beat_id, resolved)
        if resolved and resolved not in brief_image_candidates:
            brief_image_candidates.append(resolved)
        images.append({
            "file": filename or Path(rel).name,
            "role": role,
            "role_zh": ROLE_LABELS_ZH.get(role, role or "素材"),
            "path": resolved,
            "exists": resolved is not None,
            "missing_path": rel if rel and resolved is None else None,
            "hero_only_motion": role == "product_hero",
        })

    for filename, meta in _brief_image_rows(brief.get("images")):
        append_uploaded_image(filename, meta)
    for raw in precheck_doc.get("entries") or []:
        if isinstance(raw, dict):
            append_uploaded_image(str(raw.get("file") or ""), raw)

    def present(value: Any) -> bool:
        return value is not None and value != ""

    def first_present(*values: Any) -> Any:
        return next((value for value in values if present(value)), None)

    plan_doc = (
        video_plan.get("video_plan")
        if isinstance(video_plan.get("video_plan"), dict)
        else video_plan
    )
    plan_segment_rows = (
        plan_doc.get("segments")
        if isinstance(plan_doc.get("segments"), list)
        else []
    )
    plan_beat_rows = (
        plan_doc.get("beats")
        if isinstance(plan_doc.get("beats"), list)
        else []
    )
    plan_rows = plan_segment_rows or plan_beat_rows
    segment_rows = (
        segment_doc.get("segments")
        if isinstance(segment_doc.get("segments"), list)
        else []
    )

    # Segment cards are the commercial card authority.  Older projects that
    # predate segment_cards fall back to video_plan, but ledger/planned rows
    # never create cards by themselves.
    canonical_rows = segment_rows or plan_rows
    canonical_beat_ids: list[str] = []
    for row in canonical_rows:
        if not isinstance(row, dict):
            continue
        raw_id = row.get("beat") if "beat" in row else row.get("id")
        for beat_id in normalize_beat_ids(raw_id):
            if beat_id not in canonical_beat_ids:
                canonical_beat_ids.append(beat_id)
    canonical_beat_set = set(canonical_beat_ids)

    seg_by_beat: dict[str, dict] = {}

    # A real commercial run may split the same beat across video_plan
    # (method/provider/model/timing) and segment_cards (copy/shot/prompt).
    # Merge both documents by beat instead of letting one document hide the
    # other. Later segment_cards values win only when they are non-empty.
    for source_rows in (plan_rows, segment_rows):
        for row in source_rows:
            if not isinstance(row, dict):
                continue
            raw_id = row.get("beat") if "beat" in row else row.get("id")
            for beat_id in normalize_beat_ids(raw_id):
                normalized = dict(row)
                normalized["beat"] = beat_id
                normalized["time"] = first_present(
                    normalized.get("time"),
                    normalized.get("t"),
                )
                normalized["asset_plan_zh"] = first_present(
                    normalized.get("asset_plan_zh"),
                    normalized.get("purpose"),
                )
                normalized["generation_prompt_zh"] = first_present(
                    normalized.get("generation_prompt_zh"),
                    normalized.get("prompt_zh"),
                    normalized.get("video_prompt_zh"),
                )
                merged = dict(seg_by_beat.get(beat_id) or {})
                for key, value in normalized.items():
                    if present(value) or key not in merged:
                        merged[key] = value
                seg_by_beat[beat_id] = merged
    raw_ledger_entries = [
        entry for entry in (ledger_doc.get("entries") or [])
        if isinstance(entry, dict)
    ]
    raw_planned_entries = [
        entry for entry in (ledger_doc.get("planned_entries") or [])
        if isinstance(entry, dict)
    ]

    def normalize_matrix_media_path(raw: Any, kind: Any) -> Optional[str]:
        raw_path = str(raw or "").strip()
        if not raw_path:
            return None
        return (
            _resolve_commercial_video(project_dir, raw_path)
            if str(kind or "").lower() == "video"
            else _resolve_commercial_image(project_dir, raw_path)
        )

    matrix_ledger_entries: list[dict[str, Any]] = []
    for entry in raw_ledger_entries:
        normalized = deepcopy(entry)
        resolved = normalize_matrix_media_path(
            entry.get("path") or entry.get("output_path"),
            entry.get("kind"),
        )
        if resolved:
            if entry.get("path"):
                normalized["path"] = resolved
            else:
                normalized["output_path"] = resolved
        matrix_ledger_entries.append(normalized)
    matrix_planned_entries: list[dict[str, Any]] = []
    for entry in raw_planned_entries:
        normalized = deepcopy(entry)
        for field in ("output_path", "candidate_output_path"):
            resolved = normalize_matrix_media_path(entry.get(field), entry.get("kind"))
            if resolved:
                normalized[field] = resolved
        if isinstance(entry.get("candidate_paths"), list):
            normalized["candidate_paths"] = [
                normalize_matrix_media_path(path, entry.get("kind")) or path
                for path in entry["candidate_paths"]
            ]
        matrix_planned_entries.append(normalized)
    assignment_matrix = validate_beat_assignment_matrix(
        project_id=str(marker.get("project_id") or project_dir.name),
        segment_cards=segment_doc,
        video_plan=video_plan,
        ledger_entries=matrix_ledger_entries,
        planned_entries=matrix_planned_entries,
        decision_log=artifacts.get("decision_log") or {},
        project_dir=project_dir,
    )
    matrix_assigned_pairs = {
        (beat_id, path)
        for beat_id, paths in (assignment_matrix.get("assigned") or {}).items()
        for path in paths
    }

    assignment_warnings: list[dict[str, Any]] = []
    orphan_assignments: list[dict[str, Any]] = []
    unused_assets_by_path: dict[str, dict[str, Any]] = {}
    i2i_asset_paths: set[str] = set()

    def safe_path_hint(raw: Any, *, kind: str = "image") -> Optional[str]:
        raw_path = str(raw or "").strip().replace("\\", "/")
        if not raw_path:
            return None
        resolved = (
            _resolve_commercial_image(project_dir, raw_path)
            if kind == "image"
            else _resolve_commercial_video(project_dir, raw_path)
        )
        if resolved:
            return resolved
        candidate = Path(raw_path)
        expected = ("assets", "images") if kind == "image" else ("assets", "video")
        allowed = MEDIA_IMAGE_EXT if kind == "image" else MEDIA_VIDEO_EXT
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.parts[:2] != expected
            or candidate.suffix.lower() not in allowed
        ):
            return None
        return candidate.as_posix()

    def add_assignment_warning(
        reason: str,
        *,
        source: str,
        beat_ids: list[str] | None = None,
        path: Optional[str] = None,
    ) -> None:
        warning = {
            "source": source,
            "reason": reason,
            "beat_ids": beat_ids or [],
            "path": path,
        }
        if warning not in assignment_warnings:
            assignment_warnings.append(warning)

    ledger_by_beat: dict[str, list[dict]] = {}
    for index, entry in enumerate(raw_ledger_entries):
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        kind = entry.get("kind")
        resolved_rel = None
        if kind == "image" or (
            kind is None and Path(path).suffix.lower() in MEDIA_IMAGE_EXT
        ):
            kind = "image"
            resolved_rel = _resolve_commercial_image(project_dir, path)
            resolved_path = project_dir / resolved_rel if resolved_rel else None
        elif kind == "video":
            resolved_rel = _resolve_commercial_video(project_dir, path)
            resolved_path = project_dir / resolved_rel if resolved_rel else None
        else:
            resolved_path = None
        is_i2i = _is_generated_image_entry(entry)
        item = {
            "label": entry.get("label"),
            "label_zh": entry.get("label_zh") or entry.get("label") or "",
            "kind": kind,
            "origin": entry.get("origin"),
            "asset_source": entry.get("asset_source"),
            "gap_fill": entry.get("gap_fill"),
            "status": entry.get("status"),
            "review_status": entry.get("review_status"),
            "provider": entry.get("provider"),
            "model": entry.get("model"),
            "file": entry.get("file"),
            "path": rel(project_dir, resolved_path) if resolved_path else None,
            "missing_path": path if path and resolved_path is None else None,
            "exists": resolved_path is not None,
            "selected": bool(entry.get("selected")),
            "note_zh": entry.get("note_zh") or "",
            "is_i2i": is_i2i,
            "preview_kind": (
                "candidate" if is_i2i else "user_asset"
            ),
        }
        beat_ids = normalize_beat_ids(
            entry.get("beats") if "beats" in entry else entry.get("beat")
        )
        valid_ids = [beat_id for beat_id in beat_ids if beat_id in canonical_beat_set]
        orphan_ids = [beat_id for beat_id in beat_ids if beat_id not in canonical_beat_set]
        safe_path = safe_path_hint(path, kind=kind if kind in {"image", "video"} else "image")
        if is_i2i and safe_path:
            i2i_asset_paths.add(safe_path)
        if orphan_ids:
            orphan = {
                "source": f"asset_ledger.entries[{index}]",
                "beat_ids": orphan_ids,
                "path": safe_path,
                "file": entry.get("file") or (Path(safe_path).name if safe_path else None),
                "reason": "分配目标不是 canonical Beat",
            }
            orphan_assignments.append(orphan)
            add_assignment_warning(
                orphan["reason"],
                source=orphan["source"],
                beat_ids=orphan_ids,
                path=safe_path,
            )
        if entry.get("selected") is not False:
            for beat_id in valid_ids:
                beat_item = deepcopy(item)
                if (
                    is_i2i
                    and resolved_rel
                    and (beat_id, resolved_rel) in matrix_assigned_pairs
                ):
                    beat_item["preview_kind"] = "approved"
                ledger_by_beat.setdefault(beat_id, []).append(beat_item)
        if kind == "image":
            append_uploaded_image(
                str(entry.get("file") or Path(path).name),
                {
                    **entry,
                    "role": entry.get("user_class") or entry.get("role"),
                },
            )
            if (
                safe_path
                and not is_i2i
                and (entry.get("selected") is False or not valid_ids)
            ):
                reason = (
                    "未选用且未分配到 canonical Beat"
                    if entry.get("selected") is False
                    else "仅分配到非 canonical Beat"
                    if orphan_ids
                    else "未分配到任何 canonical Beat"
                )
                unused_assets_by_path[safe_path] = {
                    "path": safe_path,
                    "file": entry.get("file") or Path(safe_path).name,
                    "reason": reason,
                    "status": entry.get("status") or "unassigned",
                }

    planned_by_beat: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(raw_planned_entries):
        beat_ids = normalize_beat_ids(
            entry.get("beats") if "beats" in entry else entry.get("beat")
        )
        valid_ids = [beat_id for beat_id in beat_ids if beat_id in canonical_beat_set]
        orphan_ids = [beat_id for beat_id in beat_ids if beat_id not in canonical_beat_set]
        item = deepcopy(entry)
        status = str(item.get("status") or "").strip().lower()
        review_status = str(item.get("review_status") or "").strip().lower()
        is_i2i = _is_generated_image_entry(item)
        item.pop("path", None)
        output_path = str(
            item.get("output_path")
            or item.get("candidate_output_path")
            or ""
        )
        if status in {"ready", "approved", "review_pending", "generated"}:
            if item.get("kind") == "image":
                resolved_rel = _resolve_commercial_image(project_dir, output_path)
                resolved_output = project_dir / resolved_rel if resolved_rel else None
            elif item.get("kind") == "video":
                resolved_rel = _resolve_commercial_video(project_dir, output_path)
                resolved_output = project_dir / resolved_rel if resolved_rel else None
            else:
                resolved_output = None
            if resolved_output is not None:
                item["path"] = rel(project_dir, resolved_output)
                item["exists"] = True
                item["preview_kind"] = (
                    "candidate"
                    if item.get("kind") == "image"
                    else "approved"
                    if (
                        status == "approved"
                        or (status == "ready" and review_status == "approved")
                    )
                    else "candidate"
                )
            else:
                item["status"] = "failed"
                item["exists"] = False
                safe_output = safe_path_hint(
                    output_path,
                    kind=str(item.get("kind") or "image"),
                )
                if not safe_output:
                    output_candidate = Path(output_path.replace("\\", "/"))
                    if (
                        output_path
                        and not output_candidate.is_absolute()
                        and ".." not in output_candidate.parts
                    ):
                        safe_output = output_candidate.as_posix()
                if safe_output:
                    item["missing_output_path"] = safe_output
                item.setdefault(
                    "error_zh",
                    "输出文件不存在" if output_path else "未提供输出文件路径",
                )
        safe_output = safe_path_hint(
            output_path,
            kind=str(item.get("kind") or "image"),
        )
        if is_i2i and safe_output:
            i2i_asset_paths.add(safe_output)
        if orphan_ids:
            orphan = {
                "source": f"asset_ledger.planned_entries[{index}]",
                "beat_ids": orphan_ids,
                "path": safe_output,
                "file": (
                    item.get("file")
                    or (Path(safe_output).name if safe_output else None)
                ),
                "reason": "计划素材目标不是 canonical Beat",
            }
            orphan_assignments.append(orphan)
            add_assignment_warning(
                orphan["reason"],
                source=orphan["source"],
                beat_ids=orphan_ids,
                path=safe_output,
            )
        for beat_id in valid_ids:
            beat_item = deepcopy(item)
            if (
                beat_item.get("kind") == "image"
                and beat_item.get("path")
                and (beat_id, beat_item["path"]) in matrix_assigned_pairs
            ):
                beat_item["preview_kind"] = "approved"
            planned_by_beat.setdefault(beat_id, []).append(beat_item)

    beats: list[dict[str, Any]] = []
    overview_rows = [
        row for row in (overview_doc.get("overview") or [])
        if isinstance(row, dict)
    ]
    segment_evidence: list[dict[str, Any]] = []
    segment_by_beat: dict[str, dict[str, Any]] = {}
    seen_segment_paths: set[tuple[str, str]] = set()

    def append_segment_evidence(
        raw: dict[str, Any],
        *,
        batch_id: str = "",
        source_artifact: str = "artifacts/review_overview.json",
    ) -> None:
        output_path = str(raw.get("output_path") or "").strip()
        resolved = _resolve_commercial_stage_video(project_dir, output_path)
        if resolved is None:
            return
        beat_id = str(first_present(raw.get("beat"), raw.get("id")) or "").strip()
        identity = batch_id or beat_id
        if not identity or (identity, resolved) in seen_segment_paths:
            return
        seen_segment_paths.add((identity, resolved))
        item = deepcopy(raw)
        item["output_path"] = output_path
        item["path"] = resolved
        item["exists"] = True
        item["artifact_path"] = source_artifact
        if batch_id:
            item["batch_id"] = batch_id
        else:
            item["beat"] = beat_id
            segment_by_beat[beat_id] = item
        segment_evidence.append(item)

    for row in overview_rows:
        append_segment_evidence(row)
    referenced_batch_ids: set[str] = set()
    for batch in overview_doc.get("batches") or []:
        if not isinstance(batch, dict):
            continue
        batch_id = str(first_present(batch.get("id"), batch.get("batch_id")) or "").strip()
        if batch_id:
            referenced_batch_ids.add(batch_id)
            append_segment_evidence(batch, batch_id=batch_id)
    batch_review_sources = artifacts.get("_batch_review_sources") or {}
    for batch_id, review in (artifacts.get("batch_reviews") or {}).items():
        if not isinstance(review, dict):
            continue
        normalized_batch_id = str(
            first_present(review.get("batch_id"), review.get("id"), batch_id) or ""
        ).strip()
        source_artifact = batch_review_sources.get(batch_id)
        if normalized_batch_id in referenced_batch_ids and source_artifact:
            append_segment_evidence(
                review,
                batch_id=normalized_batch_id,
                source_artifact=source_artifact,
            )

    overview_by_beat: dict[str, dict[str, Any]] = {}
    for row in overview_rows:
        raw_id = row.get("beat") if "beat" in row else row.get("id")
        for beat_id in normalize_beat_ids(raw_id):
            if beat_id in canonical_beat_set:
                overview_by_beat.setdefault(beat_id, row)
    unambiguous_brief_reference = (
        brief_image_candidates[0]
        if len(canonical_beat_ids) == 1 and len(brief_image_candidates) == 1
        else None
    )

    reuse_groups = assignment_matrix.get("reuse_groups") or []
    reuse_pending_groups = assignment_matrix.get("reuse_pending") or []

    def group_has_beat(groups: list[dict[str, Any]], beat_id: str) -> bool:
        return any(
            beat_id in normalize_beat_ids(group.get("beat_ids"))
            for group in groups
            if isinstance(group, dict)
        )

    def is_i2i_entry(item: dict[str, Any]) -> bool:
        return _is_generated_image_entry(item)

    def i2i_assignment_state(item: dict[str, Any]) -> str:
        status = str(item.get("status") or "").strip().lower()
        review = str(item.get("review_status") or "").strip().lower()
        if status in {"failed", "rejected"} or review == "rejected":
            return "failed"
        if item.get("preview_kind") == "approved":
            return "approved"
        if status in {"generating", "in_progress"}:
            return "generating"
        if review == "approved":
            return "failed"
        if (
            status in {
                "ready",
                "approved",
                "generated",
                "review_pending",
                "i2i_review_pending",
            }
            or review in {"pending", "review_pending"}
        ):
            return "review_pending"
        return "i2i_planned"

    assignment_status_zh = {
        "user_asset": "用户素材",
        "reuse_pending": "复用待确认",
        "reuse_approved": "复用已确认",
        "missing": "缺少素材",
        "i2i_planned": "I2I 待生成",
        "generating": "I2I 生成中",
        "review_pending": "I2I 待审",
        "approved": "I2I 已批准",
        "failed": "I2I 失败",
        "assignment_conflict": "素材冲突",
    }
    assignment_reasons = {
        "user_asset": "已由该 Beat 专用的用户上传素材覆盖。",
        "reuse_pending": "同一真实素材分配到多个 Beat，等待精确复用确认。",
        "reuse_approved": "同一真实素材的跨 Beat 复用已按范围确认。",
        "missing": "没有账本闭环素材；参考图仅供核对，不计为已分配。",
        "i2i_planned": "已规划 I2I 补图，尚未开始生成。",
        "generating": "I2I 补图正在生成，尚不可作为批准素材。",
        "review_pending": "I2I 已生成候选，等待审查批准。",
        "approved": "I2I 输出已审查并批准用于该 Beat。",
        "failed": "I2I 生成或审查失败，需要重试或改用其它素材。",
        "assignment_conflict": "素材冲突：同一 Beat 存在多个不同的闭环素材，必须确认唯一选用项。",
    }

    for beat_id in canonical_beat_ids:
        row = overview_by_beat.get(beat_id) or {}
        plan = seg_by_beat.get(beat_id) or {}
        asset = first_present(row.get("asset"), plan.get("asset")) or ""
        asset_alt = first_present(row.get("asset_alt"), plan.get("asset_alt")) or ""
        resolved_asset = _resolve_commercial_asset(project_dir, asset) if asset else None
        reviewed_segment = segment_by_beat.get(beat_id)
        if reviewed_segment is not None:
            resolved_asset = reviewed_segment["path"]
        resolved_asset_alt = (
            _resolve_commercial_asset(project_dir, asset_alt) if asset_alt else None
        )
        t0 = plan.get("t_start")
        t1 = plan.get("t_end")
        if t0 is None or t1 is None:
            t0, t1 = _parse_time_span(first_present(row.get("time"), plan.get("time")) or "")
        explicit_reference = first_present(
            row.get("ref"),
            plan.get("ref"),
            plan.get("ref_image"),
        )
        reference_path = (
            _resolve_commercial_image(project_dir, str(explicit_reference or ""))
            if explicit_reference
            else None
        )
        if explicit_reference:
            reference = explicit_reference
        else:
            reference_path = (
                brief_images_by_beat.get(beat_id)
                or unambiguous_brief_reference
            )
            reference = reference_path
        beat_ledger = ledger_by_beat.get(beat_id) or []
        beat_planned = planned_by_beat.get(beat_id) or []
        assigned_paths = list(
            dict.fromkeys((assignment_matrix.get("assigned") or {}).get(beat_id) or [])
        )
        i2i_rows = [
            item for item in [*beat_ledger, *beat_planned]
            if is_i2i_entry(item)
        ]
        has_assignment_conflict = any(
            conflict.get("beat_id") == beat_id
            for conflict in assignment_matrix.get("assignment_conflicts") or []
            if isinstance(conflict, dict)
        )
        closed_user_paths = {
            item.get("path")
            for item in beat_ledger
            if (
                item.get("preview_kind") == "user_asset"
                and item.get("path") in assigned_paths
            )
        }
        closed_i2i_paths = {
            item.get("path")
            for item in [*beat_ledger, *beat_planned]
            if (
                is_i2i_entry(item)
                and item.get("preview_kind") == "approved"
                and item.get("path") in assigned_paths
            )
        }
        plan_gap = str(plan.get("gap_fill") or "")
        if has_assignment_conflict:
            assignment_status = "assignment_conflict"
        elif closed_user_paths and group_has_beat(reuse_groups, beat_id):
            assignment_status = (
                "reuse_pending"
                if group_has_beat(reuse_pending_groups, beat_id)
                else "reuse_approved"
            )
        elif closed_user_paths:
            assignment_status = "user_asset"
        elif closed_i2i_paths:
            assignment_status = "approved"
        elif i2i_rows:
            assignment_status = i2i_assignment_state(i2i_rows[-1])
        elif (assignment_matrix.get("assigned") or {}).get(beat_id):
            assignment_status = "user_asset"
        else:
            plan_status = str(plan.get("assignment_status") or "")
            plan_ref = str(plan.get("ref_image") or plan.get("ref") or "")
            plan_ref_resolved = (
                _resolve_commercial_image(project_dir, plan_ref) if plan_ref else None
            )
            if (
                plan_gap == "user_upload"
                and plan_status == "assigned"
                and plan_ref_resolved
            ):
                assignment_status = "user_asset"
            else:
                assignment_status = "missing"
        reuse_status = (
            assignment_status
            if assignment_status in {"reuse_pending", "reuse_approved"}
            else None
        )
        required_raw = first_present(row.get("need_count"), plan.get("need_count"), 1)
        try:
            required_count = max(0, int(required_raw))
        except (TypeError, ValueError):
            required_count = 1
        available_count = len(assigned_paths)
        card_warnings: list[str] = []
        assignment_warning = None
        if (
            explicit_reference
            and reference_path
            and reference_path not in assigned_paths
        ):
            assignment_warning = "账本映射待补齐"
            card_warnings.append(assignment_warning)
            add_assignment_warning(
                assignment_warning,
                source="video_plan",
                beat_ids=[beat_id],
                path=reference_path,
            )
        if has_assignment_conflict:
            card_warnings.append("同一 Beat 存在多个闭环素材，需确认唯一选用项")
        candidate_previews: list[dict[str, Any]] = []
        for item in [*beat_ledger, *beat_planned]:
            if (
                item.get("kind") == "image"
                and item.get("path")
                and item.get("exists") is True
                and item.get("preview_kind") == "candidate"
            ):
                candidate_previews.append({
                    "path": item["path"],
                    "file": item.get("file") or Path(item["path"]).name,
                    "label_zh": item.get("label_zh") or "生成图候选",
                    "status": i2i_assignment_state(item),
                    "review_status": item.get("review_status"),
                    "provider": item.get("provider"),
                    "model": item.get("model"),
                })
        assignment_reason = assignment_reasons[assignment_status]
        if (
            assignment_status == "user_asset"
            and not closed_user_paths
            and not (assignment_matrix.get("assigned") or {}).get(beat_id)
        ):
            assignment_reason = (
                "方案已锁定用户图；点「进入下一步」后写入账本并闭环。"
            )
        beats.append({
            "beat": beat_id,
            "time": first_present(row.get("time"), plan.get("time")),
            "t_start": t0,
            "t_end": t1,
            "method": first_present(row.get("method"), plan.get("method")),
            "provider": first_present(row.get("provider"), plan.get("provider")),
            "model": first_present(row.get("model"), plan.get("model")),
            "generation_prompt_zh": first_present(
                row.get("generation_prompt_zh"),
                row.get("prompt_zh"),
                row.get("video_prompt_zh"),
                plan.get("generation_prompt_zh"),
            ),
            "angle_use": first_present(row.get("angle_use"), plan.get("angle_use")),
            "status": first_present(row.get("status"), plan.get("status")),
            "ref": reference,
            "reference_path": reference_path,
            "asset_path": resolved_asset,
            "asset_missing_path": asset if asset and not resolved_asset else None,
            "asset_alt_path": resolved_asset_alt,
            "asset_alt_missing_path": asset_alt if asset_alt and not resolved_asset_alt else None,
            "asset_plan_zh": first_present(row.get("asset_plan_zh"), plan.get("asset_plan_zh")),
            "copy_plan_zh": first_present(row.get("copy_plan_zh"), plan.get("copy_plan_zh")),
            "shot_plan_zh": first_present(row.get("shot_plan_zh"), plan.get("shot_plan_zh")),
            "gap_status": first_present(row.get("gap_status"), plan.get("gap_status")),
            "need_detail_zh": first_present(
                row.get("need_detail_zh"),
                plan.get("need_detail_zh"),
            ),
            "gap_fill": plan_gap or None,
            "assignment_status": assignment_status,
            "assignment_status_zh": assignment_status_zh[assignment_status],
            "assignment_reason": assignment_reason,
            "assignment_warning": assignment_warning,
            "assignment_warnings": card_warnings,
            "required_count": required_count,
            "available_count": available_count,
            "reuse_status": reuse_status,
            # Keep legacy names stable while exposing the unified counters.
            "need_count": first_present(
                row.get("need_count"),
                plan.get("need_count"),
                required_count,
            ),
            "have_count": first_present(
                row.get("have_count"),
                plan.get("have_count"),
                available_count,
            ),
            "ledger": beat_ledger,
            "ledger_preview": beat_ledger,
            "planned_entries": beat_planned,
            "planned_preview": beat_planned,
            "candidate_previews": candidate_previews,
        })

    assigned_upload_paths = {
        path
        for paths in (assignment_matrix.get("assigned") or {}).values()
        for path in paths
    }
    for image in images:
        path = image.get("path")
        if (
            path
            and path not in assigned_upload_paths
            and path not in i2i_asset_paths
        ):
            unused_assets_by_path.setdefault(path, {
                "path": path,
                "file": image.get("file") or Path(path).name,
                "reason": "未分配到任何 canonical Beat",
                "status": "unassigned",
            })
    for field, reason in (
        ("canonical_source_conflicts", "canonical Beat 来源存在冲突"),
        ("beat_reference_conflicts", "beat 与 beats 字段存在冲突"),
        ("source_conflicts", "素材来源声明存在冲突"),
        ("assignment_conflicts", "同一 Beat 存在多个闭环素材"),
        ("open_ledger_entries", "账本素材状态尚未闭环"),
        ("open_planned_entries", "计划素材状态尚未闭环"),
        ("planned_source_issues", "计划图片缺少明确来源"),
        ("planned_output_issues", "计划输出缺失或不安全"),
        ("candidate_selection_conflicts", "候选素材尚未唯一选定"),
        ("i2i_issues", "I2I 素材尚未完成批准闭环"),
        ("video_plan_conflicts", "video_plan 与素材矩阵不一致"),
        ("decision_log_issues", "decision_log 项目标识不一致"),
    ):
        rows = assignment_matrix.get(field) or []
        if rows:
            add_assignment_warning(
                reason,
                source=f"assignment_matrix.{field}",
            )

    duration = (
        segment_doc.get("duration_seconds")
        or profile.get("duration_seconds")
        or brief.get("duration_seconds")
        or 0
    )
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0.0
    if not duration and beats:
        ends = [b["t_end"] for b in beats if b.get("t_end") is not None]
        duration = max(ends) if ends else 0.0

    beat_marks: list[dict[str, Any]] = []
    batch_seconds: set[float] = set()
    if review_mode == "pro":
        for batch in overview_doc.get("batches") or []:
            if not isinstance(batch, dict):
                continue
            _a, b_end = _parse_time_span(batch.get("span") or "")
            if b_end is None or not duration:
                continue
            if 0 < b_end < duration:
                batch_seconds.add(float(b_end))

    for b in beats:
        if b.get("t_end") is not None and duration and b["t_end"] < duration:
            sec = float(b["t_end"])
            # Skip beat tick when a batch boundary already sits on this second.
            if sec in batch_seconds:
                continue
            beat_marks.append({
                "seconds": sec,
                "kind": "beat",
                "label": f"{sec:g}s",
                "beat": b.get("beat"),
            })

    batch_marks: list[dict[str, Any]] = []
    if review_mode == "pro":
        for batch in overview_doc.get("batches") or []:
            if not isinstance(batch, dict):
                continue
            _a, b_end = _parse_time_span(batch.get("span") or "")
            if b_end is None or not duration:
                continue
            if 0 < b_end < duration:
                batch_marks.append({
                    "seconds": float(b_end),
                    "kind": "batch",
                    "label": f"{float(b_end):g}s",
                    "batch_id": batch.get("id"),
                })

    awaiting = _first_decision_stage(stages)
    decision = None
    if awaiting:
        meta = strip_recommend(awaiting.get("metadata") or {})
        name = awaiting.get("name") or ""
        decision = {
            "stage": name,
            "stage_label_zh": awaiting.get("label_zh") or COMMERCIAL_STAGE_LABELS_ZH.get(name, name),
            "title_zh": meta.get("decision_title_zh"),
            "prompt_zh": meta.get("decision_prompt_zh"),
            "context_zh": meta.get("decision_context_zh"),
            "options": meta.get("decision_options") if isinstance(meta.get("decision_options"), list) else [],
            "approval_note": meta.get("approval_note"),
            "examples_zh": meta.get("examples_zh"),
            "gap_plan": meta.get("gap_plan") if isinstance(meta.get("gap_plan"), dict) else None,
            "producing_wait": bool(meta.get("producing_wait")),
        }

    def evidence_media(raw: Any) -> dict[str, Any]:
        path = str(raw or "").strip()
        resolved = canonical_video_path(project_dir, path)
        if resolved is not None:
            return {
                "path": resolved,
                "exists": True,
                "missing_path": None,
                "reason_code": None,
                "missing_reason_zh": None,
                "conflict_with": None,
            }
        candidate = canonical_video_candidate(project_dir, path)
        is_missing = candidate is not None and not candidate.exists()
        return {
            "path": None,
            "exists": False,
            "missing_path": path or None,
            "reason_code": (
                "missing_stage_media"
                if is_missing
                else ("invalid_stage_media" if path else None)
            ),
            "missing_reason_zh": (
                f"媒体文件不存在：{path}"
                if is_missing
                else (
                    "阶段 canonical 媒体必须是当前项目内存在、非空视频文件。"
                    if path
                    else None
                )
            ),
            "conflict_with": None,
        }

    def invalidate_reused_evidence(
        evidence: dict[str, Any],
        later_stage: str,
    ) -> None:
        reused_path = evidence.get("path")
        evidence.update({
            "path": None,
            "exists": False,
            "missing_path": reused_path,
            "reason_code": "canonical_path_conflict",
            "missing_reason_zh": (
                f"canonical 路径冲突：前序阶段与后续 {later_stage} "
                "复用同一视频，前序证据按缺失处理。"
            ),
            "conflict_with": later_stage,
        })

    decision_rows = _commercial_decisions_summary(artifacts.get("decision_log") or {})
    delivery_row = next(
        (row for row in reversed(decision_rows) if row.get("category") == "delivery_signoff"),
        None,
    )
    sample_doc = artifacts.get("sample_reel") or {}
    draft_doc = artifacts.get("full_draft_pro") or {}
    final_review = artifacts.get("final_review") or {}
    sample_media = evidence_media(sample_doc.get("path"))
    draft_media = evidence_media(draft_doc.get("path"))
    final_media = evidence_media(final_review.get("output_path"))
    if final_media.get("path"):
        for earlier_media in (sample_media, draft_media):
            if earlier_media.get("path") == final_media["path"]:
                invalidate_reused_evidence(earlier_media, "compose")
        for segment_media in segment_evidence:
            if segment_media.get("path") == final_media["path"]:
                invalidate_reused_evidence(segment_media, "compose")
    if (
        draft_media.get("path")
        and sample_media.get("path") == draft_media["path"]
    ):
        invalidate_reused_evidence(sample_media, "draft")
    if draft_media.get("path"):
        for segment_media in segment_evidence:
            if segment_media.get("path") == draft_media["path"]:
                invalidate_reused_evidence(segment_media, "draft")
    if sample_media.get("path"):
        for segment_media in segment_evidence:
            if segment_media.get("path") == sample_media["path"]:
                invalidate_reused_evidence(sample_media, "segment")
                break
    for beat in beats:
        segment_media = segment_by_beat.get(str(beat.get("beat") or ""))
        if (
            segment_media
            and segment_media.get("reason_code") == "canonical_path_conflict"
        ):
            beat["asset_path"] = None
            beat["asset_conflict_reason_zh"] = segment_media.get(
                "missing_reason_zh"
            )
    sample_beat_ids: list[str] = []
    raw_sample_beat_ids = sample_doc.get("beat_ids")
    if not isinstance(raw_sample_beat_ids, list):
        raw_sample_beat_ids = []
    for raw_beat_id in raw_sample_beat_ids:
        beat_id = str(raw_beat_id).strip() if isinstance(raw_beat_id, str) else ""
        if beat_id and beat_id not in sample_beat_ids:
            sample_beat_ids.append(beat_id)

    def named_render_candidate(kind: str) -> dict[str, Any] | None:
        """Find explicit legacy sample/draft names without treating them as evidence."""
        for render in media.get("renders") or []:
            path = str(render.get("path") or "")
            filename = Path(path).name.lower()
            matches = (
                "sample" in filename
                if kind == "sample"
                else ("full_draft" in filename or "draft" in filename)
            )
            if matches:
                return {"path": path, "exists": True}
        return None

    sample_attached = bool(sample_doc)
    draft_attached = bool(draft_doc)
    sample_candidate = None if sample_attached else named_render_candidate("sample")
    draft_candidate = None if draft_attached else named_render_candidate("draft")
    stage_evidence = {
        "sample": {
            **sample_media,
            "beat_ids": sample_beat_ids,
            "artifact_path": "artifacts/sample_reel.json" if sample_attached else None,
            "evidence_attached": sample_attached,
            "candidate": sample_candidate,
            "duration_seconds": sample_doc.get("duration_seconds"),
            "status": sample_doc.get("status"),
            "user_confirmation_text": (
                sample_doc.get("user_confirmation_text")
                or sample_doc.get("approval_text")
                or sample_doc.get("user_response_text")
            ),
        },
        "segment": segment_evidence,
        "draft": {
            **draft_media,
            "artifact_path": "artifacts/full_draft_pro.json" if draft_attached else None,
            "evidence_attached": draft_attached,
            "candidate": draft_candidate,
            "status": draft_doc.get("status"),
            "issue_segments": draft_doc.get("issue_segments") or [],
            "modification_list": draft_doc.get("modification_list") or [],
        },
        "compose": {
            **final_media,
            "status": final_review.get("status"),
            "technical_probe": (final_review.get("checks") or {}).get("technical_probe") or {},
            "issues_found": final_review.get("issues_found") or [],
        },
        "delivery": {
            **final_media,
            "quality_status": final_review.get("status"),
            "issues_found": final_review.get("issues_found") or [],
            "decision": delivery_row.get("selected") if delivery_row else None,
            "decision_label_zh": delivery_row.get("selected_label_zh") if delivery_row else None,
            "decision_response_zh": delivery_row.get("user_response_text") if delivery_row else None,
        },
    }

    players: list[dict[str, str]] = []
    if show_players:
        seen_player_paths: set[str] = set()

        def append_player(label: str, item: dict[str, Any] | None) -> None:
            if not item or not item.get("path") or item["path"] in seen_player_paths:
                return
            seen_player_paths.add(item["path"])
            players.append({"label": label, "path": item["path"]})

        append_player("试片", sample_media)
        append_player("完整初稿", draft_media)
        append_player("终稿", final_media)
        for render in media.get("renders") or []:
            if render["path"] in seen_player_paths:
                continue
            fname = Path(render.get("path") or "").name
            lower = fname.lower()
            batch_match = re.search(r"batch[_-]?(\d+)", lower)
            if "sample" in lower:
                label = "试片" if sample_attached else "未挂接阶段证据 · 试片候选"
            elif "full_draft" in lower or "draft" in lower:
                label = "完整初稿" if draft_attached else "未挂接阶段证据 · 初稿候选"
            elif batch_match:
                label = f"第{int(batch_match.group(1))}批预览"
            elif "final" in lower:
                label = "终稿"
            else:
                label = fname
            append_player(label, render)

    spent_usd = None
    if cost and cost.get("total_spent_usd") is not None:
        spent_usd = float(cost["total_spent_usd"])
    elif artifacts.get("cost_log"):
        spent_usd = float((artifacts["cost_log"] or {}).get("budget_spent_usd") or 0)
    budget_cny = profile.get("budget_cny") or budget.get("budget_cny")
    spent_cny = round(spent_usd * usd_cny, 3) if spent_usd is not None else None
    remaining_cny = (
        round(float(budget_cny) - spent_cny, 3)
        if budget_cny is not None and spent_cny is not None
        else None
    )

    motion_mix = profile.get("motion_mix") or brief.get("motion_mix")
    ai_share_raw = profile.get("ai_share_pct")
    if ai_share_raw is None:
        ai_share_raw = brief.get("ai_share_pct")
    motion_mix_zh = format_motion_mix_zh(
        motion_mix=motion_mix,
        ai_share_pct=ai_share_raw,
    )

    video_model = profile.get("video_model") or brief.get("channel", {}).get("video_model")
    video_model_zh = next(
        (item["label_zh"] for item in COMMERCIAL_VIDEO_MODELS if item["id"] == video_model),
        video_model,
    )
    tier_labels = {"heavy": "重", "medium": "中", "light": "轻"}
    mode_labels = {"pro": "专业", "normal": "普通", "minimal": "极简"}
    display_mode_zh = interrupt_mode_zh(review_preset, review_mode) or mode_labels.get(
        review_mode, review_mode
    )
    candidate_labels = {"stable_dual": "稳定双候选", "adaptive": "自适应"}

    return {
        "review_mode": review_preset or review_mode,
        "review_mode_preset": review_preset,
        "confirm_stop_ids": confirm_ids,
        "user_stage_zh": progress.get("label_zh"),
        "card_mode": card_mode,
        "show_preview": show_preview,
        "show_players": show_players,
        "overall_prompt_zh": segment_doc.get("overall_prompt_zh"),
        "brief_summary": {
            "theme": brief.get("theme") or marker.get("title"),
            "duration_seconds": profile.get("duration_seconds") or brief.get("duration_seconds") or duration,
            "production_tier": tier_labels.get(profile.get("production_tier"), profile.get("production_tier")),
            "video_channel": (profile.get("video_channel") or brief.get("channel", {}).get("video_channel") or "").upper(),
            "review_mode_zh": display_mode_zh,
            "imported_asset_count": profile.get("imported_asset_count"),
            "motion_mix_zh": motion_mix_zh,
            "motion_mix": motion_mix,
            "ai_share_pct": ai_share_raw,
            "budget_cny": budget_cny,
            "style_label_zh": profile.get("style_label_zh"),
            "video_model": video_model,
            "video_model_zh": video_model_zh,
            "candidate_mode_zh": candidate_labels.get(profile.get("candidate_mode")),
        },
        "assets": images,
        "asset_precheck": {
            "summary": precheck_doc.get("summary") or {},
            "entries": precheck_doc.get("entries") or [],
        },
        "asset_vision": artifacts.get("asset_vision") or {},
        "beats": beats,
        "unused_assets": list(unused_assets_by_path.values()),
        "orphan_assignments": orphan_assignments,
        "assignment_warnings": assignment_warnings,
        "timeline": {
            "duration_seconds": duration,
            "beat_marks": beat_marks,
            "batch_marks": batch_marks,
        },
        "batches": overview_doc.get("batches") or [],
        "batch_reviews": artifacts.get("batch_reviews") or {
            key: value
            for key, value in {
                "batch_01": artifacts.get("batch01_review"),
                "batch_02": artifacts.get("batch02_review"),
            }.items()
            if value is not None
        },
        "decision": decision,
        "decisions": decision_rows,
        "legacy_checkpoints": legacy_checkpoints,
        "stage_evidence": stage_evidence,
        "plan_archive": {
            "overall_prompt_zh": segment_doc.get("overall_prompt_zh") or "",
            "has_brief": bool(brief),
            "has_video_plan": bool(artifacts.get("video_plan")),
            "has_segment_cards": bool(segment_doc),
            "segment_count": len(beats),
            "sealed_zh": (
                "方案证据已落盘"
                if brief and (artifacts.get("video_plan") or segment_doc)
                else "方案证据不完整：请确认 Agent 已写入 brief / video_plan / segment_cards"
            ),
        },
        "players": players,
        "cost_cny": {
            "spent_cny": spent_cny,
            "spent_usd": spent_usd,
            "budget_cny": budget_cny,
            "remaining_cny": remaining_cny,
            "usd_cny_rate": usd_cny,
        },
    }
