"""Human review state machine for ecommerce image/video candidates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_STATUSES = frozenset({"pending", "rejected", "approved", "satisfied"})
APPROVED_STATUSES = frozenset({"approved", "satisfied"})


def _data(product_manifest: Any) -> dict[str, Any]:
    if hasattr(product_manifest, "data"):
        value = getattr(product_manifest, "data")
    else:
        value = product_manifest
    if not isinstance(value, dict):
        raise TypeError("product_manifest must be ProductManifest or dict")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_pending_candidates(product_manifest: Any) -> list[dict[str, Any]]:
    """Return pending I2I and I2V entries without promoting them."""
    data = _data(product_manifest)
    pending: list[dict[str, Any]] = []
    for kind in ("i2i_candidates", "i2v_candidates"):
        entries = data.get(kind) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("status") == "pending":
                item = dict(entry)
                item["candidate_type"] = kind
                pending.append(item)
    return pending


def review_candidate(
    candidate_path: str | Path,
    reference_images: list[str] | None,
    reviewer_decision: str,
    *,
    product_manifest: Any | None = None,
    scene_id: str | None = None,
    notes: str = "",
    reviewer: str = "human",
) -> dict[str, Any]:
    """Record a three-level human decision and optionally update a manifest.

    ``rejected`` candidates remain in the manifest as audit history. They are
    never removed or silently promoted to an approved asset.
    """
    decision = str(reviewer_decision).strip().lower()
    if decision not in REVIEW_STATUSES - {"pending"}:
        raise ValueError("reviewer_decision must be rejected, approved, or satisfied")
    candidate = str(candidate_path)
    record: dict[str, Any] = {
        "candidate": candidate,
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": _now(),
        "reference_images": list(reference_images or []),
    }
    if scene_id:
        record["scene_id"] = scene_id
    if notes:
        record["notes"] = notes

    if product_manifest is None:
        return record

    data = _data(product_manifest)
    target_kind = "i2v_candidates" if Path(candidate).suffix.lower() in {".mp4", ".mov", ".webm"} else "i2i_candidates"
    entries = data.setdefault(target_kind, [])
    if not isinstance(entries, list):
        raise ValueError(f"{target_kind} must be a list")
    target = next((item for item in entries if isinstance(item, dict) and item.get("path") == candidate), None)
    if target is None:
        target = {"path": candidate, "status": "pending"}
        if scene_id:
            target["scene_id"] = scene_id
        entries.append(target)
    target["status"] = decision
    target["reviewed_at"] = record["reviewed_at"]
    if notes:
        target["notes"] = notes
    data.setdefault("review_log", []).append({"action": "candidate_review", **record})
    return record


def apply_fallback(plan: dict[str, Any], product_manifest: Any) -> dict[str, Any]:
    """Return a plan with non-approved AI inserts switched to Remotion fallback."""
    data = _data(product_manifest)
    statuses_by_path = {
        str(item.get("path")): item.get("status")
        for kind in ("i2i_candidates", "i2v_candidates")
        for item in (data.get(kind) or [])
        if isinstance(item, dict) and item.get("path")
    }
    updated = deepcopy(plan)
    for beat in updated.get("beats") or updated.get("scenes") or []:
        source = str(beat.get("source") or beat.get("asset") or "")
        candidate = str(beat.get("i2v_candidate") or source)
        status = statuses_by_path.get(candidate)
        if status not in APPROVED_STATUSES:
            if beat.get("type") == "agnes_insert" or beat.get("operation") == "image_to_video":
                beat["type"] = "deterministic"
                beat["source"] = "Remotion deterministic static frame"
                beat["fallback_applied"] = True
                beat["review_status"] = status or "pending"
    return updated


__all__ = [
    "APPROVED_STATUSES",
    "REVIEW_STATUSES",
    "apply_fallback",
    "get_pending_candidates",
    "review_candidate",
]
