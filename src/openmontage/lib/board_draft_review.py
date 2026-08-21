"""Draft-review reject / suggestions helpers for commercial boards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.board_stage_artifacts import build_full_draft_pro
from lib.paths import PROJECTS_DIR
from lib.persistence.json_store import JsonStore


class DraftReviewError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "draft_review",
        safe_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = safe_message or message


def _projects_root(projects_dir: Path | None) -> Path:
    return Path(projects_dir) if projects_dir is not None else Path(PROJECTS_DIR)


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
    path.parent.mkdir(parents=True, exist_ok=True)
    JsonStore.write_atomic(path, data, replace_retries=3)


def draft_artifact_path(project_id: str, *, projects_dir: Path | None = None) -> Path:
    return _project_dir(project_id, projects_dir) / "artifacts" / "full_draft_pro.json"


def read_draft(project_id: str, *, projects_dir: Path | None = None) -> dict[str, Any]:
    return _read_json(draft_artifact_path(project_id, projects_dir=projects_dir))


def draft_is_rejected(project_id: str, *, projects_dir: Path | None = None) -> bool:
    draft = read_draft(project_id, projects_dir=projects_dir)
    return str(draft.get("status") or "").strip().lower() == "rejected"


def intent_note(intent: dict[str, Any]) -> str:
    payload = intent.get("payload") if isinstance(intent.get("payload"), dict) else {}
    return str(payload.get("note") or "").strip()


def suggestions_from_note(note: str) -> list[str]:
    """Heuristic suggestions from optional rejection note. Never empty."""
    text = str(note or "").strip()
    lower = text.lower()
    tips: list[str] = []
    if any(token in text for token in ("模糊", "不清晰", "糊", "清晰度")) or "blur" in lower:
        tips.append("建议逐段查看画质偏软的镜头，记下段号后再决定是否重做该段。")
    if any(token in text for token in ("节奏", "太快", "太慢", "拖沓", "时长")):
        tips.append("建议对照分段列表检查每段时长与旁白是否匹配，再决定是否重生成或剪辑。")
    if any(token in text for token in ("商品", "产品", "看不清", "主体")):
        tips.append("建议优先核对商品主体是否居中、是否被裁切，问题集中的段可单独重做。")
    if any(token in text for token in ("字幕", "文案", "旁白", "字")):
        tips.append("建议先通过画面初稿，字幕与旁白可在后续字幕配乐步骤再补。")
    if any(token in text for token in ("颜色", "色偏", "风格", "不一致")):
        tips.append("建议对比各段色调与风格是否统一；差异大的段可标进修改清单。")
    if text and not tips:
        tips.append(f"已记录你的意见：「{text[:80]}」。建议先按分段预览核对，再决定是否进入终稿合成。")
    if not tips:
        tips.append("未填写原因也可以。请用下方分段列表逐段预览，确认可接受后再点「按建议继续」。")
    tips.append("确认建议后点「按建议继续，进入终稿合成」才会往下走；不会自动换渠道或静默重烧。")
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for tip in tips:
        if tip in seen:
            continue
        seen.add(tip)
        out.append(tip)
    return out


def list_draft_segments(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> list[dict[str, Any]]:
    project = _project_dir(project_id, projects_dir)
    overview = _read_json(project / "artifacts" / "review_overview.json")
    rows = [row for row in (overview.get("overview") or []) if isinstance(row, dict)]
    segments: list[dict[str, Any]] = []
    for row in rows:
        beat = str(row.get("beat") or "").strip()
        rel = str(row.get("output_path") or "").strip().replace("\\", "/")
        if not beat or not rel:
            continue
        path = project / rel
        exists = path.is_file() and path.stat().st_size > 0
        segments.append(
            {
                "beat": beat,
                "path": rel if exists else None,
                "exists": exists,
                "status": str(row.get("status") or ""),
                "label_zh": f"第 {beat} 段",
            }
        )
    return segments


def apply_draft_reject(
    project_id: str,
    intent: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    draft = read_draft(project_id, projects_dir=projects_dir)
    path = str(draft.get("path") or "").strip()
    if not path:
        segments = list_draft_segments(project_id, projects_dir=projects_dir)
        for item in segments:
            if item.get("exists") and item.get("path"):
                path = str(item["path"])
                break
    if not path:
        raise DraftReviewError(
            "初稿视频缺失，无法记录拒绝。",
            code="draft_missing",
            safe_message="当前没有可评审的初稿视频，请留在本页等待分段齐套。",
        )
    note = intent_note(intent)
    suggestions = suggestions_from_note(note)
    modifications = list(suggestions)
    if note:
        modifications.insert(0, f"用户意见：{note}")
    updated = build_full_draft_pro(
        path,
        issue_segments=draft.get("issue_segments") or [],
        modification_list=modifications,
        status="rejected",
        approved=False,
        extra={
            "rejection_note": note,
            "suggestions_zh": suggestions,
            "user_response_text": note,
        },
    )
    _write_json(draft_artifact_path(project_id, projects_dir=projects_dir), updated)
    return updated


def apply_draft_approve(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    draft = read_draft(project_id, projects_dir=projects_dir)
    path = str(draft.get("path") or "").strip()
    if not path:
        raise DraftReviewError(
            "初稿视频缺失，无法通过。",
            code="draft_missing",
            safe_message="当前没有可评审的初稿视频，请留在本页等待分段齐套。",
        )
    updated = build_full_draft_pro(
        path,
        issue_segments=draft.get("issue_segments") or [],
        modification_list=draft.get("modification_list") or [],
        status="approved",
        approved=True,
        extra={
            key: draft[key]
            for key in ("rejection_note", "suggestions_zh", "user_response_text")
            if key in draft
        },
    )
    _write_json(draft_artifact_path(project_id, projects_dir=projects_dir), updated)
    return updated
