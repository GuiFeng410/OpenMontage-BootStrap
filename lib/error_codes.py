"""Canonical error-code strings used by MCP envelopes and related facades.

Values are existing public codes. Do not invent new external codes here.
Produce/board raise-site codes stay at those call sites this round.
"""

from __future__ import annotations

from typing import Any

# --- MCP class defaults ---
DOCTOR_ERROR = "doctor_error"
SANDBOX_VIOLATION = "sandbox_violation"
CONFIG_ERROR = "config_error"

# --- Shared MCP / facade codes ---
BAD_REQUEST = "bad_request"
NOT_FOUND = "not_found"
CONFLICT = "conflict"
UNKNOWN_PROJECT = "unknown_project"
RUNNER_BUSY = "runner_busy"

# --- Install / clone ---
UNSAFE_OVERWRITE = "unsafe_overwrite"
CLONE_FAILED = "clone_failed"
MISSING_REQUIREMENTS = "missing_requirements"
VENV_FAILED = "venv_failed"
PIP_FAILED = "pip_failed"
MISSING_REMOTION = "missing_remotion"
NPM_MISSING = "npm_missing"
NPM_FAILED = "npm_failed"

# --- Produce / doctor ---
INVALID_PROJECT_EVIDENCE = "invalid_project_evidence"
APPROVAL_BUNDLE_FAILED = "approval_bundle_failed"
INTENT_ERROR = "intent_error"
USER_CONFIRMATION_REQUIRED = "user_confirmation_required"
PROVIDER_ERROR = "provider_error"
PROVIDER_FAILED = "provider_failed"
MIX_FAILED = "mix_failed"
PROJECT_ID_EXHAUSTED = "project_id_exhausted"
INVALID_PROJECT = "invalid_project"
PIPELINE_MISMATCH = "pipeline_mismatch"
PROBE_FAILED = "probe_failed"
SYNTH_FAILED = "synth_failed"
MISSING_DEP = "missing_dep"
BAD_CONFIG = "bad_config"
BAD_STATE = "bad_state"

# --- Approval bundle / project export (existing .code values) ---
INTENT_NOT_FOUND = "intent_not_found"
INTENT_INVALID = "intent_invalid"
INTENT_REVISION_DRIFT = "intent_revision_drift"
INTENT_TYPE_MISMATCH = "intent_type_mismatch"
MISSING_PROJECT_EVIDENCE = "missing_project_evidence"
INTENT_STATUS_INVALID = "intent_status_invalid"
CONFIRMATION_REQUIRED = "confirmation_required"
INTENT_PLAN_REQUIRED = "intent_plan_required"
INVALID_PROJECT_MARKER = "invalid_project_marker"
EXPORT_INTENT_REQUIRED = "export_intent_required"

# --- Edit-intent MCP mapping (not merged with interaction IntentError) ---
MISSING_SOURCE_RENDER = "missing_source_render"
INTENT_TRANSACTION_FAILED = "intent_transaction_failed"
INTENT_TRANSACTION_RECOVERY_REQUIRED = "intent_transaction_recovery_required"


def to_doctor_error(
    exc: BaseException,
    *,
    fallback_message: str | None = None,
    fallback_code: str | None = None,
) -> Any:
    """Map a domain exception to DoctorError without changing known messages/codes."""
    from lib.approval_bundle import ApprovalBundleError
    from lib.interaction_intents import UnknownProjectError
    from lib.project_export import ProjectExportError
    from openmontage.mcp.common.errors import DoctorError

    if isinstance(exc, DoctorError):
        return exc
    if isinstance(exc, UnknownProjectError):
        return DoctorError("unknown project", code=UNKNOWN_PROJECT)
    if isinstance(exc, (ApprovalBundleError, ProjectExportError)):
        return DoctorError(exc.safe_message, code=exc.code)
    message = fallback_message or str(exc) or "internal error"
    code = fallback_code or DOCTOR_ERROR
    return DoctorError(message, code=code)


def to_http_detail(exc: BaseException) -> str:
    """Plain-string HTTP detail. Server is not switched this round."""
    return str(exc)
