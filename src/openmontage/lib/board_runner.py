"""Local Backlot-side consumer for pending interaction intents.

The browser only writes intents. This runner applies panel decisions,
runs authorized image-to-image at assets_gate, starts produce after
the gate is sealed, and handles end-and-export. It never silently
switches providers. The browser still does not call paid APIs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import lib.approval_bundle as approval_bundle
import lib.board_advance as board_advance
import lib.board_produce as board_produce
import lib.board_production_run as production_run
import lib.interaction_intents as intents
import lib.project_export as project_export
from lib.checkpoint import CheckpointValidationError
from lib.paths import PROJECTS_DIR

PHASE_IDLE = "idle"
PHASE_QUEUED = "queued"
PHASE_APPLYING = "applying"
PHASE_PRODUCING = "producing"
PHASE_PAUSED = "paused"
PHASE_READY = "ready"
PHASE_EXPORTED = "exported"
PHASE_NEEDS_CHAT = "needs_chat"

_PAID_AUTHORIZATION_SCOPES = {
    "assets_gate": "batch",
    "sample_review": "batch",
}


def _list_pending(project_id: str) -> list[dict[str, Any]]:
    listed = []
    for item in approval_bundle.list_interaction_intents(project_id):
        if item.get("status") in {"pending", "planned"}:
            listed.append(item)
    return listed


def _has_final(project_id: str) -> bool:
    return board_produce.final_ready_for_delivery(
        project_id,
        projects_dir=PROJECTS_DIR,
    )


def _consume_export(project_id: str, pending: list[dict[str, Any]]) -> dict[str, Any] | None:
    exports = [item for item in pending if item.get("intent_type") == "project_export"]
    if not exports:
        return None
    latest = exports[-1]
    from lib.application.export_project import export_project

    return export_project(
        project_id,
        intent_id=str(latest["intent_id"]),
    )


def _peek_intent(project_id: str, intent_id: str) -> dict[str, Any]:
    path = intents._intent_path(intents._project_dir(project_id), intent_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _complete_brief_locked(
    project_id: str,
    artifacts: dict[str, Any],
) -> None:
    from lib.application.approve_stage import approve_stage

    approve_stage(
        project_id,
        "brief_locked",
        "panel_intent",
        artifacts={
            "brief": artifacts["brief"],
            "asset_precheck": artifacts["asset_precheck"],
            "video_plan": artifacts["video_plan"],
            "segment_cards": artifacts["segment_cards"],
        },
        pipeline_type="bootstrap-commercial",
        metadata={"approval_source": "panel_intent"},
        metadata_remove_keys=board_advance.DECISION_STALE_KEYS,
        record_approval_note=False,
    )


def _complete_review_stage(project_id: str, stage: str) -> None:
    from lib.application.approve_stage import approve_stage
    from lib.checkpoint import read_checkpoint

    evidence = board_advance.review_stage_evidence(
        project_id, stage, projects_dir=PROJECTS_DIR
    )
    if not evidence.get("ready"):
        raise approval_bundle.ApprovalBundleError(
            "review evidence missing",
            code="review_evidence_missing",
            safe_message=str(evidence.get("friendly_zh") or "当前阶段还没有可评审视频。"),
        )
    current = read_checkpoint(PROJECTS_DIR, project_id, stage)
    artifacts = current.get("artifacts") if isinstance(current, dict) else None
    if not isinstance(artifacts, dict) or not artifacts:
        raise approval_bundle.ApprovalBundleError(
            "review checkpoint artifacts missing",
            code="review_evidence_missing",
            safe_message="当前阶段视频已发现，但 checkpoint 证据不完整，请先写回阶段证据。",
        )
    approve_stage(
        project_id,
        stage,
        "panel_intent",
        artifacts=artifacts,
        pipeline_type=str(current.get("pipeline_type") or "bootstrap-commercial"),
        metadata={"approval_source": "panel_intent"},
        metadata_remove_keys=board_advance.DECISION_STALE_KEYS,
        human_approval_required=bool(current.get("human_approval_required")),
        record_approval_note=False,
    )


def _consume_decision(
    project_id: str,
    pending: list[dict[str, Any]],
    *,
    append_decision: Callable[[str, str], Any],
) -> dict[str, Any] | None:
    decisions = [
        item
        for item in pending
        if item.get("intent_type") in {"decision", "approval_bundle"}
    ]
    if not decisions:
        return None
    item = decisions[-1]
    intent_id = str(item["intent_id"])
    revision = str(item["revision"])
    raw = _peek_intent(project_id, intent_id)
    stage = str(raw.get("stage") or item.get("stage") or "")
    lock_result: dict[str, Any] | None = None
    if stage == "brief_locked":
        from lib.board_gap_plan import GapPlanError, lock_gap_plan_from_intent

        try:
            lock_result = lock_gap_plan_from_intent(
                project_id,
                raw,
                projects_dir=PROJECTS_DIR,
            )
        except GapPlanError as exc:
            raise approval_bundle.ApprovalBundleError(
                str(exc),
                code=exc.code,
                safe_message=exc.safe_message,
            ) from exc
        if lock_result.get("action") == "continue" and lock_result.get("artifacts"):
            try:
                _complete_brief_locked(project_id, lock_result["artifacts"])
            except Exception as exc:
                raise approval_bundle.ApprovalBundleError(
                    str(exc),
                    code="brief_lock_failed",
                    safe_message="方案已选出，但本机无法写入合法规划。请留在本页刷新后重试。",
                ) from exc
    elif stage == "assets_gate":
        from lib.board_assets_gate import AssetsGateError, seal_assets_gate
        from lib.board_gap_plan import stop_action_from_intent
        from lib.board_i2i import BoardI2IError, approve_pending_i2i, run_i2i_generate

        gate_action = stop_action_from_intent(raw)
        if gate_action == "revise":
            lock_result = {"action": "revise", "artifacts": {}}
        elif gate_action == "generate":
            try:
                gen_result = run_i2i_generate(
                    project_id, projects_dir=PROJECTS_DIR
                )
            except BoardI2IError as exc:
                raise approval_bundle.ApprovalBundleError(
                    str(exc),
                    code=exc.code,
                    safe_message=exc.safe_message,
                ) from exc
            lock_result = {
                "action": "generate",
                "artifacts": gen_result,
            }
            board_advance.write_stop_card(
                project_id, "assets_gate", projects_dir=PROJECTS_DIR
            )
        else:
            try:
                approve_pending_i2i(project_id, projects_dir=PROJECTS_DIR)
                seal_result = seal_assets_gate(project_id, projects_dir=PROJECTS_DIR)
                lock_result = {
                    "action": "continue",
                    "artifacts": seal_result.get("artifacts") or {},
                }
            except BoardI2IError as exc:
                raise approval_bundle.ApprovalBundleError(
                    str(exc),
                    code=exc.code,
                    safe_message=exc.safe_message,
                ) from exc
            except AssetsGateError as exc:
                raise approval_bundle.ApprovalBundleError(
                    str(exc),
                    code=exc.code,
                    safe_message=exc.safe_message,
                ) from exc
    elif stage == "delivery_signoff":
        from lib.board_gap_plan import stop_action_from_intent

        delivery_action = stop_action_from_intent(raw)
        if delivery_action != "revise" and not _has_final(project_id):
            raise approval_bundle.ApprovalBundleError(
                "final video missing",
                code="final_video_required",
                safe_message=(
                    "成片尚未就绪，请留在本页等待制作。有成片后即可预览并导出。"
                    "不必回聊天。"
                ),
            )
        lock_result = {
            "action": "revise" if delivery_action == "revise" else "continue",
            "artifacts": {},
        }
    elif stage in {"sample_review", "segment_build", "draft_review", "final_compose"}:
        from lib.board_gap_plan import stop_action_from_intent

        review_action = stop_action_from_intent(raw)
        if stage == "draft_review" and review_action in {"reject", "revise"}:
            from lib.board_draft_review import DraftReviewError, apply_draft_reject

            try:
                apply_draft_reject(
                    project_id, raw, projects_dir=PROJECTS_DIR
                )
            except DraftReviewError as exc:
                raise approval_bundle.ApprovalBundleError(
                    str(exc),
                    code=exc.code,
                    safe_message=exc.safe_message,
                ) from exc
            board_advance.write_stop_card(
                project_id, "draft_review", projects_dir=PROJECTS_DIR
            )
            lock_result = {"action": "reject", "artifacts": {}}
        elif stage == "draft_review":
            evidence = board_advance.review_stage_evidence(
                project_id, stage, projects_dir=PROJECTS_DIR
            )
            if not evidence.get("ready"):
                board_advance.write_stop_card(
                    project_id, stage, projects_dir=PROJECTS_DIR
                )
                raise approval_bundle.ApprovalBundleError(
                    "review evidence missing",
                    code="review_evidence_missing",
                    safe_message=str(
                        evidence.get("friendly_zh") or "当前阶段还没有可评审视频。"
                    ),
                )
            from lib.board_draft_review import DraftReviewError, apply_draft_approve

            try:
                apply_draft_approve(project_id, projects_dir=PROJECTS_DIR)
            except DraftReviewError as exc:
                raise approval_bundle.ApprovalBundleError(
                    str(exc),
                    code=exc.code,
                    safe_message=exc.safe_message,
                ) from exc
            lock_result = {"action": "continue", "artifacts": {}}
        else:
            if review_action != "revise":
                evidence = board_advance.review_stage_evidence(
                    project_id, stage, projects_dir=PROJECTS_DIR
                )
                if not evidence.get("ready"):
                    board_advance.write_stop_card(
                        project_id, stage, projects_dir=PROJECTS_DIR
                    )
                    raise approval_bundle.ApprovalBundleError(
                        "review evidence missing",
                        code="review_evidence_missing",
                        safe_message=str(
                            evidence.get("friendly_zh") or "当前阶段还没有可评审视频。"
                        ),
                    )
            lock_result = {
                "action": "revise" if review_action == "revise" else "continue",
                "artifacts": {},
            }
    planned = approval_bundle.plan_approval_bundle(
        project_id,
        intent_id,
        checkpoint_revision=revision,
    )
    applied = approval_bundle.apply_approval_bundle(
        project_id,
        intent_id,
        confirm_phrase=approval_bundle.CONFIRM_PHRASE,
        checkpoint_revision=revision,
        append_decision=append_decision,
    )
    if (
        stage in _PAID_AUTHORIZATION_SCOPES
        and (lock_result or {}).get("action") == "continue"
    ):
        try:
            _record_stage_authorization(
                project_id,
                stage,
                intent_id,
                revision,
            )
        except (production_run.ProductionRunError, OSError) as exc:
            raise approval_bundle.ApprovalBundleError(
                str(exc),
                code="run_state_invalid",
                safe_message=(
                    "选择已应用，但生产授权状态无法安全写入。已暂停且不会调用视频模型，"
                    "请留在本页刷新恢复。"
                ),
            ) from exc
    if (
        stage in {"sample_review", "segment_build", "draft_review", "final_compose"}
        and (lock_result or {}).get("action") not in {"revise", "reject"}
    ):
        _complete_review_stage(project_id, stage)
    return {
        "planned": planned,
        "applied": applied,
        "intent_id": intent_id,
        "stop_action": (lock_result or {}).get("action") or "continue",
    }


def _load_plan_artifacts_from_disk(project_id: str) -> dict[str, Any] | None:
    project_dir = PROJECTS_DIR / project_id
    art_dir = project_dir / "artifacts"
    keys = ("gap_plan", "brief", "asset_precheck", "video_plan", "segment_cards")
    artifacts: dict[str, Any] = {}
    for key in keys:
        path = art_dir / f"{key}.json"
        if not path.is_file():
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(loaded, dict):
            return None
        artifacts[key] = loaded
    return artifacts


def _has_applied_stage_intent(project_id: str, stage: str) -> bool:
    intents_dir = PROJECTS_DIR / project_id / "intents"
    if not intents_dir.is_dir():
        return False
    for path in sorted(intents_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if str(data.get("stage") or "") != stage:
            continue
        if str(data.get("status") or "") != "applied":
            continue
        if data.get("intent_type") in {"decision", "approval_bundle"}:
            return True
    return False


def _has_applied_brief_locked_intent(project_id: str) -> bool:
    return _has_applied_stage_intent(project_id, "brief_locked")


def _last_applied_stage_intent(project_id: str, stage: str) -> dict[str, Any] | None:
    intents_dir = PROJECTS_DIR / project_id / "intents"
    if not intents_dir.is_dir():
        return None
    latest: dict[str, Any] | None = None
    latest_key = ""
    for path in sorted(intents_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if str(data.get("stage") or "") != stage:
            continue
        if str(data.get("status") or "") != "applied":
            continue
        if data.get("intent_type") not in {"decision", "approval_bundle"}:
            continue
        key = str(data.get("created_at") or path.stem)
        if key >= latest_key:
            latest_key = key
            latest = data
    return latest


def _record_stage_authorization(
    project_id: str,
    stage: str,
    intent_id: str,
    revision: str,
) -> bool:
    scope = _PAID_AUTHORIZATION_SCOPES.get(stage)
    if not scope:
        return False
    project = PROJECTS_DIR / project_id
    existing = production_run.read_production_run(project)
    if existing and any(
        item.get("authorization_revision") == revision
        for item in existing.get("authorization_refs") or []
        if isinstance(item, dict)
    ):
        return False
    run, _created = production_run.load_or_initialize_production_run(
        project,
        persist=False,
    )
    updated = production_run.add_authorization_ref(
        run,
        authorization_revision=revision,
        scope=scope,
        intent_ref=f"intents/{intent_id}.json",
    )
    production_run.write_production_run(project, updated)
    return True


def _recover_applied_authorization(project_id: str) -> bool:
    for stage in _PAID_AUTHORIZATION_SCOPES:
        raw = _last_applied_stage_intent(project_id, stage)
        if not raw:
            continue
        intent_id = str(raw.get("intent_id") or "").strip()
        revision = str(raw.get("revision") or "").strip()
        if not intent_id or not revision:
            continue
        from lib.board_gap_plan import stop_action_from_intent

        if stop_action_from_intent(raw) == "revise":
            continue
        if _record_stage_authorization(
            project_id,
            stage,
            intent_id,
            revision,
        ):
            return True
    return False


def _recover_stuck_assets_gate(
    project_id: str,
    marker: dict[str, Any],
) -> bool:
    from lib.checkpoint import read_checkpoint
    from lib.board_assets_gate import plan_allows_auto_seal, seal_assets_gate

    checkpoint = read_checkpoint(PROJECTS_DIR, project_id, "assets_gate")
    if not isinstance(checkpoint, dict) or checkpoint.get("status") == "completed":
        return False
    project_dir = PROJECTS_DIR / project_id
    if not plan_allows_auto_seal(project_dir):
        return False
    if not _has_applied_stage_intent(project_id, "assets_gate"):
        return False
    try:
        seal_assets_gate(project_id, projects_dir=PROJECTS_DIR)
        board_advance.advance_after_apply(
            project_id,
            "assets_gate",
            marker,
            projects_dir=PROJECTS_DIR,
        )
        return True
    except Exception:
        return False


def _recover_stuck_brief_locked(
    project_id: str,
    marker: dict[str, Any],
) -> bool:
    """Complete brief_locked when intent was applied but checkpoint/artifacts lag."""
    from lib.checkpoint import read_checkpoint
    from lib.board_gap_plan import GapPlanError, lock_gap_plan_from_intent

    checkpoint = read_checkpoint(PROJECTS_DIR, project_id, "brief_locked")
    if not isinstance(checkpoint, dict) or checkpoint.get("status") == "completed":
        return False
    if not _has_applied_brief_locked_intent(project_id):
        return False
    artifacts = _load_plan_artifacts_from_disk(project_id)
    if not artifacts:
        raw = _last_applied_stage_intent(project_id, "brief_locked")
        if not raw:
            return False
        try:
            lock_result = lock_gap_plan_from_intent(
                project_id,
                raw,
                projects_dir=PROJECTS_DIR,
            )
        except GapPlanError:
            return False
        if lock_result.get("action") != "continue" or not lock_result.get("artifacts"):
            return False
        artifacts = lock_result["artifacts"]
    try:
        _complete_brief_locked(project_id, artifacts)
        board_advance.advance_after_apply(
            project_id,
            "brief_locked",
            marker,
            projects_dir=PROJECTS_DIR,
        )
        return True
    except Exception:
        return False


def _recover_stuck_delivery_signoff(
    project_id: str,
    marker: dict[str, Any],
) -> bool:
    """Reopen delivery when it was marked completed without a final video."""
    if _has_final(project_id):
        return False
    current = board_advance.current_confirm_stop(
        project_id, marker, projects_dir=PROJECTS_DIR
    )
    if current != "delivery_signoff":
        return False
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    from lib.checkpoint import CheckpointValidationError, read_checkpoint

    try:
        checkpoint = read_checkpoint(PROJECTS_DIR, project_id, "delivery_signoff")
    except CheckpointValidationError:
        checkpoint = {"status": "completed"}
    already_waiting = bool(stop.get("paused")) or (
        bool(stop.get("producing_wait"))
        and (not isinstance(checkpoint, dict) or checkpoint.get("status") != "completed")
    )
    if already_waiting:
        return False
    try:
        seeded = board_advance.ensure_current_stop_card(
            project_id, marker, projects_dir=PROJECTS_DIR
        )
        return bool(seeded)
    except Exception:
        return False


def tick(
    project_id: str,
    *,
    append_decision: Callable[[str, str], Any],
    runner_alive: bool = True,
) -> dict[str, Any]:
    """Consume one round of pending intents. Paid generate only after panel intent."""
    marker = project_export.read_marker(project_id)
    if project_export.is_completed(marker):
        status = {
            "phase": PHASE_EXPORTED,
            "runner_alive": runner_alive,
            "friendly_zh": "项目已结束并导出，不再自动续做。",
            "export_path": marker.get("export_path"),
            "stop_runner": True,
            "library_path": "/",
        }
        project_export.write_runner_status(project_id, status)
        return {"project_id": project_id, **status, "actions": []}

    pending = _list_pending(project_id)
    actions: list[str] = []

    export_result = _consume_export(project_id, pending)
    if export_result is not None:
        actions.append("project_export")
        phase = PHASE_EXPORTED if export_result.get("ok") else PHASE_PAUSED
        status = {
            "phase": phase,
            "runner_alive": runner_alive,
            "friendly_zh": export_result.get("friendly_zh"),
            "export_path": export_result.get("export_path"),
            "stop_runner": phase == PHASE_EXPORTED,
            "library_path": "/" if phase == PHASE_EXPORTED else "",
        }
        if phase != PHASE_EXPORTED:
            project_export.write_runner_status(project_id, status)
        return {"project_id": project_id, **status, "actions": actions, "export": export_result}

    if pending:
        project_export.write_runner_status(
            project_id,
            {
                "phase": PHASE_APPLYING,
                "runner_alive": runner_alive,
                "friendly_zh": "已收到看板选择，本机正在处理，请留在本页。",
            },
        )
        try:
            applied = _consume_decision(
                project_id,
                pending,
                append_decision=append_decision,
            )
        except approval_bundle.ApprovalBundleError as exc:
            status = {
                "phase": PHASE_PAUSED,
                "runner_alive": runner_alive,
                "friendly_zh": getattr(exc, "safe_message", None)
                or "本机无法自动确认这笔选择。请留在本页，或点刷新重试。",
                "current_question": "请留在本页，或点刷新重试。",
            }
            project_export.write_runner_status(project_id, status)
            return {
                "project_id": project_id,
                **status,
                "actions": actions,
                "error": str(exc),
            }
        if applied:
            actions.append("approval_bundle")
            applied_stage = str((applied.get("applied") or {}).get("intent", {}).get("stage") or "")
            if not applied_stage:
                applied_stage = str((applied.get("planned") or {}).get("intent", {}).get("stage") or "")
            next_stop = None
            try:
                marker = board_advance.read_marker(
                    project_id, projects_dir=PROJECTS_DIR
                ) or marker
                stop_action = str(applied.get("stop_action") or "continue")
                if stop_action not in {"revise", "generate", "reject"}:
                    next_stop = board_advance.advance_after_apply(
                        project_id,
                        applied_stage or "brief_locked",
                        marker,
                        projects_dir=PROJECTS_DIR,
                    )
                elif stop_action == "reject" and applied_stage == "draft_review":
                    # Stay on draft_review with refreshed suggestions card.
                    board_advance.write_stop_card(
                        project_id, "draft_review", projects_dir=PROJECTS_DIR
                    )
            except Exception:
                next_stop = None
            if next_stop:
                actions.append("next_stop")

    remaining_early = _list_pending(project_id)
    recovered = False
    if not remaining_early and "next_stop" not in actions:
        marker = board_advance.read_marker(
            project_id, projects_dir=PROJECTS_DIR
        ) or marker
        recovered = _recover_stuck_brief_locked(project_id, marker)
        if not recovered:
            recovered = _recover_stuck_assets_gate(project_id, marker)
        if not recovered:
            recovered = _recover_stuck_delivery_signoff(project_id, marker)
        if recovered:
            actions.append("recover_stuck_stage")
            marker = board_advance.read_marker(
                project_id, projects_dir=PROJECTS_DIR
            ) or marker

    if not remaining_early:
        try:
            if _recover_applied_authorization(project_id):
                actions.append("recover_authorization")
        except (production_run.ProductionRunError, OSError) as exc:
            status = {
                "phase": PHASE_PAUSED,
                "runner_alive": runner_alive,
                "friendly_zh": (
                    "生产授权状态无法安全恢复。已暂停且不会调用视频模型，"
                    "请先修复生产状态文件。"
                ),
            }
            project_export.write_runner_status(project_id, status)
            return {
                "project_id": project_id,
                **status,
                "actions": actions,
                "error": str(exc),
            }

    seeded = None
    existing_job = board_produce.read_job(project_id) or {}
    job_status = str(existing_job.get("status") or "")
    job_blocks_seed = job_status in {
        board_produce.STATUS_PAUSED,
        board_produce.STATUS_QUEUED,
        board_produce.STATUS_RUNNING,
        board_produce.STATUS_FAILED,
    }
    if "approval_bundle" not in actions and not recovered and not job_blocks_seed:
        try:
            marker = board_advance.read_marker(
                project_id, projects_dir=PROJECTS_DIR
            ) or marker
            profile = (
                marker.get("production_profile")
                if isinstance(marker.get("production_profile"), dict)
                else {}
            )
            if profile.get("production_start_requested_at") or profile.get(
                "runner_start_pending"
            ):
                seeded = board_advance.ensure_current_stop_card(
                    project_id,
                    marker,
                    projects_dir=PROJECTS_DIR,
                )
                if seeded:
                    actions.append("seed_stop")
        except Exception:
            seeded = None

    produce = {"action": "", "status": ""}
    try:
        marker = board_advance.read_marker(
            project_id, projects_dir=PROJECTS_DIR
        ) or marker
        from lib.application.sync_production_job import sync_production_job

        produce = sync_production_job(project_id)
        if produce.get("action"):
            actions.append(str(produce["action"]))
    except Exception as exc:
        produce = {
            "action": "produce_paused",
            "status": board_produce.STATUS_PAUSED,
            "job": {
                "status": board_produce.STATUS_PAUSED,
                "code": "produce_state_error",
                "friendly_zh": (
                    "生产状态无法安全推进，已暂停且不会自动重试。"
                    "请留在本页查看状态后再处理。"
                ),
                "error": str(exc),
            },
        }
        actions.append("produce_paused")

    if _has_final(project_id):
        try:
            opened = board_advance.open_delivery_preview(
                project_id, projects_dir=PROJECTS_DIR
            )
        except Exception as exc:
            opened = {"ok": False, "error": str(exc)}
        if not opened.get("ok"):
            actions.append("delivery_paused")
            status = {
                "phase": PHASE_PAUSED,
                "runner_alive": runner_alive,
                "friendly_zh": (
                    "终稿证据已完成，但交付预览暂时无法打开。"
                    "项目未标记为可交付，请留在本页重试。"
                ),
            }
            project_export.write_runner_status(project_id, status)
            return {"project_id": project_id, **status, "actions": actions}
        actions.append("delivery_ready")
        status = {
            "phase": PHASE_READY,
            "runner_alive": runner_alive,
            "friendly_zh": board_advance.DELIVERY_READY_ZH,
        }
        project_export.write_runner_status(project_id, status)
        return {"project_id": project_id, **status, "actions": actions}

    remaining = _list_pending(project_id)
    marker = board_advance.read_marker(project_id, projects_dir=PROJECTS_DIR) or marker
    produce_job = produce.get("job") if isinstance(produce.get("job"), dict) else {}
    produce_status = str(produce.get("status") or produce_job.get("status") or "")
    produce_copy = str(produce_job.get("friendly_zh") or "")
    board_stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    if remaining:
        status = {
            "phase": PHASE_QUEUED,
            "runner_alive": runner_alive,
            "friendly_zh": "选择已提交，本机排队处理中，请留在本页。",
        }
    elif produce_status == board_produce.STATUS_PAUSED:
        status = {
            "phase": PHASE_PAUSED,
            "runner_alive": runner_alive,
            "friendly_zh": produce_copy or "制作已暂停。请留在本页刷新可用性，不要改档除非你要求。",
        }
    elif produce_status == board_produce.STATUS_FAILED:
        exhausted = bool(produce_job.get("retry_exhausted"))
        status = {
            "phase": PHASE_PAUSED,
            "runner_alive": runner_alive,
            "retry_exhausted": exhausted,
            "stop_runner": exhausted,
            "friendly_zh": produce_copy or "制作失败，请留在本页查看原因。",
        }
    elif board_stop.get("paused"):
        status = {
            "phase": PHASE_PAUSED,
            "runner_alive": runner_alive,
            "friendly_zh": str(board_stop.get("decision_prompt_zh") or "制作已暂停。"),
        }
    elif produce_status in {
        board_produce.STATUS_QUEUED,
        board_produce.STATUS_RUNNING,
    }:
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": produce_copy or board_advance.PRODUCING_WAIT_ZH,
        }
    elif "next_stop" in actions:
        wait_copy = str((marker.get("board_stop") or {}).get("decision_prompt_zh") or "")
        next_stage = str((marker.get("board_stop") or {}).get("stage") or "")
        if (marker.get("board_stop") or {}).get("producing_wait"):
            friendly = wait_copy or board_advance.PRODUCING_WAIT_ZH
        else:
            submit = board_advance.primary_submit_label_zh(next_stage)
            friendly = (
                f"面板选择已生效。下一停点已在本页，请点「{submit}」。"
            )
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": friendly,
        }
    elif "seed_stop" in actions or seeded:
        seed_stage = str((marker.get("board_stop") or {}).get("stage") or "brief_locked")
        submit = board_advance.primary_submit_label_zh(seed_stage)
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": f"已锁定制作档。请在本页确认当前停点后点「{submit}」。",
        }
    elif recovered:
        rec_stage = str((marker.get("board_stop") or {}).get("stage") or "")
        if (marker.get("board_stop") or {}).get("producing_wait"):
            friendly = board_advance.PRODUCING_WAIT_ZH
        else:
            submit = board_advance.primary_submit_label_zh(rec_stage)
            friendly = f"方案已补写完成。下一停点已在本页，请点「{submit}」。"
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": friendly,
        }
    elif actions and not marker.get("board_stop"):
        status = {
            "phase": PHASE_IDLE,
            "runner_alive": runner_alive,
            "friendly_zh": "当前没有待确认停点。成片出现后请在本页预览并点「结束并导出项目」。",
        }
    elif actions:
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": "面板选择已生效。请留在本页查看下一停点。本机不会静默付费生视频。",
        }
    else:
        status = {
            "phase": PHASE_IDLE,
            "runner_alive": runner_alive,
            "friendly_zh": "本机 runner 空闲。点选后请留在本页等待。",
        }
    project_export.write_runner_status(project_id, status)
    return {"project_id": project_id, **status, "actions": actions}


def list_project_ids(projects_dir: Path | None = None) -> list[str]:
    root = Path(projects_dir or PROJECTS_DIR)
    if not root.is_dir():
        return []
    found: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "project.json").is_file():
            found.append(child.name)
    return found


def tick_all(
    *,
    append_decision: Callable[[str, str], Any],
    project_id: str = "",
    runner_alive: bool = True,
) -> dict[str, Any]:
    wanted = str(project_id or "").strip()
    if not wanted:
        return {
            "projects": [],
            "count": 0,
            "skipped": True,
            "reason": "no_project_id",
        }
    ids = [wanted]
    results = []
    for item in ids:
        try:
            results.append(
                tick(item, append_decision=append_decision, runner_alive=runner_alive)
            )
        except intents.UnknownProjectError as exc:
            results.append({"project_id": item, "phase": PHASE_PAUSED, "error": str(exc)})
        except project_export.ProjectExportError as exc:
            results.append(
                {
                    "project_id": item,
                    "phase": PHASE_PAUSED,
                    "friendly_zh": exc.safe_message,
                    "error": str(exc),
                }
            )
        except CheckpointValidationError as exc:
            status = {
                "phase": PHASE_PAUSED,
                "runner_alive": runner_alive,
                "friendly_zh": (
                    "该项目的阶段证据校验失败，已单独暂停；"
                    "其他项目仍可继续。请修复项目证据后再恢复。"
                ),
            }
            try:
                project_export.write_runner_status(item, status)
            except (OSError, project_export.ProjectExportError):
                pass
            results.append({"project_id": item, **status, "error": str(exc)})
    return {"projects": results, "count": len(results)}
