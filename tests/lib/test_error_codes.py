"""Canonical error-code catalog and MCP mapping helper."""

from __future__ import annotations

from lib.approval_bundle import ApprovalBundleError
from lib.error_codes import (
    APPROVAL_BUNDLE_FAILED,
    CONFIG_ERROR,
    DOCTOR_ERROR,
    SANDBOX_VIOLATION,
    UNKNOWN_PROJECT,
    to_doctor_error,
    to_http_detail,
)
from lib.interaction_intents import IntentError as InteractionIntentError
from lib.interaction_intents import UnknownProjectError
from lib.project_export import ProjectExportError
from openmontage.mcp.common.errors import ConfigError, DoctorError, SandboxError


def test_mcp_error_classes_use_catalog_codes() -> None:
    assert SandboxError("x").code == SANDBOX_VIOLATION
    assert ConfigError("x").code == CONFIG_ERROR
    assert DoctorError("x").code == DOCTOR_ERROR


def test_to_doctor_error_unknown_project() -> None:
    src = UnknownProjectError("missing marker")
    mapped = to_doctor_error(src)
    assert isinstance(mapped, DoctorError)
    assert mapped.code == UNKNOWN_PROJECT
    assert mapped.message == "unknown project"


def test_to_doctor_error_preserves_approval_and_export() -> None:
    approval = ApprovalBundleError(
        "internal",
        code="intent_not_found",
        safe_message="未找到指定的面板选择",
    )
    export = ProjectExportError(
        "internal",
        code="export_intent_required",
        safe_message="需要结束导出确认",
    )
    mapped_a = to_doctor_error(approval)
    mapped_e = to_doctor_error(export)
    assert mapped_a.code == "intent_not_found"
    assert mapped_a.message == "未找到指定的面板选择"
    assert mapped_e.code == "export_intent_required"
    assert mapped_e.message == "需要结束导出确认"


def test_to_doctor_error_passthrough_and_fallback() -> None:
    original = DoctorError("keep me", code="bad_request")
    assert to_doctor_error(original) is original
    mapped = to_doctor_error(
        RuntimeError("boom"),
        fallback_message="approval bundle operation failed; intent changes were rolled back",
        fallback_code=APPROVAL_BUNDLE_FAILED,
    )
    assert mapped.message == (
        "approval bundle operation failed; intent changes were rolled back"
    )
    assert mapped.code == APPROVAL_BUNDLE_FAILED


def test_to_http_detail_is_plain_string() -> None:
    detail = to_http_detail(RuntimeError("confirm required"))
    assert detail == "confirm required"
    assert isinstance(detail, str)


def test_dual_intent_error_types_remain_separate() -> None:
    from lib.edit_intents import IntentError as EditIntentError

    assert InteractionIntentError is not EditIntentError
    assert not issubclass(EditIntentError, InteractionIntentError)
    assert not issubclass(InteractionIntentError, EditIntentError)
