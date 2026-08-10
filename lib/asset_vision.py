"""Merge OpenAI-compatible vision results into commercial asset_precheck.

P1 gate: vision assists suggested_class; user confirmation still required.
No Key → degrade to filename heuristics (caller should skip this module).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from lib.asset_precheck import scan_user_images
from tools.analysis.openai_compat_vision import OpenAICompatVision, resolve_vision_env

_VALID_CLASSES = {
    "product_hero",
    "product_detail",
    "product_angle",
    "on_body",
    "packaging",
    "lifestyle",
    "background",
    "in_use",
}


def _normalize_class(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in _VALID_CLASSES:
        return raw
    if raw in {"unknown", "unclassified", ""}:
        return ""
    return ""


def merge_vision_into_precheck(
    precheck: dict[str, Any],
    vision_images: list[dict[str, Any]],
    *,
    model: str = "",
) -> dict[str, Any]:
    """Attach vision fields; prefer vision class when filename hint is empty."""
    by_file: dict[str, dict[str, Any]] = {}
    for row in vision_images:
        if not isinstance(row, dict):
            continue
        key = str(row.get("file") or "").strip()
        if key:
            by_file[key] = row
            by_file[Path(key).name] = row

    entries_out: list[dict[str, Any]] = []
    for entry in precheck.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        row = dict(entry)
        hit = by_file.get(str(row.get("file") or "")) or by_file.get(str(row.get("path") or ""))
        if hit:
            v_class = _normalize_class(hit.get("suggested_class"))
            row["filename_suggested_class"] = row.get("suggested_class") or ""
            row["vision_description_zh"] = str(hit.get("description_zh") or "")
            row["vision_usable_for_zh"] = str(hit.get("usable_for_zh") or "")
            row["vision_confidence"] = hit.get("confidence")
            row["vision_risks_zh"] = list(hit.get("risks_zh") or [])
            row["vision_suggested_class"] = v_class
            row["vision_model"] = model
            if v_class and not row.get("suggested_class"):
                row["suggested_class"] = v_class
            elif v_class and row.get("suggested_class") != v_class:
                # Keep filename hint; surface vision as alternate for user card.
                row["vision_alt_class"] = v_class
        entries_out.append(row)

    counts = Counter(e.get("suggested_class") or "unclassified" for e in entries_out)
    summary = dict(precheck.get("summary") or {})
    summary["counts_by_suggested_class"] = dict(counts)
    summary["vision_enriched"] = bool(vision_images)
    summary["vision_model"] = model
    has_unclassified = any(not e.get("suggested_class") for e in entries_out)
    summary["needs_user_attention"] = bool(
        not entries_out
        or has_unclassified
        or summary.get("low_resolution_count")
        or summary.get("duplicate_group_count")
    )
    return {
        **precheck,
        "entries": entries_out,
        "summary": summary,
    }


def describe_project_user_images(
    project_dir: str | Path,
    *,
    files: list[str] | None = None,
    prompt: str = "",
    model: str = "",
) -> dict[str, Any]:
    """Scan + optional vision. Never writes artifacts. Empty Key → degrade."""
    project_path = Path(project_dir).resolve()
    precheck = scan_user_images(project_path)
    cfg = resolve_vision_env()
    base: dict[str, Any] = {
        "version": "1.0",
        "vision_available": cfg["available"],
        "vision_degraded": not cfg["available"],
        "key_source": cfg.get("key_source") or "",
        "base_url": cfg["base_url"],
        "model": model or cfg["model"],
        "precheck": precheck,
        "vision": None,
        "message_zh": "",
    }
    if not cfg["available"]:
        base["message_zh"] = (
            "未配置 VISION_API_KEY / DASHSCOPE_API_KEY：已降级为文件名启发式，"
            "仍须用户确认分类后写入 asset_ledger。"
        )
        return base

    entries = precheck.get("entries") or []
    if files:
        wanted = {Path(f).name for f in files}
        entries = [e for e in entries if e.get("file") in wanted or Path(str(e.get("path") or "")).name in wanted]
    if not entries:
        base["message_zh"] = "没有可识图的本地素材（assets/images/ 为空或过滤后为空）。"
        return base

    paths = [str(project_path / e["path"]) for e in entries if e.get("path")]
    tool = OpenAICompatVision()
    result = tool.execute(
        {
            "image_paths": paths,
            **({"model": model} if model else {}),
            **({"prompt": prompt} if prompt else {}),
        }
    )
    if not result.success:
        base["vision_degraded"] = True
        base["message_zh"] = f"识图调用失败，已保留文件名启发式：{result.error}"
        base["error"] = result.error
        return base

    data = result.data if isinstance(result.data, dict) else {}
    images = list(data.get("images") or [])
    merged = merge_vision_into_precheck(precheck, images, model=result.model or base["model"])
    base["precheck"] = merged
    base["vision"] = {
        "model": result.model or base["model"],
        "duration_seconds": result.duration_seconds,
        "images": images,
    }
    base["message_zh"] = (
        f"已用 {result.model or base['model']} 识图辅助分类；"
        "suggested_class 仍须用户确认后才能写入 asset_ledger。"
    )
    return base
