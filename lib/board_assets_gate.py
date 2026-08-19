"""Seal commercial assets_gate when user-upload plan is already closed."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.asset_precheck import scan_user_images, validate_beat_assignment_matrix
from lib.board_gap_plan import CLASS_NEED_ZH, projects_root
from lib.checkpoint import CheckpointValidationError, merge_write_checkpoint
from lib.paths import PROJECTS_DIR as DEFAULT_PROJECTS_DIR


class AssetsGateError(Exception):
    def __init__(self, message: str, *, code: str = "assets_gate") -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


_NEED_ZH_TO_CLASS = {zh: key for key, zh in CLASS_NEED_ZH.items()}
UNUSED_UPLOAD_NOTE_ZH = "各段已有唯一选用图，本张为多余上传，未分配到任何段。"
UNUSED_UPLOAD_REASON = "extra_unassigned_upload"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _class_for_beat(gap_plan: dict[str, Any], beat_id: str) -> str:
    for item in gap_plan.get("covered") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("beat_id") or "") != beat_id:
            continue
        need_zh = str(item.get("need_zh") or "").strip()
        if need_zh in _NEED_ZH_TO_CLASS:
            return _NEED_ZH_TO_CLASS[need_zh]
    return "product_hero"


def _precheck_row(precheck: dict[str, Any], path: str) -> dict[str, Any]:
    for entry in precheck.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("path") or "") == path:
            return dict(entry)
    return {}


def _ledger_path_key(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().casefold()


def _append_unused_uploads(
    *,
    project_dir: Path,
    precheck: dict[str, Any],
    entries: list[dict[str, Any]],
    used_paths: set[str],
) -> None:
    used_keys = {_ledger_path_key(path) for path in used_paths}
    inventory = scan_user_images(project_dir, min_dimension=1)
    unsafe: list[str] = []
    oversized: list[str] = []
    for image in inventory.get("entries") or []:
        if not isinstance(image, dict):
            continue
        path = str(image.get("path") or "").strip()
        if not path or _ledger_path_key(path) in used_keys:
            continue
        issues = image.get("issues") or []
        if isinstance(issues, list) and "unsafe_svg_declaration" in issues:
            unsafe.append(path)
            continue
        if isinstance(issues, list) and "svg_too_large" in issues:
            oversized.append(path)
            continue
        scan_row = _precheck_row(precheck, path) or dict(image)
        row = {
            **scan_row,
            "path": path,
            "file": scan_row.get("file") or Path(path).name,
            "kind": "image",
            "user_class": str(
                scan_row.get("user_class")
                or scan_row.get("suggested_class")
                or "unclassified"
            ).strip()
            or "unclassified",
            "status": "confirmed",
            "origin": "user_upload",
            "asset_source": "user_upload",
            "gap_fill": "user_upload",
            "selected": False,
            "note_zh": UNUSED_UPLOAD_NOTE_ZH,
            "reason": UNUSED_UPLOAD_REASON,
        }
        row.pop("beats", None)
        row.pop("beat", None)
        entries.append(row)
        used_keys.add(_ledger_path_key(path))
    if unsafe:
        raise AssetsGateError(
            "商品片 assets_gate 发现危险 SVG，禁止完成："
            f"{sorted(unsafe)}"
        )
    if oversized:
        raise AssetsGateError(
            "商品片 assets_gate 发现过大 SVG，禁止完成："
            f"{sorted(oversized)}"
        )


def plan_allows_auto_seal(project_dir: Path) -> bool:
    video_plan = _read_json(project_dir / "artifacts" / "video_plan.json")
    segments = video_plan.get("segments") or []
    if not segments:
        return False
    for segment in segments:
        if not isinstance(segment, dict):
            return False
        gap_fill = str(segment.get("gap_fill") or "")
        status = str(segment.get("assignment_status") or "")
        if gap_fill == "i2i" or status == "i2i_planned":
            return False
        if gap_fill != "user_upload" or status != "assigned":
            return False
        if not str(segment.get("ref_image") or "").strip():
            return False
    return True


def build_asset_ledger_from_plan(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    root = projects_root(projects_dir)
    project_dir = root / project_id
    video_plan = _read_json(project_dir / "artifacts" / "video_plan.json")
    precheck = _read_json(project_dir / "artifacts" / "asset_precheck.json")
    gap_plan = _read_json(project_dir / "artifacts" / "gap_plan.json")
    segments = [
        item for item in (video_plan.get("segments") or []) if isinstance(item, dict)
    ]
    if not segments:
        raise AssetsGateError("缺少 video_plan 分段，无法完成素材检查。")

    entries: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    counts: dict[str, int] = {}

    for segment in segments:
        beat_id = str(segment.get("beat") or segment.get("id") or "").strip()
        path = str(segment.get("ref_image") or "").strip()
        gap_fill = str(segment.get("gap_fill") or "")
        status = str(segment.get("assignment_status") or "")
        if gap_fill == "i2i" or status == "i2i_planned":
            raise AssetsGateError(
                "存在图生图计划，须在本页完成生成与审图后再进入下一步。",
                code="i2i_not_closed",
            )
        if gap_fill != "user_upload" or status != "assigned" or not beat_id or not path:
            raise AssetsGateError(
                "分段素材未全部锁定为用户图，无法自动完成素材检查。",
                code="plan_not_closed",
            )
        scan_row = _precheck_row(precheck, path)
        user_class = str(
            scan_row.get("user_class")
            or scan_row.get("suggested_class")
            or _class_for_beat(gap_plan, beat_id)
        ).strip() or "product_hero"
        counts[user_class] = counts.get(user_class, 0) + 1
        row = {
            **scan_row,
            "path": path,
            "file": scan_row.get("file") or Path(path).name,
            "kind": "image",
            "beats": [beat_id],
            "user_class": user_class,
            "status": "confirmed",
            "origin": "user_upload",
            "asset_source": "user_upload",
            "gap_fill": "user_upload",
            "selected": True,
        }
        entries.append(row)
        used_paths.add(path)

    _append_unused_uploads(
        project_dir=project_dir,
        precheck=precheck,
        entries=entries,
        used_paths=used_paths,
    )
    used_count = sum(1 for item in entries if item.get("selected") is not False)

    ledger = {
        "version": "1.0",
        "project_id": project_id,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "gap_fill": "none",
        "entries": entries,
        "summary": {
            "available_image_count": used_count,
            "counts_by_class": counts,
            "missing_asset_classes": [],
            "status_zh": "就绪",
            "quality_warning": "",
        },
    }
    result = validate_beat_assignment_matrix(
        project_id=project_id,
        segment_cards=_read_json(project_dir / "artifacts" / "segment_cards.json"),
        video_plan=video_plan,
        ledger_entries=entries,
        planned_entries=[],
        decision_log=_read_json(project_dir / "decision_log.json"),
        project_dir=project_dir,
    )
    if not result.get("ready"):
        issues = result.get("issues") or result.get("blocking_issues") or []
        detail = "; ".join(str(item) for item in issues[:3]) if issues else "矩阵未闭环"
        raise AssetsGateError(
            f"素材分配未闭环：{detail}",
            code="matrix_not_ready",
        )
    return ledger


def seal_assets_gate(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Write asset_ledger and mark assets_gate completed. No paid generate."""
    root = projects_root(projects_dir)
    project_dir = root / project_id
    ledger = build_asset_ledger_from_plan(project_id, projects_dir=root)
    art_dir = project_dir / "artifacts"
    _write_json(art_dir / "asset_ledger.json", ledger)

    brief = _read_json(art_dir / "brief.json")
    asset_precheck = _read_json(art_dir / "asset_precheck.json")
    video_plan = _read_json(art_dir / "video_plan.json")
    segment_cards = _read_json(art_dir / "segment_cards.json")
    artifacts = {
        "brief": brief,
        "asset_precheck": asset_precheck,
        "video_plan": video_plan,
        "segment_cards": segment_cards,
        "asset_ledger": ledger,
    }
    try:
        merge_write_checkpoint(
            root,
            project_id,
            "assets_gate",
            "completed",
            {
                "brief": brief,
                "asset_precheck": asset_precheck,
                "segment_cards": segment_cards,
                "asset_ledger": ledger,
            },
            pipeline_type="bootstrap-commercial",
            human_approval_required=False,
            human_approved=True,
            metadata_patch={
                "needs_user_decision": False,
                "approval_source": "panel_intent",
            },
            metadata_remove_keys=(
                "decision_title_zh",
                "decision_context_zh",
                "decision_prompt_zh",
                "decision_options",
                "recommendation_zh",
                "examples_zh",
            ),
        )
    except CheckpointValidationError as exc:
        raise AssetsGateError(str(exc), code="assets_gate_checkpoint") from exc
    return {"action": "continue", "artifacts": artifacts, "ledger": ledger}
