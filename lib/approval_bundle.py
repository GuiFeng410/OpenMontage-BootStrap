"""FastAPI-free planning and application of interaction approval bundles."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import lib.interaction_intents as intents
from lib.paths import PROJECTS_DIR

CONFIRM_PHRASE = "确认面板选择"
FAST_TRACK_SELECTED = "fast_track_v2"
FAST_TRACK_SUBJECT = "Commercial fast-track production"
REVOKE_METHOD = "聊天发送撤销快速模式"

_PLAN_SOURCE_TYPES = frozenset({"decision", "approval_bundle"})
_TIER_IDS = frozenset({"light", "medium", "heavy"})
_REVIEW_IDS = frozenset({"guided", "normal", "pro", "professional"})
_RUNTIME_IDS = frozenset({"remotion", "hyperframes"})
_LOCAL_VISUAL_SOURCES = frozenset({"", "template"})
_COMMERCIAL_AUTO_STAGES = [
    "brief_locked",
    "assets_gate",
    "sample_review",
    "segment_build",
    "draft_review",
    "final_compose",
    "delivery_signoff",
]
_DEFAULT_PAUSE_CONDITIONS = [
    "generated_image_review",
    "budget_exceeded",
    "unit_price_exceeded",
    "provider_changed",
    "model_changed",
    "runtime_changed",
]


class ApprovalBundleError(intents.IntentError):
    """Safe, coded failure for facade MCP error envelopes."""

    def __init__(self, message: str, *, code: str, safe_message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = safe_message


def _intent_path(project_id: str, intent_id: str) -> Path:
    project = intents._project_dir(project_id)
    return intents._intent_path(project, intent_id)


def _load(project_id: str, intent_id: str) -> tuple[Path, dict[str, Any]]:
    path = _intent_path(project_id, intent_id)
    if not path.is_file():
        raise ApprovalBundleError(
            f"intent not found: {intent_id}",
            code="intent_not_found",
            safe_message="未找到指定的面板选择",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApprovalBundleError(
            f"intent cannot be read safely: {intent_id}",
            code="intent_invalid",
            safe_message="面板选择文件无效",
        ) from exc
    if not isinstance(data, dict):
        raise ApprovalBundleError(
            f"intent must be an object: {intent_id}",
            code="intent_invalid",
            safe_message="面板选择文件无效",
        )
    try:
        intents.validate_interaction_intent(data)
    except intents.IntentError as exc:
        raise ApprovalBundleError(
            f"intent validation failed: {intent_id}",
            code="intent_invalid",
            safe_message="面板选择文件无效",
        ) from exc
    return path, data


def _persist(path: Path, data: dict[str, Any]) -> None:
    intents._atomic_write_json(path, data)


def _expire_and_persist(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    expired = intents.expire_if_needed(data)
    if expired["status"] != data["status"]:
        _persist(path, expired)
    return expired


def _supersede_for_drift(
    path: Path,
    data: dict[str, Any],
    checkpoint_revision: str,
) -> None:
    if checkpoint_revision == data["revision"]:
        return
    if data["status"] in {"pending", "planned", "approved"}:
        data = intents.transition(data, "superseded")
        _persist(path, data)
    raise ApprovalBundleError(
        (
            "checkpoint revision does not match intent revision: "
            f"{checkpoint_revision!r} != {data['revision']!r}"
        ),
        code="intent_revision_drift",
        safe_message="面板选择版本已变化，请刷新后重新选择",
    )


def _require_approval_bundle(data: dict[str, Any]) -> None:
    if data.get("intent_type") != "approval_bundle":
        raise ApprovalBundleError(
            "intent is not an approval_bundle",
            code="intent_type_mismatch",
            safe_message="指定项目不是审批包选择",
        )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _first_text(*candidates: object) -> str:
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_number(*candidates: object) -> float | None:
    for value in candidates:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _selection_values(payload: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    selections = payload.get("selections")
    if not isinstance(selections, list):
        return values
    known_keys = {
        "production_tier",
        "review_mode",
        "provider",
        "model",
        "runtime",
        "duration_seconds",
        "theme",
        "quality_target",
        "resolution",
    }
    for item in selections:
        if not isinstance(item, dict):
            continue
        option_id = item.get("option_id") or item.get("id")
        if not isinstance(option_id, str) or not option_id.strip():
            continue
        option_id = option_id.strip()
        key = item.get("decision_key")
        if isinstance(key, str) and key.strip():
            short = key.rsplit("::", 1)[-1]
            if short in known_keys:
                values[short] = option_id
        if option_id in _TIER_IDS:
            values.setdefault("production_tier", option_id)
        if option_id in _REVIEW_IDS:
            values.setdefault(
                "review_mode",
                "pro" if option_id == "professional" else option_id,
            )
        if option_id in _RUNTIME_IDS:
            values.setdefault("runtime", option_id)
        duration = _first_number(option_id)
        if duration is not None and duration > 0:
            values.setdefault("duration_seconds", duration)
    return values


def _build_approval_payload(
    project_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    project = intents._project_dir(project_id)
    marker = _read_json_object(project / "project.json")
    profile = (
        marker.get("production_profile")
        if isinstance(marker.get("production_profile"), dict)
        else {}
    )
    brief = _read_json_object(project / "artifacts" / "brief.json")
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    picked = _selection_values(payload)

    production_tier = _first_text(
        payload.get("production_tier"),
        picked.get("production_tier"),
        profile.get("production_tier"),
        brief.get("production_tier"),
    )
    visual_source = _first_text(profile.get("visual_source"))
    allow_local_default = (
        production_tier == "light" or visual_source in _LOCAL_VISUAL_SOURCES
    )
    local_provider = "local" if allow_local_default else ""
    local_model = "deterministic" if allow_local_default else ""
    local_runtime = "remotion" if allow_local_default else ""
    light_runtime = (
        profile.get("light_presentation")
        if profile.get("light_presentation") in _RUNTIME_IDS
        else ""
    )

    theme = _first_text(
        payload.get("theme"),
        picked.get("theme"),
        brief.get("theme"),
        marker.get("title"),
        profile.get("theme"),
    )
    duration = _first_number(
        payload.get("duration_seconds"),
        picked.get("duration_seconds"),
        profile.get("duration_seconds"),
        brief.get("duration_seconds"),
        marker.get("duration_seconds"),
    )
    provider = _first_text(
        payload.get("provider"),
        picked.get("provider"),
        data.get("provider"),
        profile.get("video_channel"),
        profile.get("provider"),
        local_provider,
    )
    model = _first_text(
        payload.get("model"),
        picked.get("model"),
        data.get("model"),
        profile.get("video_model"),
        profile.get("model"),
        local_model,
    )
    runtime = _first_text(
        payload.get("runtime"),
        picked.get("runtime"),
        data.get("runtime"),
        profile.get("render_runtime"),
        light_runtime,
        local_runtime,
    )
    missing = [
        name
        for name, value in (
            ("theme", theme),
            ("duration_seconds", duration if duration is not None and duration > 0 else None),
            ("production_tier", production_tier),
            ("provider", provider),
            ("model", model),
            ("runtime", runtime),
        )
        if value in (None, "")
    ]
    if missing:
        raise ApprovalBundleError(
            f"cannot build approval bundle; missing {', '.join(missing)}",
            code="missing_project_evidence",
            safe_message="当前项目证据不足，无法生成审批包，请改用完整确认卡",
        )

    unit_price = _first_number(
        payload.get("unit_price_cny"),
        profile.get("unit_price_cny"),
    )
    if unit_price is None:
        unit_price = 0.0
    total_budget = _first_number(
        payload.get("total_budget_cny"),
        profile.get("budget_cny"),
        data.get("cost_cap_cny"),
    )
    if total_budget is None:
        total_budget = 0.0
    max_generations = _first_number(
        payload.get("max_generations"),
        data.get("call_cap"),
        2,
    )
    auto_retry = _first_number(payload.get("auto_retry_count"), 1)
    auto_stages = payload.get("auto_stages")
    if not isinstance(auto_stages, list) or not auto_stages:
        auto_stages = list(_COMMERCIAL_AUTO_STAGES)
    pause_conditions = payload.get("pause_conditions")
    if not isinstance(pause_conditions, list) or not pause_conditions:
        pause_conditions = list(_DEFAULT_PAUSE_CONDITIONS)

    return {
        "theme": theme,
        "duration_seconds": float(duration),
        "production_tier": production_tier,
        "review_mode": _first_text(
            payload.get("review_mode"),
            picked.get("review_mode"),
            profile.get("review_mode"),
            "guided",
        ),
        "provider": provider,
        "model": model,
        "runtime": runtime,
        "asset_strategy": _first_text(payload.get("asset_strategy"), "reuse-approved"),
        "allow_deterministic_reuse": (
            payload["allow_deterministic_reuse"]
            if isinstance(payload.get("allow_deterministic_reuse"), bool)
            else True
        ),
        "max_generations": int(max_generations or 2),
        "unit_price_cny": float(unit_price),
        "total_budget_cny": float(total_budget),
        "resolution": _first_text(
            payload.get("resolution"),
            picked.get("resolution"),
            profile.get("resolution"),
            "1080x1920",
        ),
        "quality_target": _first_text(
            payload.get("quality_target"),
            picked.get("quality_target"),
            profile.get("quality_target"),
            "draft",
        ),
        "auto_retry_count": int(auto_retry if auto_retry is not None else 1),
        "auto_stages": [str(item) for item in auto_stages if str(item).strip()],
        "pause_conditions": [
            str(item) for item in pause_conditions if str(item).strip()
        ],
        "expires_at": str(payload.get("expires_at") or data["expires_at"]),
        "revoke_method": _first_text(payload.get("revoke_method"), REVOKE_METHOD),
    }


def _materialize_approval_bundle(
    project_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    intent_type = data.get("intent_type")
    if intent_type == "approval_bundle":
        return data
    if intent_type not in _PLAN_SOURCE_TYPES:
        raise ApprovalBundleError(
            "intent is not an approval_bundle",
            code="intent_type_mismatch",
            safe_message="指定项目不是审批包选择",
        )

    payload = _build_approval_payload(project_id, data)
    promoted = dict(data)
    promoted["intent_type"] = "approval_bundle"
    promoted["payload"] = payload
    note = data.get("note")
    raw_payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    payload_note = raw_payload.get("note")
    if not note and isinstance(payload_note, str) and payload_note.strip():
        promoted["note"] = payload_note.strip()
    promoted["provider"] = payload["provider"]
    promoted["model"] = payload["model"]
    promoted["runtime"] = payload["runtime"]
    promoted["cost_cap_cny"] = payload["total_budget_cny"]
    promoted["call_cap"] = payload["max_generations"]
    try:
        intents.validate_interaction_intent(promoted)
    except intents.IntentError as exc:
        raise ApprovalBundleError(
            f"promoted approval bundle invalid: {exc}",
            code="missing_project_evidence",
            safe_message="当前项目证据不足，无法生成审批包，请改用完整确认卡",
        ) from exc
    return promoted


def _restore_bytes(path: Path, original: bytes) -> None:
    temporary = path.with_name(f".{path.name}.rollback.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(original)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _decision_json(data: dict[str, Any]) -> str:
    intent_id = str(data["intent_id"])
    revision = str(data["revision"])
    decision = {
        "decision_id": f"approval-bundle:{intent_id}:{revision}",
        "stage": str(data["stage"]),
        "category": "approval_policy",
        "subject": FAST_TRACK_SUBJECT,
        "options_considered": [
            {
                "option_id": FAST_TRACK_SELECTED,
                "label": "商品片快速模式 v2（面板 intent）",
                "score": 1.0,
                "reason": (
                    "面板已提交待确认选择；Agent 已按当前 revision 生成并展示 "
                    "approval bundle 中文摘要，后续推进由证据 snapshot 的 evaluate 结果决定。"
                ),
            }
        ],
        "selected": FAST_TRACK_SELECTED,
        "reason": (
            "approval_source=fast_track_v2；"
            f"用户确认审批包：{data['summary']}"
        ),
        "user_visible": True,
        "user_approved": True,
        "user_response_text": CONFIRM_PHRASE,
    }
    return json.dumps(decision, ensure_ascii=False)


def list_interaction_intents(project_id: str) -> list[dict[str, Any]]:
    """List valid interaction intents while ignoring edit and corrupt files."""

    project = intents._project_dir(project_id)
    directory = project / intents.INTENTS_SUBDIR
    if not directory.is_dir():
        return []

    listed: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or data.get("intent_type") not in intents.INTERACTION_INTENT_TYPES
            ):
                continue
            intents.validate_interaction_intent(data)
        except (OSError, json.JSONDecodeError, intents.IntentError):
            continue
        data = _expire_and_persist(path, data)
        listed.append(data)
    return listed


def plan_approval_bundle(
    project_id: str,
    intent_id: str,
    *,
    checkpoint_revision: str,
) -> dict[str, Any]:
    """Build a §6.3 bundle from a panel decision and persist pending→planned."""

    path, data = _load(project_id, intent_id)
    data = _expire_and_persist(path, data)
    _supersede_for_drift(path, data, checkpoint_revision)
    if data["status"] not in {"pending", "planned"}:
        raise ApprovalBundleError(
            f"approval bundle cannot be planned from {data['status']}",
            code="intent_status_invalid",
            safe_message="当前面板选择状态不能进入计划",
        )
    data = _materialize_approval_bundle(project_id, data)

    if data["status"] == "pending":
        data = intents.transition(data, "planned")
        _persist(path, data)
    elif data["status"] == "planned":
        _persist(path, data)
    else:
        raise ApprovalBundleError(
            f"approval bundle cannot be planned from {data['status']}",
            code="intent_status_invalid",
            safe_message="当前面板选择状态不能进入计划",
        )

    return {
        "intent": data,
        "summary_zh": f"已计划审批包：{data['summary']}（版本 {data['revision']}）",
    }


def apply_approval_bundle(
    project_id: str,
    intent_id: str,
    *,
    confirm_phrase: str,
    checkpoint_revision: str,
    append_decision: Callable[[str, str], Any],
) -> dict[str, Any]:
    """Apply a planned approval bundle and append its audit decision."""

    if confirm_phrase != CONFIRM_PHRASE:
        raise ApprovalBundleError(
            "confirm_phrase must exactly equal 确认面板选择",
            code="confirmation_required",
            safe_message="请输入确认面板选择",
        )

    path, data = _load(project_id, intent_id)
    _require_approval_bundle(data)
    data = _expire_and_persist(path, data)
    _supersede_for_drift(path, data, checkpoint_revision)
    if data["status"] == "pending":
        raise ApprovalBundleError(
            "approval bundle must be planned before apply",
            code="intent_plan_required",
            safe_message="请先计划该面板选择，再执行确认",
        )
    if data["status"] != "planned":
        raise ApprovalBundleError(
            f"approval bundle cannot be applied from {data['status']}",
            code="intent_status_invalid",
            safe_message="当前面板选择状态不能应用",
        )

    original = path.read_bytes()
    approved = intents.transition(data, "approved")
    applied = intents.transition(approved, "applied")
    try:
        _persist(path, applied)
        decision_result = append_decision(project_id, _decision_json(applied))
    except Exception:
        _restore_bytes(path, original)
        raise

    return {
        "intent": applied,
        "decision": decision_result,
        "summary_zh": f"已应用审批包：{applied['summary']}",
    }
