"""FastMCP exposure regressions for the edit-intent Agent loop."""

from __future__ import annotations

import asyncio

import pytest

import lib.edit_apply as edit_apply
import lib.edit_intents as edit_intents
from openmontage.mcp.bootstrap import server as server_mod
from openmontage.mcp.bootstrap import tools as tools_mod
from openmontage.mcp.bootstrap.server import mcp
from openmontage.mcp.common.errors import DoctorError


@pytest.mark.parametrize(
    "tool_name",
    ("produce_list_intents", "produce_apply_intent"),
)
def test_fastmcp_exposes_edit_intent_tools(tool_name: str) -> None:
    tool_names = {tool.name for tool in asyncio.run(mcp.list_tools())}

    assert tool_name in tool_names


def test_apply_intent_drift_uses_failure_envelope(monkeypatch) -> None:
    monkeypatch.setattr(
        tools_mod,
        "produce_apply_intent",
        lambda _project_id, _intent_id: {
            "applied": False,
            "reason": "drift",
            "friendly_zh": "你标记的是旧版本。",
        },
    )

    result = server_mod.produce_apply_intent("demo-pro", "intent-old")

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == {
        "code": "intent_drift",
        "message": "你标记的是旧版本。",
    }


def test_apply_intent_invalid_project_maps_to_safe_error(
    monkeypatch, tmp_path
) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(edit_apply, "PROJECTS_DIR", root)
    monkeypatch.setattr(edit_intents, "PROJECTS_DIR", root)

    with pytest.raises(DoctorError) as caught:
        tools_mod.produce_apply_intent("missing-project", "intent-1")

    assert caught.value.code == "unknown_project"
    assert caught.value.message == "unknown project"

    envelope = server_mod.produce_apply_intent(
        "missing-project",
        "intent-1",
    )
    assert envelope["ok"] is False
    assert envelope["error"] == {
        "code": "unknown_project",
        "message": "unknown project",
    }


def test_apply_intent_validation_error_uses_safe_failure_envelope(
    monkeypatch,
) -> None:
    def reject(_project_id, _intent_id):
        raise edit_intents.IntentError("sensitive validation detail")

    monkeypatch.setattr(edit_apply, "apply_intent", reject)

    result = server_mod.produce_apply_intent("demo-pro", "intent-bad")

    assert result["ok"] is False
    assert result["error"] == {
        "code": "intent_error",
        "message": "edit intent could not be applied",
    }
    assert "sensitive" not in result["error"]["message"]


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            "missing_source_render",
            "intent migration required: missing canonical source_render",
        ),
        (
            "intent_transaction_failed",
            "edit intent transaction failed; changes rolled back",
        ),
    ],
)
def test_apply_intent_coded_failures_preserve_failure_envelope(
    monkeypatch,
    code,
    message,
) -> None:
    error = edit_intents.IntentError(message)
    error.code = code

    def reject(_project_id, _intent_id):
        raise error

    monkeypatch.setattr(edit_apply, "apply_intent", reject)

    result = server_mod.produce_apply_intent("demo-pro", "intent-old")

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == {"code": code, "message": message}
