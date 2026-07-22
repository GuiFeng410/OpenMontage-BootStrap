"""ImageSelector Agnes auto-prefer routing coverage."""

from __future__ import annotations

from typing import Any

import pytest

from tools.base_tool import ToolStatus
from tools.graphics.image_selector import ImageSelector


class _StubTool:
    capability = "image_generation"

    def __init__(
        self,
        name: str,
        provider: str,
        *,
        status: ToolStatus = ToolStatus.AVAILABLE,
    ) -> None:
        self.name = name
        self.provider = provider
        self.quality_score: float | None = None
        self.best_for = [name]
        self.supports = {"text_to_image": True}
        self.input_schema = {"properties": {"prompt": {}}}
        self._status = status

    def get_status(self) -> ToolStatus:
        return self._status

    def is_operation_available(self, operation: str) -> bool:
        return True

    def get_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "agent_skills": [],
            "best_for": self.best_for,
            "supports": self.supports,
            "quality_score": self.quality_score,
        }


class _ScoreStub:
    def __init__(self, tool_name: str, provider: str, weighted: float) -> None:
        self.tool_name = tool_name
        self.provider = provider
        self.weighted_score = weighted

    def explain(self) -> str:
        return f"{self.tool_name}"

    def to_dict(self) -> dict[str, Any]:
        return {"tool_name": self.tool_name, "provider": self.provider}


@pytest.fixture()
def rankings(monkeypatch):
    table: list[_ScoreStub] = []

    def fake_rank(candidates, task_context):  # noqa: ANN001
        return list(table)

    monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)
    return table


def test_image_auto_prefers_agnes_when_key_present(rankings, monkeypatch):
    monkeypatch.setenv("AGNES_API_KEY", "test-agnes-key")
    agnes = _StubTool("agnes_image", "agnes")
    flux = _StubTool("flux_image", "flux")
    rankings.extend([
        _ScoreStub("flux_image", "flux", 0.95),
        _ScoreStub("agnes_image", "agnes", 0.80),
    ])

    tool, _ = ImageSelector()._select_best_tool(
        {"preferred_provider": "auto"}, [agnes, flux], {}
    )
    assert tool is not None
    assert tool.name == "agnes_image"


def test_image_explicit_preferred_overrides_agnes(rankings, monkeypatch):
    monkeypatch.setenv("AGNES_API_KEY", "test-agnes-key")
    agnes = _StubTool("agnes_image", "agnes")
    flux = _StubTool("flux_image", "flux")
    rankings.extend([
        _ScoreStub("agnes_image", "agnes", 0.95),
        _ScoreStub("flux_image", "flux", 0.90),
    ])

    tool, _ = ImageSelector()._select_best_tool(
        {"preferred_provider": "flux"}, [agnes, flux], {}
    )
    assert tool.name == "flux_image"
