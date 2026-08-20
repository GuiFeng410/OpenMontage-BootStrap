"""Copy final.mp4 to exports/ and mark the project completed."""

from __future__ import annotations

from typing import Any


def export_project(
    project_id: str,
    *,
    intent_id: str = "",
    confirm_phrase: str = "",
) -> dict[str, Any]:
    """Delegate to the existing export copy + completed marker write."""
    from lib.project_export import apply_project_export

    return apply_project_export(
        project_id,
        intent_id=intent_id,
        confirm_phrase=confirm_phrase,
    )
