"""Run authorized image-to-image at assets_gate. Browser never calls APIs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lib.board_gap_plan import projects_root

GenerateFn = Callable[..., dict[str, Any]]

STATUS_PLANNED = "i2i_planned"
STATUS_GENERATING = "generating"
STATUS_REVIEW = "i2i_review_pending"
STATUS_ASSIGNED = "assigned"


class BoardI2IError(Exception):
    def __init__(self, message: str, *, code: str = "i2i") -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


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


def _segments(video_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = video_plan.get("segments") or []
    return [item for item in rows if isinstance(item, dict)]


def planned_output_path(beat_id: str) -> str:
    return f"assets/images/i2i_{beat_id}.png"


def i2i_mode(project_dir: Path) -> str:
    """user_ready | i2i_planned | generating | i2i_review | open."""
    video_plan = _read_json(project_dir / "artifacts" / "video_plan.json")
    statuses = {
        str(item.get("assignment_status") or "")
        for item in _segments(video_plan)
        if str(item.get("gap_fill") or "") == "i2i"
        or str(item.get("assignment_status") or "")
        in {STATUS_PLANNED, STATUS_GENERATING, STATUS_REVIEW}
    }
    if STATUS_GENERATING in statuses:
        return "generating"
    if STATUS_PLANNED in statuses:
        return "i2i_planned"
    if STATUS_REVIEW in statuses:
        return "i2i_review"
    if any(str(item.get("gap_fill") or "") == "i2i" for item in _segments(video_plan)):
        if all(
            str(item.get("assignment_status") or "") == STATUS_ASSIGNED
            and str(item.get("ref_image") or "").strip()
            for item in _segments(video_plan)
            if str(item.get("gap_fill") or "") == "i2i"
        ):
            return "user_ready"
    open_fill = {
        str(item.get("gap_fill") or "")
        for item in _segments(video_plan)
        if str(item.get("assignment_status") or "")
        not in {STATUS_ASSIGNED, "ready", "approved"}
    }
    if open_fill:
        return "open"
    return "user_ready"


def _source_image(segments: list[dict[str, Any]]) -> str:
    for item in segments:
        if str(item.get("gap_fill") or "") != "user_upload":
            continue
        path = str(item.get("ref_image") or "").strip()
        if path:
            return path
    raise BoardI2IError(
        "图生图需要一张已锁定的用户图作参考。请先补传主图。",
        code="i2i_source_missing",
    )


def _prompt_for_beat(cards: dict[str, Any], beat_id: str) -> str:
    for item in cards.get("segments") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("beat") or "") != beat_id:
            continue
        parts = [
            str(item.get("copy_plan_zh") or "").strip(),
            str(item.get("shot_plan_zh") or "").strip(),
            str(item.get("asset_plan_zh") or "").strip(),
        ]
        text = "；".join(part for part in parts if part)
        if text:
            return text
    return f"基于商品主图生成 {beat_id} 所需角度，保持同一商品身份。"


def _default_generate(
    provider: str,
    prompt: str,
    output_path: str,
    extras: dict[str, Any],
) -> dict[str, Any]:
    from openmontage.mcp.providers_image.tools import image_generate

    return image_generate(
        provider,
        prompt,
        output_path,
        extras_json=json.dumps(extras, ensure_ascii=False),
        confirm=True,
        confirm_sample_ok=True,
    )


def run_i2i_generate(
    project_id: str,
    *,
    projects_dir: Path | None = None,
    generate: GenerateFn | None = None,
) -> dict[str, Any]:
    """Generate pending i2i beats. Does not seal assets_gate or start video."""
    root = projects_root(projects_dir)
    project_dir = root / project_id
    art_dir = project_dir / "artifacts"
    video_plan = _read_json(art_dir / "video_plan.json")
    cards = _read_json(art_dir / "segment_cards.json")
    segments = _segments(video_plan)
    source = _source_image(segments)
    source_abs = project_dir / source
    if not source_abs.is_file():
        raise BoardI2IError(
            f"参考图不存在：{source}",
            code="i2i_source_missing",
        )
    generate_fn = generate or _default_generate
    written: list[str] = []
    for segment in segments:
        status = str(segment.get("assignment_status") or "")
        gap_fill = str(segment.get("gap_fill") or "")
        if gap_fill != "i2i" and status not in {STATUS_PLANNED, STATUS_REVIEW}:
            continue
        if status == STATUS_ASSIGNED and str(segment.get("ref_image") or "").strip():
            continue
        beat_id = str(segment.get("beat") or segment.get("id") or "").strip()
        if not beat_id:
            continue
        provider = str(segment.get("provider") or segment.get("model") or "").strip()
        if not provider:
            raise BoardI2IError(
                f"{beat_id} 未锁定生图模型，不能生成。",
                code="i2i_model_missing",
            )
        dest_rel = str(segment.get("planned_output_path") or "").strip() or planned_output_path(
            beat_id
        )
        dest_abs = project_dir / dest_rel
        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        segment["assignment_status"] = STATUS_GENERATING
        segment["planned_output_path"] = dest_rel
        _write_json(art_dir / "video_plan.json", video_plan)
        extras = {
            "operation": "image_to_image",
            "image_path": str(source_abs),
            "n": 1,
        }
        try:
            result = generate_fn(
                provider,
                _prompt_for_beat(cards, beat_id),
                str(dest_abs),
                extras,
            )
        except Exception as exc:
            segment["assignment_status"] = STATUS_PLANNED
            _write_json(art_dir / "video_plan.json", video_plan)
            raise BoardI2IError(
                f"{beat_id} 补图失败：{exc}",
                code="i2i_generate_failed",
            ) from exc
        if isinstance(result, dict) and result.get("success") is False:
            segment["assignment_status"] = STATUS_PLANNED
            _write_json(art_dir / "video_plan.json", video_plan)
            raise BoardI2IError(
                f"{beat_id} 补图失败：{result.get('error') or '未知错误'}",
                code="i2i_generate_failed",
            )
        if not dest_abs.is_file() or dest_abs.stat().st_size <= 0:
            out = ""
            if isinstance(result, dict):
                out = str(result.get("output_path") or "")
            if out:
                out_path = Path(out)
                if out_path.is_file() and out_path != dest_abs:
                    dest_abs.write_bytes(out_path.read_bytes())
        if not dest_abs.is_file() or dest_abs.stat().st_size <= 0:
            segment["assignment_status"] = STATUS_PLANNED
            _write_json(art_dir / "video_plan.json", video_plan)
            raise BoardI2IError(
                f"{beat_id} 补图未写出文件。",
                code="i2i_output_missing",
            )
        rel = dest_rel.replace("\\", "/")
        segment["assignment_status"] = STATUS_REVIEW
        segment["gap_fill"] = "i2i"
        segment["asset_source"] = "i2i"
        segment["planned_output_path"] = rel
        segment["candidate_paths"] = [rel]
        segment.pop("ref_image", None)
        written.append(rel)
        _write_json(art_dir / "video_plan.json", video_plan)
    if not written:
        raise BoardI2IError("没有待生成的图生图分段。", code="i2i_nothing_to_generate")
    return {"action": "generate", "paths": written}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approve_pending_i2i(
    project_id: str,
    *,
    projects_dir: Path | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Mark review-pending i2i outputs approved and backfill ref_image."""
    root = projects_root(projects_dir)
    project_dir = root / project_id
    art_dir = project_dir / "artifacts"
    video_plan = _read_json(art_dir / "video_plan.json")
    log_path = project_dir / "decision_log.json"
    log = _read_json(log_path)
    decisions = log.get("decisions") if isinstance(log.get("decisions"), list) else []
    if not isinstance(log.get("project_id"), str) or not log.get("project_id"):
        log = {"version": "1.0", "project_id": project_id, "decisions": decisions}
    approved: list[str] = []
    response = (note or "").strip() or "通过这些补图。"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for segment in _segments(video_plan):
        if str(segment.get("assignment_status") or "") != STATUS_REVIEW:
            continue
        beat_id = str(segment.get("beat") or segment.get("id") or "").strip()
        rel = str(segment.get("planned_output_path") or "").strip()
        candidates = segment.get("candidate_paths") or []
        if not rel and isinstance(candidates, list) and candidates:
            rel = str(candidates[0] or "").strip()
        if not beat_id or not rel:
            raise BoardI2IError(
                "补图候选不完整，无法批准。",
                code="i2i_candidate_missing",
            )
        abs_path = project_dir / rel
        if not abs_path.is_file():
            raise BoardI2IError(
                f"{beat_id} 候选文件不存在：{rel}",
                code="i2i_output_missing",
            )
        digest = _file_sha256(abs_path)
        decision_id = f"d-i2i-review-{beat_id}"
        decisions.append(
            {
                "decision_id": decision_id,
                "stage": "assets_gate",
                "category": "asset_decision",
                "subject": rel,
                "asset_path": rel,
                "asset_source": "generated",
                "asset_sha256": digest,
                "beat_ids": [beat_id],
                "options_considered": [
                    {
                        "option_id": "approved",
                        "label": "批准生成图",
                        "score": 1.0,
                        "reason": "用户在素材检查页通过该补图。",
                    }
                ],
                "selected": "approved",
                "reason": "用户批准该候选图。",
                "user_visible": True,
                "user_approved": True,
                "user_response_text": response,
                "decided_at": now,
            }
        )
        segment["assignment_status"] = STATUS_ASSIGNED
        segment["ref_image"] = rel
        segment["review_status"] = "approved"
        segment["decision_id"] = decision_id
        segment["output_path"] = rel
        approved.append(rel)
    if not approved:
        return {"action": "noop", "paths": []}
    log["decisions"] = decisions
    log["project_id"] = project_id
    _write_json(log_path, log)
    _write_json(art_dir / "video_plan.json", video_plan)
    return {"action": "approved", "paths": approved}


def i2i_ledger_row(
    *,
    beat_id: str,
    path: str,
    segment: dict[str, Any],
    user_class: str,
    file_name: str,
) -> dict[str, Any]:
    rel = path.replace("\\", "/")
    candidates = segment.get("candidate_paths") or [rel]
    if not isinstance(candidates, list) or not candidates:
        candidates = [rel]
    return {
        "path": rel,
        "file": file_name,
        "kind": "image",
        "beats": [beat_id],
        "user_class": user_class,
        "status": "confirmed",
        "origin": "i2i",
        "asset_source": "i2i",
        "gap_fill": "i2i",
        "selected": True,
        "provider": segment.get("provider"),
        "model": segment.get("model"),
        "review_status": "approved",
        "decision_id": segment.get("decision_id") or f"d-i2i-review-{beat_id}",
        "candidate_paths": [str(item) for item in candidates],
        "output_path": rel,
    }
