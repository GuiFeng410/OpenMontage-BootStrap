"""Read-only fast-track v2 continue/pause/signoff comparator."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from schemas.artifacts import validate_artifact

ACTIONS = ("continue", "pause", "signoff_ready")

REQUIRED_SNAPSHOT_FIELDS = (
    "policy",
    "now",
    "current_stage",
    "asset_matrix_closed",
    "generated_images_pending_review",
    "provider",
    "model",
    "runtime",
    "cost_cny_used",
    "calls_used",
    "unit_price_cny",
    "identity_qa_pass",
    "structure_qa_pass",
    "technical_qa_pass",
    "new_cloud_upload_authorization",
    "new_cross_beat_reuse",
    "product_downgrade_or_hero_replace",
    "revision_list_nonempty",
    "user_paused",
    "user_revoked",
    "user_revision_submitted",
    "intent_expired",
    "revision_drift",
    "artifact_revision",
    "bundle_baseline_revision",
    "final_video_ready",
)

REASON_CODES = {
    "missing_field",
    "policy_invalid",
    "policy_expired",
    "stage_not_authorized",
    "asset_matrix_open",
    "generated_image_review",
    "new_cross_beat_reuse",
    "provider_changed",
    "model_changed",
    "runtime_changed",
    "budget_exceeded",
    "unit_price_exceeded",
    "call_cap_exceeded",
    "identity_qa_failed",
    "structure_qa_failed",
    "technical_qa_failed",
    "pixverse_cloud_upload",
    "product_expression_downgrade",
    "user_paused",
    "user_revoked",
    "user_revision",
    "intent_expired",
    "revision_drift",
    "awaiting_signoff",
}

_BOOLEAN_FIELDS = (
    "asset_matrix_closed",
    "generated_images_pending_review",
    "identity_qa_pass",
    "structure_qa_pass",
    "technical_qa_pass",
    "new_cloud_upload_authorization",
    "new_cross_beat_reuse",
    "product_downgrade_or_hero_replace",
    "revision_list_nonempty",
    "user_paused",
    "user_revoked",
    "user_revision_submitted",
    "intent_expired",
    "revision_drift",
    "final_video_ready",
)

_NUMERIC_FIELDS = ("cost_cny_used", "calls_used", "unit_price_cny")

_PAUSE_COPY = {
    "missing_field": (
        "快速模式信息不完整，已暂停。",
        "请补齐当前快照中的必填字段后再试。",
    ),
    "policy_invalid": (
        "快速模式授权策略无效，已暂停。",
        "请重新确认一份符合约束的快速模式策略。",
    ),
    "policy_expired": (
        "快速模式授权已过期，已暂停。",
        "请在聊天中重新授权快速模式。",
    ),
    "intent_expired": (
        "当前交互意图已过期，已暂停。",
        "请重新提交当前阶段的操作意图。",
    ),
    "revision_drift": (
        "项目证据版本已变化，已暂停。",
        "请基于最新版本重新核对并确认。",
    ),
    "user_paused": (
        "已按用户要求暂停快速模式。",
        "请确认是否恢复快速模式。",
    ),
    "user_revoked": (
        "用户已撤销快速模式授权。",
        "请在聊天中重新授权后再继续。",
    ),
    "user_revision": (
        "检测到用户修改请求，已暂停。",
        "请先处理当前修改请求。",
    ),
    "generated_image_review": (
        "生成图片仍待人工审核，已暂停。",
        "请先完成当前生成图片的审核。",
    ),
    "asset_matrix_open": (
        "素材矩阵尚未封板，已暂停。",
        "请先完成素材矩阵确认。",
    ),
    "provider_changed": (
        "当前供应商与授权策略不一致，已暂停。",
        "请确认是否改用当前供应商。",
    ),
    "model_changed": (
        "当前模型与授权策略不一致，已暂停。",
        "请确认是否改用当前模型。",
    ),
    "runtime_changed": (
        "当前运行时与授权策略不一致，已暂停。",
        "请确认是否改用当前运行时。",
    ),
    "budget_exceeded": (
        "累计费用已超过授权预算，已暂停。",
        "请确认是否调整预算上限。",
    ),
    "call_cap_exceeded": (
        "调用次数已超过授权上限，已暂停。",
        "请确认是否调整调用次数上限。",
    ),
    "unit_price_exceeded": (
        "当前单价高于授权锁定单价，或下一次调用会撑破预算，已暂停。",
        "请确认是否允许当前单次调用费用。",
    ),
    "identity_qa_failed": (
        "主体一致性检查未通过，已暂停。",
        "请先修复主体一致性问题。",
    ),
    "structure_qa_failed": (
        "结构质量检查未通过，已暂停。",
        "请先修复结构质量问题。",
    ),
    "technical_qa_failed": (
        "技术质量检查未通过，已暂停。",
        "请先修复技术质量问题。",
    ),
    "pixverse_cloud_upload": (
        "出现新的云端上传授权事项，已暂停。",
        "请确认是否允许本次云端上传。",
    ),
    "new_cross_beat_reuse": (
        "出现新的跨节拍素材复用，已暂停。",
        "请确认是否允许本次跨节拍复用。",
    ),
    "product_expression_downgrade": (
        "出现产品表达降级或主图替换，已暂停。",
        "请确认是否接受本次产品表达调整。",
    ),
    "stage_not_authorized": (
        "当前阶段不在自动执行授权范围内，已暂停。",
        "请确认是否授权当前阶段。",
    ),
}


def _pause(reason_code: str) -> dict[str, Any]:
    friendly_zh, current_question = _PAUSE_COPY[reason_code]
    return {
        "action": "pause",
        "reason_code": reason_code,
        "friendly_zh": friendly_zh,
        "current_question": current_question,
    }


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("datetime must be a non-empty string")
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def _same_text(left: object, right: object) -> bool:
    return isinstance(left, str) and isinstance(right, str) and left.strip() == right.strip()


def evaluate_fast_track(snapshot: dict) -> dict:
    """Return the first fail-closed fast-track action without any writes."""
    if not isinstance(snapshot, dict):
        return _pause("missing_field")

    current = deepcopy(snapshot)
    if any(
        field not in current or current[field] is None
        for field in REQUIRED_SNAPSHOT_FIELDS
    ):
        return _pause("missing_field")
    if any(type(current[field]) is not bool for field in _BOOLEAN_FIELDS):
        return _pause("missing_field")
    if any(
        isinstance(current[field], bool)
        or not isinstance(current[field], (int, float))
        for field in _NUMERIC_FIELDS
    ):
        return _pause("missing_field")

    policy = current["policy"]
    try:
        validate_artifact("fast_track_policy", policy)
        expires_at = _parse_datetime(policy["expires_at"])
    except Exception:  # noqa: BLE001 - invalid policy must fail closed
        return _pause("policy_invalid")

    try:
        now = _parse_datetime(current["now"])
        expired = now >= expires_at
    except (TypeError, ValueError):
        return _pause("missing_field")
    if expired:
        return _pause("policy_expired")
    if current["intent_expired"]:
        return _pause("intent_expired")
    if (
        current["revision_drift"]
        or current["artifact_revision"] != current["bundle_baseline_revision"]
    ):
        return _pause("revision_drift")
    if current["user_paused"]:
        return _pause("user_paused")
    if current["user_revoked"]:
        return _pause("user_revoked")
    if current["user_revision_submitted"] or current["revision_list_nonempty"]:
        return _pause("user_revision")
    if current["generated_images_pending_review"]:
        return _pause("generated_image_review")
    if not current["asset_matrix_closed"]:
        return _pause("asset_matrix_open")
    if not _same_text(current["provider"], policy["provider"]):
        return _pause("provider_changed")
    if not _same_text(current["model"], policy["model"]):
        return _pause("model_changed")
    if not _same_text(current["runtime"], policy["runtime"]):
        return _pause("runtime_changed")
    if current["cost_cny_used"] > policy["cost_cap_cny"]:
        return _pause("budget_exceeded")
    if current["calls_used"] > policy["call_cap"]:
        return _pause("call_cap_exceeded")
    if current["unit_price_cny"] > policy["unit_price_cny"]:
        return _pause("unit_price_exceeded")
    if current["unit_price_cny"] > 0 and (
        policy["cost_cap_cny"] == 0
        or current["cost_cny_used"] + current["unit_price_cny"]
        > policy["cost_cap_cny"]
    ):
        return _pause("unit_price_exceeded")
    if not current["identity_qa_pass"]:
        return _pause("identity_qa_failed")
    if not current["structure_qa_pass"]:
        return _pause("structure_qa_failed")
    if not current["technical_qa_pass"]:
        return _pause("technical_qa_failed")
    if current["new_cloud_upload_authorization"]:
        return _pause("pixverse_cloud_upload")
    if current["new_cross_beat_reuse"]:
        return _pause("new_cross_beat_reuse")
    if current["product_downgrade_or_hero_replace"]:
        return _pause("product_expression_downgrade")
    if current["current_stage"] not in policy["auto_stages"]:
        return _pause("stage_not_authorized")

    if current["current_stage"] == "delivery_signoff":
        if current["final_video_ready"]:
            return {
                "action": "signoff_ready",
                "reason_code": "awaiting_signoff",
                "friendly_zh": "最终视频已就绪，等待人工签收。",
                "current_question": "请确认是否签收当前最终视频？",
            }
        return _pause("missing_field")

    return {
        "action": "continue",
        "reason_code": None,
        "friendly_zh": "当前条件满足，可继续下一阶段。",
        "current_question": None,
    }


def pause_checkpoint_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Metadata patch for produce_write_checkpoint after a pause result."""

    if not isinstance(result, dict):
        result = {}
    return {
        "fast_track_pause": {
            "reason_code": result.get("reason_code") or "",
            "friendly_zh": result.get("friendly_zh") or "",
            "current_question": result.get("current_question") or "",
        }
    }
