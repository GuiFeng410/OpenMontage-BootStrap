"""providers-stock — free stock search/download with confirm on download (Stock-最小)."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.common.registry import get_tool, tool_result_to_dict
from openmontage.mcp.common.sandbox import require_projects_root, resolve_under_projects

# source + media_kind → BaseTool name (download path)
STOCK_TOOLS: dict[tuple[str, str], str] = {
    ("pexels", "image"): "pexels_image",
    ("pexels", "video"): "pexels_video",
    ("pixabay", "image"): "pixabay_image",
    ("pixabay", "video"): "pixabay_video",
}

ENV_HINTS: dict[str, list[str]] = {
    "pexels": ["PEXELS_API_KEY"],
    "pixabay": ["PIXABAY_API_KEY"],
}

SOURCES = ("pexels", "pixabay")
MEDIA_KINDS = ("image", "video")


def _allowed_sources() -> set[str] | None:
    raw = os.environ.get("OPENMONTAGE_ALLOWED_STOCK_SOURCES", "").strip()
    if not raw:
        # Fall back to shared allow-list if set
        raw = os.environ.get("OPENMONTAGE_ALLOWED_PROVIDERS", "").strip()
    if not raw:
        return None
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _parse_extras(extras_json: str) -> dict[str, Any]:
    if not extras_json or not extras_json.strip():
        return {}
    try:
        data = json.loads(extras_json)
    except json.JSONDecodeError as exc:
        raise DoctorError(f"extras_json invalid: {exc}", code="bad_request") from exc
    if not isinstance(data, dict):
        raise DoctorError("extras_json must be a JSON object", code="bad_request")
    return data


def _sandbox_output(path: str | None, default_rel: str) -> str:
    if not path:
        path = default_rel
    resolved = resolve_under_projects(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def _resolve_stock(source: str, media_kind: str) -> tuple[str, str, str]:
    src = (source or "").strip().lower()
    kind = (media_kind or "").strip().lower()
    if src not in SOURCES:
        raise DoctorError(
            f"Unknown stock source {source!r}. Allowed: {list(SOURCES)}",
            code="bad_request",
        )
    if kind not in MEDIA_KINDS:
        raise DoctorError(
            f"media_kind must be one of {list(MEDIA_KINDS)}",
            code="bad_request",
        )
    allowed = _allowed_sources()
    if allowed is not None and src not in allowed:
        raise ConfigError(
            f"Stock source {src!r} not in OPENMONTAGE_ALLOWED_STOCK_SOURCES/"
            f"OPENMONTAGE_ALLOWED_PROVIDERS={sorted(allowed)}"
        )
    tool_name = STOCK_TOOLS[(src, kind)]
    return src, kind, tool_name


def _require_key(source: str) -> str:
    for env_name in ENV_HINTS[source]:
        val = os.environ.get(env_name, "").strip()
        if val:
            return val
    raise ConfigError(
        f"{source} API key missing. Set one of {ENV_HINTS[source]}. "
        "Free keys: https://www.pexels.com/api/ or https://pixabay.com/api/docs/"
    )


def list_stock_sources() -> dict[str, Any]:
    allowed = _allowed_sources()
    rows = []
    for source in SOURCES:
        if allowed is not None and source not in allowed:
            continue
        env_names = ENV_HINTS[source]
        key_present = any(os.environ.get(e) for e in env_names)
        for kind in MEDIA_KINDS:
            tool_name = STOCK_TOOLS[(source, kind)]
            try:
                tool = get_tool(tool_name)
                info = tool.get_info()
                status = info.get("status")
            except Exception:  # noqa: BLE001
                status = "missing"
                info = {}
            rows.append(
                {
                    "source": source,
                    "media_kind": kind,
                    "tool_name": tool_name,
                    "status": status,
                    "available": status == "available",
                    "key_configured": key_present,
                    "env_vars": env_names,
                    "estimated_cost_usd": 0.0,
                    "best_for": info.get("best_for"),
                }
            )
    return {
        "sources": rows,
        "projects_dir": str(require_projects_root()) if os.environ.get("OPENMONTAGE_PROJECTS_DIR") else None,
        "allowed_sources": sorted(allowed) if allowed else None,
        "note": (
            "Free stock only (Pexels/Pixabay). "
            "Protocol: list → stock_search → stock_download(confirm=true). "
            "Not registered by default at BootStrap install — optional add-on."
        ),
    }


def _search_pexels_image(api_key: str, query: str, extras: dict[str, Any]) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "query": query,
        "per_page": int(extras.get("per_page", 5)),
        "page": int(extras.get("page", 1)),
    }
    for key in ("orientation", "size", "color"):
        if extras.get(key):
            params[key] = extras[key]
    r = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": api_key},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    out = []
    for i, photo in enumerate(data.get("photos", [])):
        out.append(
            {
                "index": i,
                "id": photo.get("id"),
                "preview_url": (photo.get("src") or {}).get("medium"),
                "width": photo.get("width"),
                "height": photo.get("height"),
                "photographer": photo.get("photographer"),
                "alt": photo.get("alt"),
                "page_url": photo.get("url"),
                "license": "Pexels License (free, no attribution required)",
            }
        )
    return out


def _search_pexels_video(api_key: str, query: str, extras: dict[str, Any]) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "query": query,
        "per_page": int(extras.get("per_page", 5)),
        "page": int(extras.get("page", 1)),
    }
    for key in ("orientation", "size"):
        if extras.get(key):
            params[key] = extras[key]
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": api_key},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    videos = data.get("videos", [])
    min_dur = extras.get("min_duration")
    max_dur = extras.get("max_duration")
    if min_dur or max_dur:
        filtered = []
        for v in videos:
            dur = v.get("duration", 0)
            if min_dur and dur < min_dur:
                continue
            if max_dur and dur > max_dur:
                continue
            filtered.append(v)
        videos = filtered
    out = []
    for i, video in enumerate(videos):
        out.append(
            {
                "index": i,
                "id": video.get("id"),
                "duration_seconds": video.get("duration"),
                "width": video.get("width"),
                "height": video.get("height"),
                "user": (video.get("user") or {}).get("name"),
                "preview_url": video.get("image"),
                "page_url": video.get("url"),
                "license": "Pexels License (free, no attribution required)",
            }
        )
    return out


def _search_pixabay_image(api_key: str, query: str, extras: dict[str, Any]) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "key": api_key,
        "q": query,
        "per_page": max(3, min(int(extras.get("per_page", 5)), 200)),
        "page": int(extras.get("page", 1)),
        "safesearch": str(extras.get("safesearch", True)).lower(),
    }
    for key in ("image_type", "orientation", "category", "colors"):
        val = extras.get(key)
        if val and val != "all":
            params[key] = val
    if extras.get("editors_choice"):
        params["editors_choice"] = "true"
    r = requests.get("https://pixabay.com/api/", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    out = []
    for i, hit in enumerate(data.get("hits", [])):
        out.append(
            {
                "index": i,
                "id": hit.get("id"),
                "preview_url": hit.get("previewURL") or hit.get("webformatURL"),
                "width": hit.get("imageWidth"),
                "height": hit.get("imageHeight"),
                "user": hit.get("user"),
                "tags": hit.get("tags"),
                "page_url": hit.get("pageURL"),
                "license": "Pixabay Content License (free, no attribution required)",
            }
        )
    return out


def _search_pixabay_video(api_key: str, query: str, extras: dict[str, Any]) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "key": api_key,
        "q": query,
        "per_page": max(3, min(int(extras.get("per_page", 5)), 200)),
        "page": int(extras.get("page", 1)),
        "safesearch": str(extras.get("safesearch", True)).lower(),
    }
    if extras.get("video_type") and extras["video_type"] != "all":
        params["video_type"] = extras["video_type"]
    if extras.get("category"):
        params["category"] = extras["category"]
    if extras.get("editors_choice"):
        params["editors_choice"] = "true"
    r = requests.get("https://pixabay.com/api/videos/", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    hits = data.get("hits", [])
    min_dur = extras.get("min_duration")
    max_dur = extras.get("max_duration")
    if min_dur or max_dur:
        filtered = []
        for h in hits:
            dur = h.get("duration", 0)
            if min_dur and dur < min_dur:
                continue
            if max_dur and dur > max_dur:
                continue
            filtered.append(h)
        hits = filtered
    out = []
    for i, hit in enumerate(hits):
        out.append(
            {
                "index": i,
                "id": hit.get("id"),
                "duration_seconds": hit.get("duration"),
                "user": hit.get("user"),
                "tags": hit.get("tags"),
                "page_url": hit.get("pageURL"),
                "preview_url": (hit.get("videos") or {}).get("tiny", {}).get("url"),
                "license": "Pixabay Content License (free, no attribution required)",
            }
        )
    return out


def stock_search(
    source: str,
    media_kind: str,
    query: str,
    extras_json: str = "{}",
) -> dict[str, Any]:
    if not query.strip():
        raise DoctorError("query is required", code="bad_request")
    src, kind, tool_name = _resolve_stock(source, media_kind)
    api_key = _require_key(src)
    extras = _parse_extras(extras_json)
    try:
        if src == "pexels" and kind == "image":
            candidates = _search_pexels_image(api_key, query, extras)
        elif src == "pexels" and kind == "video":
            candidates = _search_pexels_video(api_key, query, extras)
        elif src == "pixabay" and kind == "image":
            candidates = _search_pixabay_image(api_key, query, extras)
        else:
            candidates = _search_pixabay_video(api_key, query, extras)
    except requests.HTTPError as exc:
        raise DoctorError(f"{src} search HTTP error: {exc}", code="provider_failed") from exc
    except requests.RequestException as exc:
        raise DoctorError(f"{src} search failed: {exc}", code="provider_failed") from exc

    return {
        "source": src,
        "media_kind": kind,
        "tool_name": tool_name,
        "query": query,
        "estimated_cost_usd": 0.0,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "next_step": (
            "Present candidates to the user. After they approve, call stock_download "
            "with the same source/media_kind/query and confirm=true "
            "(download uses first search hit via BaseTool; refine query if needed)."
            if candidates
            else "No candidates; refine query or try the other source."
        ),
        "note": "Search does not write files. Download requires confirm=true.",
    }


def stock_download(
    source: str,
    media_kind: str,
    query: str,
    output_path: str = "",
    extras_json: str = "{}",
    confirm: bool = False,
    project_id: str = "",
    scene_id: str = "",
    asset_id: str = "",
) -> dict[str, Any]:
    require_projects_root()
    if not confirm:
        raise ConfigError(
            "stock_download requires confirm=true after the user approved stock_search results."
        )
    if not query.strip():
        raise DoctorError("query is required", code="bad_request")
    src, kind, tool_name = _resolve_stock(source, media_kind)
    _require_key(src)
    extras = _parse_extras(extras_json)
    pid = (project_id or "").strip()
    if pid:
        # Prefer project-scoped stock paths for medium produce
        default = (
            f"{pid}/assets/stock/{src}_{kind}.jpg"
            if kind == "image"
            else f"{pid}/assets/stock/{src}_{kind}.mp4"
        )
    else:
        default = (
            f"assets/stock/{src}_{kind}.jpg" if kind == "image" else f"assets/stock/{src}_{kind}.mp4"
        )
    out = _sandbox_output(output_path or default, default)
    tool = get_tool(tool_name)
    inputs = {"query": query, "output_path": out, **extras}
    # Pixabay requires per_page >= 3
    if src == "pixabay" and "per_page" not in inputs:
        inputs["per_page"] = 5
    result = tool.execute(inputs)
    payload = tool_result_to_dict(result)
    if not payload.get("success"):
        raise DoctorError(
            f"{tool_name} download failed: {payload.get('error')}. "
            "No silent source fallback.",
            code="provider_failed",
        )
    payload["source"] = src
    payload["media_kind"] = kind
    payload["tool_name"] = tool_name
    payload["output_path"] = out
    payload["estimated_cost_usd"] = 0.0
    payload["cost_usd"] = 0.0

    if pid:
        from openmontage.mcp.common.asset_manifest import build_stock_asset_entry, upsert_asset_entry

        aid = (asset_id or "").strip() or f"stock_{src}_{kind}_{len(query)}"
        # Keep asset_id filesystem-safe-ish
        aid = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in aid)[:64]
        entry = build_stock_asset_entry(
            project_id=pid,
            asset_id=aid,
            media_kind=kind,
            absolute_path=out,
            source=src,
            tool_name=tool_name,
            scene_id=(scene_id or "").strip() or "scene_01",
            query=query,
            license_text=str(payload.get("license") or ""),
            original_url=str(payload.get("url") or payload.get("page_url") or ""),
            cost_usd=0.0,
        )
        registered = upsert_asset_entry(pid, entry)
        payload["project_id"] = pid
        payload["asset_id"] = aid
        payload["scene_id"] = entry["scene_id"]
        payload["manifest_entry"] = entry
        payload["asset_manifest_path"] = registered["asset_manifest_path"]
        payload["asset_count"] = registered["asset_count"]
        payload["next_step"] = (
            "Pass asset_manifest from produce_read_asset_manifest(project_id) "
            "into produce_compose_preflight / produce_compose_start."
        )
    return payload
