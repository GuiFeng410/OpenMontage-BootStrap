"""Delivery signoff requires a final video. Empty plan-only signoff is void."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.board_advance import final_video_ready
from lib.board_gap_plan import projects_root


class DeliverySignoffError(Exception):
    def __init__(self, message: str, *, code: str = "delivery_signoff") -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


def can_seal_minimal_plan_signoff(project_dir: Path) -> bool:
    """Always false: Plan/15 作废无成片即签收。"""
    return False


def seal_delivery_signoff_minimal(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Refuse to complete delivery without final.mp4."""
    root = projects_root(projects_dir)
    if not final_video_ready(project_id, projects_dir=root):
        raise DeliverySignoffError(
            "交付确认须先有成片。请留在本页等待制作，成片出现后再导出。",
            code="final_video_required",
        )
    raise DeliverySignoffError(
        "交付确认在有成片后于本页预览并导出，不再做无视频签收。",
        code="final_video_required",
    )
