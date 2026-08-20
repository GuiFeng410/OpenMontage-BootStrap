"""Project-scoped asset_manifest.json helpers for BootStrap medium/heavy paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import DoctorError
from openmontage.mcp.common.sandbox import project_dir, require_projects_root, resolve_under_projects

MANIFEST_REL = "artifacts/asset_manifest.json"


def empty_asset_manifest() -> dict[str, Any]:
    return {"version": "1.0", "assets": [], "total_cost_usd": 0.0}


def manifest_path(project_id: str) -> Path:
    require_projects_root()
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise DoctorError(f"Project not found: {project_id}", code="not_found")
    return pdir / MANIFEST_REL


def load_asset_manifest(project_id: str) -> dict[str, Any]:
    path = manifest_path(project_id)
    if not path.exists():
        return empty_asset_manifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise DoctorError(f"asset_manifest unreadable: {exc}", code="bad_request") from exc
    if not isinstance(data, dict):
        raise DoctorError("asset_manifest must be a JSON object", code="bad_request")
    data.setdefault("version", "1.0")
    assets = data.get("assets")
    if not isinstance(assets, list):
        data["assets"] = []
    data.setdefault("total_cost_usd", 0.0)
    return data


def save_asset_manifest(project_id: str, manifest: dict[str, Any]) -> Path:
    path = manifest_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep schema-friendly shape
    out = {
        "version": "1.0",
        "assets": list(manifest.get("assets") or []),
        "total_cost_usd": float(manifest.get("total_cost_usd") or 0.0),
    }
    if isinstance(manifest.get("metadata"), dict):
        out["metadata"] = manifest["metadata"]
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def path_relative_to_project(project_id: str, absolute_or_rel: str) -> str:
    """Store paths relative to project dir when possible (schema preference)."""
    pdir = project_dir(project_id).resolve()
    resolved = resolve_under_projects(absolute_or_rel).resolve()
    try:
        return resolved.relative_to(pdir).as_posix()
    except ValueError:
        return resolved.as_posix()


def build_stock_asset_entry(
    *,
    project_id: str,
    asset_id: str,
    media_kind: str,
    absolute_path: str,
    source: str,
    tool_name: str,
    scene_id: str,
    query: str = "",
    license_text: str = "",
    original_url: str = "",
    cost_usd: float = 0.0,
) -> dict[str, Any]:
    kind = (media_kind or "").strip().lower()
    if kind not in {"image", "video"}:
        raise DoctorError("media_kind must be image or video for stock assets", code="bad_request")
    aid = (asset_id or "").strip()
    if not aid:
        raise DoctorError("asset_id is required", code="bad_request")
    sid = (scene_id or "").strip() or "scene_01"
    entry: dict[str, Any] = {
        "id": aid,
        "type": kind,
        "path": path_relative_to_project(project_id, absolute_path),
        "source_tool": tool_name,
        "scene_id": sid,
        "subtype": "stock",
        "provider": source,
        "cost_usd": float(cost_usd),
        "generation_summary": f"stock download via {source}/{kind}",
    }
    if query:
        entry["prompt"] = query
    if license_text:
        entry["license"] = license_text
    if original_url:
        entry["original_url"] = original_url
    return entry


def upsert_asset_entry(project_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace asset by id; returns updated manifest + path."""
    if not isinstance(entry, dict) or not entry.get("id"):
        raise DoctorError("entry must be an object with id", code="bad_request")
    for required in ("type", "path", "source_tool", "scene_id"):
        if required not in entry:
            raise DoctorError(f"asset entry missing {required!r}", code="bad_request")
    manifest = load_asset_manifest(project_id)
    assets = [a for a in manifest["assets"] if not (isinstance(a, dict) and a.get("id") == entry["id"])]
    assets.append(entry)
    manifest["assets"] = assets
    total = 0.0
    for a in assets:
        if isinstance(a, dict) and isinstance(a.get("cost_usd"), (int, float)):
            total += float(a["cost_usd"])
    manifest["total_cost_usd"] = total
    path = save_asset_manifest(project_id, manifest)
    return {
        "project_id": project_id,
        "asset_manifest_path": str(path),
        "entry": entry,
        "asset_count": len(assets),
        "asset_manifest": manifest,
    }
