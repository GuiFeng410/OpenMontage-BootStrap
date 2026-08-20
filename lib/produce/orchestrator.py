"""Produce orchestrator: maybe_start / poll / sync_produce and paid/light pipelines."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

import lib.board_production_run as production_run
from lib.board_advance import write_stop_card
from lib.board_stage_artifacts import (
    StageArtifactValidationError,
    build_final_review,
    build_full_draft_pro,
    build_review_overview,
    build_sample_reel,
    validate_stage_artifact,
)
from lib.checkpoint import (
    CheckpointValidationError,
    merge_write_checkpoint,
    read_checkpoint,
)
from lib.paths import REPO_ROOT
from lib.review_interrupt import normalize_review_preset
from lib.produce.job_store import (
    _projects_root,
    OUTPUT_REL,
    ProduceJobError,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    _fail_job,
    _has_final,
    _locked_artifact_revision,
    _profile,
    _project_dir,
    _read_json,
    _refresh_overlay,
    _tier,
    _write_json,
    read_job,
    write_job,
)
from lib.produce.compose_adapter import (
    COMPOSE_WAIT_ZH,
    _aspect_ratio,
    _frame_size,
    _matching_segment_rel,
    _plan_beats,
    _sandbox_rel,
    _seg_rel,
    _start_compose,
    _wait_compose_done,
    build_compose_bundle,
)
from lib.produce.video_adapter import (
    _HEAVY_KEY_HINTS,
    _PAID_PROVIDERS,
    _resolve_video_generate,
    _video_extras,
    call_video_generate_with_retries,
)

def is_minimal(marker: dict[str, Any]) -> bool:
    return _review_preset(marker) == "minimal"

def _review_preset(marker: dict[str, Any]) -> str | None:
    return normalize_review_preset(
        _profile(marker).get("review_mode_preset") or _profile(marker).get("review_mode")
    )

def is_produce_preset(marker: dict[str, Any]) -> bool:
    return _review_preset(marker) in {"minimal", "normal"}

def _sample_rel(artifact_revision: str) -> str:
    digest = hashlib.sha256((artifact_revision or "rev").encode("utf-8")).hexdigest()[:12]
    return f"assets/video/sample_{digest}.mp4"

def sample_ready(project_id: str, *, projects_dir: Path | None = None) -> bool:
    project = _project_dir(project_id, projects_dir)
    data = _read_json(project / "artifacts" / "sample_reel.json")
    rel = str(data.get("path") or "").strip()
    if not rel:
        return False
    path = project / rel
    return path.is_file() and path.stat().st_size > 0

def sample_review_completed(project_id: str, *, projects_dir: Path | None = None) -> bool:
    checkpoint = read_checkpoint(
        _projects_root(projects_dir), project_id, "sample_review"
    )
    return isinstance(checkpoint, dict) and checkpoint.get("status") == "completed"

def draft_review_completed(project_id: str, *, projects_dir: Path | None = None) -> bool:
    checkpoint = read_checkpoint(
        _projects_root(projects_dir), project_id, "draft_review"
    )
    return isinstance(checkpoint, dict) and checkpoint.get("status") == "completed"

def _segments_ready(project_id: str, *, projects_dir: Path | None = None) -> bool:
    try:
        beats = _plan_beats(project_id, projects_dir=projects_dir)
    except ProduceJobError:
        return False
    project = _project_dir(project_id, projects_dir)
    overview = _read_json(project / "artifacts" / "review_overview.json")
    try:
        validate_stage_artifact("review_overview", overview)
    except StageArtifactValidationError:
        return False
    rows = [row for row in (overview.get("overview") or []) if isinstance(row, dict)]
    if len(rows) < len(beats):
        return False
    return all(
        _project_file_ready(project, str(row.get("output_path") or "")) for row in rows
    )

def _project_file_ready(project: Path, rel: str) -> bool:
    if not rel:
        return False
    path = project / rel
    return path.is_file() and path.stat().st_size > 0

def assets_gate_completed(project_id: str, *, projects_dir: Path | None = None) -> bool:
    root = _projects_root(projects_dir)
    checkpoint = read_checkpoint(root, project_id, "assets_gate")
    return isinstance(checkpoint, dict) and checkpoint.get("status") == "completed"

def final_ready_for_delivery(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> bool:
    if not _has_final(project_id, projects_dir=projects_dir):
        return False
    project = _project_dir(project_id, projects_dir)
    try:
        run = production_run.read_production_run(project)
    except production_run.ProductionRunError:
        return False
    if run is None:
        return True
    review = _read_json(project / "artifacts" / "final_review.json")
    try:
        validate_stage_artifact("final_review", review)
    except StageArtifactValidationError:
        return False
    artifact_revision = _locked_artifact_revision(project)
    review_metadata = review.get("metadata")
    if not isinstance(review_metadata, dict) or (
        review_metadata.get("artifact_revision") != artifact_revision
    ):
        return False
    final_result = (run.get("stage_results") or {}).get("final_compose")
    checkpoint = read_checkpoint(
        Path(projects_dir or PROJECTS_DIR),
        project_id,
        "final_compose",
    )
    checkpoint_review = (
        (checkpoint.get("artifacts") or {}).get("final_review")
        if isinstance(checkpoint, dict)
        else None
    )
    completed_final_job = any(
        item.get("stage") == "final_compose"
        and item.get("kind") == "final"
        and item.get("artifact_revision") == artifact_revision
        and item.get("status") == STATUS_DONE
        for item in (run.get("task_summaries") or [])
        if isinstance(item, dict)
    )
    return all(
        (
            review.get("status") == "pass",
            str(review.get("output_path") or "") == OUTPUT_REL,
            isinstance(final_result, dict),
            final_result.get("status") == "completed"
            if isinstance(final_result, dict)
            else False,
            "artifacts/final_review.json" in (final_result.get("evidence_refs") or [])
            if isinstance(final_result, dict)
            else False,
            isinstance(checkpoint, dict),
            checkpoint.get("status") == "completed"
            if isinstance(checkpoint, dict)
            else False,
            isinstance(checkpoint_review, dict),
            checkpoint_review.get("status") == "pass"
            if isinstance(checkpoint_review, dict)
            else False,
            str(checkpoint_review.get("output_path") or "") == OUTPUT_REL
            if isinstance(checkpoint_review, dict)
            else False,
            (
                checkpoint_review.get("metadata") or {}
            ).get("artifact_revision")
            == artifact_revision
            if isinstance(checkpoint_review, dict)
            else False,
            completed_final_job,
        )
    )

def _provider_id(profile: dict[str, Any], brief: dict[str, Any]) -> str:
    raw = " ".join(
        [
            str(profile.get("video_channel") or ""),
            str(profile.get("provider") or ""),
            str(profile.get("video_model") or profile.get("model") or ""),
            str(brief.get("video_channel") or ""),
            str(brief.get("provider") or ""),
        ]
    ).lower()
    for name in _HEAVY_KEY_HINTS:
        if name in raw:
            return name
    return ""

def _present_key_names() -> set[str]:
    names: set[str] = set()
    try:
        from openmontage.mcp.bootstrap.install_state import scan_stock_keys, scan_video_keys

        video = scan_video_keys(repo_root=REPO_ROOT, environ=dict(os.environ))
        stock = scan_stock_keys(repo_root=REPO_ROOT, environ=dict(os.environ))
        names.update(video.get("video_key_names_present") or [])
        names.update(stock.get("stock_key_names_present") or [])
    except Exception:
        pass
    for key, value in os.environ.items():
        if value and str(value).strip():
            names.add(key)
    return names

def key_gate(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Return a paused job payload when locked tier cannot run. None = compose OK."""
    profile = _profile(marker)
    tier = _tier(profile)
    if tier == "light":
        return None
    present_fn = _present_key_names
    facade = sys.modules.get("lib.board_produce")
    if facade is not None and getattr(facade, "_present_key_names", None) is not None:
        present_fn = facade._present_key_names
    present = present_fn()
    if tier == "medium":
        source = str(profile.get("medium_source") or "user_assets").strip().lower()
        if source != "stock":
            return None
        if "PEXELS_API_KEY" in present or "PIXABAY_API_KEY" in present:
            return {
                "status": STATUS_PAUSED,
                "engine": "stock",
                "tier": tier,
                "code": "stock_not_auto",
                "friendly_zh": (
                    "已锁定中度 Stock，不降为轻度。"
                    "本页不自动下载素材；请刷新可用性后按锁定来源继续。"
                ),
            }
        return {
            "status": STATUS_PAUSED,
            "engine": "stock",
            "tier": tier,
            "code": "stock_key_missing",
            "friendly_zh": (
                "已锁定中度 Stock，但本机没有 Stock Key，不能改走轻度。"
                "请在本页刷新可用性，或回方案改档。"
            ),
        }
    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    hints = _HEAVY_KEY_HINTS.get(provider) or ()
    has_key = any(name in present for name in hints) if hints else bool(
        present.intersection(
            {name for group in _HEAVY_KEY_HINTS.values() for name in group}
        )
    )
    if not has_key:
        return {
            "status": STATUS_PAUSED,
            "engine": "paid_video",
            "tier": tier,
            "code": "video_key_missing",
            "friendly_zh": (
                "已锁定重度，不降为轻度。本机未检测到对应视频 Key。"
                "请在本页刷新可用性后再试。"
            ),
        }
    if provider not in _PAID_PROVIDERS:
        locked = " / ".join(
            part
            for part in (
                str(profile.get("video_channel") or "").strip(),
                str(profile.get("video_model") or profile.get("model") or "").strip(),
                provider,
            )
            if part
        )
        supported = "Agnes、Kling、Seedance、Sora、Veo、MiniMax、Runway、混元、Pixverse"
        return {
            "status": STATUS_PAUSED,
            "engine": "paid_video",
            "tier": tier,
            "code": "video_channel_missing",
            "friendly_zh": (
                f"已锁定重度{('（' + locked + '）') if locked else ''}。"
                "看板本机分段目前不能走该渠道，也不会改成轻度或其它模型。"
                f"请回方案改成支持的渠道后再点开始出片：{supported}。"
            ),
        }
    return None

def _record_completed_stage(
    project_id: str,
    stage: str,
    artifact_name: str,
    artifact: dict[str, Any],
    *,
    projects_dir: Path | None,
) -> None:
    root = _projects_root(projects_dir)
    merge_write_checkpoint(
        root,
        project_id,
        stage,
        "completed",
        {artifact_name: artifact},
        pipeline_type="bootstrap-commercial",
        human_approval_required=False,
        human_approved=False,
        metadata_patch={"needs_user_decision": False, "auto_completed": True},
    )
    project = _project_dir(project_id, projects_dir)
    run = production_run.read_production_run(project)
    if run is None:
        return
    updated = production_run.record_stage_result(
        run,
        stage,
        "completed",
        checkpoint_refs=[f"checkpoint_{stage}.json"],
        evidence_refs=[f"artifacts/{artifact_name}.json"],
        human_approved=False,
    )
    production_run.write_production_run(project, updated)

def _materialize_review_overview(
    project_id: str,
    beats: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
    artifact_revision: str,
    projects_dir: Path | None,
    completed: bool,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    rows: list[dict[str, Any]] = []
    for row in beats:
        beat = str(row["beat"])
        rel = _matching_segment_rel(project, beat, artifact_revision) or _seg_rel(
            beat,
            artifact_revision,
        )
        path = project / rel
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        rows.append(
            {
                "beat": beat,
                "output_path": rel,
                "status": "completed",
                "artifact_revision": artifact_revision,
                "provider": provider,
                "model": model,
            }
        )
    if completed and len(rows) != len(beats):
        raise ProduceJobError(
            "分段证据不完整，不能完成 segment_build。",
            code="segment_evidence_incomplete",
        )
    artifact = build_review_overview(
        rows,
        batches=[],
        extra={
            "artifact_revision": artifact_revision,
            "provider": provider,
            "model": model,
            "status": "completed" if completed else "in_progress",
        },
    )
    _write_json(project / "artifacts" / "review_overview.json", artifact)
    if completed:
        _record_completed_stage(
            project_id,
            "segment_build",
            "review_overview",
            artifact,
            projects_dir=projects_dir,
        )
    return artifact

def _materialize_final_evidence(
    project_id: str,
    *,
    projects_dir: Path | None,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    final_path = project / OUTPUT_REL
    if not final_path.is_file() or final_path.stat().st_size <= 0:
        raise ProduceJobError("成片文件缺失，不能完成 final_compose。", code="final_missing")
    run = production_run.read_production_run(project)
    if run is None:
        raise ProduceJobError(
            "缺少生产运行记录，不能为新任务补写终稿证据。",
            code="final_run_missing",
        )
    artifact_revision = _locked_artifact_revision(project)
    current_job = production_run.read_produce_job(
        project,
        run_revision=run["run_revision"],
    )
    if not isinstance(current_job, dict) or any(
        (
            current_job.get("stage") != "final_compose",
            current_job.get("kind") != "final",
            current_job.get("artifact_revision") != artifact_revision,
        )
    ):
        raise ProduceJobError(
            "终稿任务与当前输入版本不一致，旧成片未被重新认领。",
            code="final_revision_stale",
        )
    existing = _read_json(project / "artifacts" / "final_review.json")
    if existing:
        try:
            validate_stage_artifact("final_review", existing)
        except StageArtifactValidationError as exc:
            raise ProduceJobError(
                f"已有终稿证据无效：{exc}",
                code="final_review_invalid",
            ) from exc
        existing_metadata = existing.get("metadata")
        existing_revision = (
            existing_metadata.get("artifact_revision")
            if isinstance(existing_metadata, dict)
            else None
        )
        if existing_revision != artifact_revision:
            raise ProduceJobError(
                "已有终稿证据属于旧输入版本，未开放交付。",
                code="final_revision_stale",
            )
    final_result = (run.get("stage_results") or {}).get("final_compose") if run else {}
    checkpoint = read_checkpoint(
        _projects_root(projects_dir),
        project_id,
        "final_compose",
    )
    if (
        existing.get("status") == "pass"
        and existing.get("output_path") == OUTPUT_REL
        and isinstance(final_result, dict)
        and final_result.get("status") == "completed"
        and isinstance(checkpoint, dict)
        and checkpoint.get("status") == "completed"
    ):
        return existing
    marker = _read_json(project / "project.json")
    profile = _profile(marker)
    artifact = build_final_review(
        OUTPUT_REL,
        status="pass",
        checks={
            "technical_probe": {
                "file_exists": True,
                "non_empty": True,
                "size_bytes": final_path.stat().st_size,
                "verification_level": "file_presence",
            }
        },
        metadata={
            "artifact_revision": artifact_revision,
            "provider": str(profile.get("provider") or profile.get("video_channel") or ""),
            "model": str(profile.get("video_model") or profile.get("model") or ""),
        },
    )
    _write_json(project / "artifacts" / "final_review.json", artifact)
    _record_completed_stage(
        project_id,
        "final_compose",
        "final_review",
        artifact,
        projects_dir=projects_dir,
    )
    return artifact

def _wait_copy(project_id: str, marker: dict[str, Any], *, projects_dir: Path | None) -> str:
    from lib.board_advance import producing_wait_copy_zh

    return producing_wait_copy_zh(marker, project_id=project_id, projects_dir=projects_dir)

def _promote_sample_to_first_segment(
    project_id: str,
    beats: list[dict[str, Any]],
    *,
    artifact_revision: str,
    provider: str,
    model: str,
    projects_dir: Path | None = None,
) -> None:
    if not beats:
        return
    project = _project_dir(project_id, projects_dir)
    sample_rel = _sample_rel(artifact_revision)
    source = project / sample_rel
    if not source.is_file() or source.stat().st_size <= 0:
        return
    dest_rel = _seg_rel(str(beats[0]["beat"]), artifact_revision)
    dest = project / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file() or dest.stat().st_size <= 0:
        shutil.copy2(source, dest)
    _materialize_review_overview(
        project_id,
        beats[:1],
        provider=provider,
        model=model,
        artifact_revision=artifact_revision,
        projects_dir=projects_dir,
        completed=False,
    )

def _run_paid_sample(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
) -> str:
    profile = _profile(marker)
    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    model = str(profile.get("video_model") or profile.get("model") or "").strip()
    beats = _plan_beats(project_id, projects_dir=projects_dir)
    if not beats:
        raise ProduceJobError("缺少 video_plan 分段，无法生成试片。", code="no_plan")
    row = beats[0]
    beat = str(row["beat"])
    width, height = _frame_size(profile)
    aspect = _aspect_ratio(width, height)
    wait_copy = _wait_copy(project_id, marker, projects_dir=projects_dir)
    generate = _resolve_video_generate(provider, video_generate)
    project = _project_dir(project_id, projects_dir)
    artifact_revision = _locked_artifact_revision(project)
    dest_rel = _sample_rel(artifact_revision)
    if dest_rel == _seg_rel(beat, artifact_revision):
        raise ProduceJobError("试片路径不能与分段路径相同。", code="sample_path_collision")
    dest = project / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    still_abs = str((project / str(row["still"])).resolve())
    extras = _video_extras(provider, still_abs, float(row["span"]), aspect)
    if model:
        extras["model"] = model
    friendly = f"正在生成试片。{wait_copy}"
    write_job(
        project_id,
        {
            "stage": "sample_review",
            "kind": "sample",
            "artifact_revision": artifact_revision,
            "batch_id": beat,
            "beat_ids": [beat],
            "expected_outputs": [dest_rel, "artifacts/sample_reel.json"],
            "status": STATUS_RUNNING,
            "engine": "paid_video",
            "tier": "heavy",
            "provider": provider,
            "model": model,
            "beat": beat,
            "friendly_zh": friendly,
        },
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, friendly, projects_dir=projects_dir)
    call_video_generate_with_retries(
        generate,
        provider,
        str(row["prompt"]),
        _sandbox_rel(project_id, dest_rel),
        json.dumps(extras, ensure_ascii=False),
        True,
        True,
        dest=dest,
    )
    if not dest.is_file() or dest.stat().st_size <= 0:
        raise ProduceJobError("试片生成结束但没有视频文件，未换渠道。", code="sample_missing")
    reel = build_sample_reel(
        dest_rel,
        [beat],
        duration_seconds=float(row["span"]),
        status="pending",
    )
    _write_json(project / "artifacts" / "sample_reel.json", reel)
    write_stop_card(
        project_id,
        "sample_review",
        pipeline_type="bootstrap-commercial",
        projects_dir=projects_dir,
    )
    return dest_rel

def _write_draft_from_segments(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> str:
    project = _project_dir(project_id, projects_dir)
    overview = _read_json(project / "artifacts" / "review_overview.json")
    rows = [row for row in (overview.get("overview") or []) if isinstance(row, dict)]
    path = str((rows[0] or {}).get("output_path") or "").strip() if rows else ""
    if not path:
        raise ProduceJobError("分段已生成但没有初稿可看的视频。", code="draft_missing")
    draft = build_full_draft_pro(path, status="pending")
    _write_json(project / "artifacts" / "full_draft_pro.json", draft)
    write_stop_card(
        project_id,
        "draft_review",
        pipeline_type="bootstrap-commercial",
        projects_dir=projects_dir,
    )
    return path

def _run_paid_pipeline(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
    compose: bool = True,
) -> None:
    profile = _profile(marker)
    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    model = str(profile.get("video_model") or profile.get("model") or "").strip()
    beats = _plan_beats(project_id, projects_dir=projects_dir)
    width, height = _frame_size(profile)
    aspect = _aspect_ratio(width, height)
    wait_copy = _wait_copy(project_id, marker, projects_dir=projects_dir)
    generate = _resolve_video_generate(provider, video_generate)
    project = _project_dir(project_id, projects_dir)
    artifact_revision = _locked_artifact_revision(project)
    _promote_sample_to_first_segment(
        project_id,
        beats,
        artifact_revision=artifact_revision,
        provider=provider,
        model=model,
        projects_dir=projects_dir,
    )
    total = len(beats)
    for index, row in enumerate(beats, start=1):
        beat = str(row["beat"])
        matched_rel = _matching_segment_rel(project, beat, artifact_revision)
        if matched_rel:
            write_job(
                project_id,
                {
                    "stage": "segment_build",
                    "kind": "segment",
                    "artifact_revision": artifact_revision,
                    "batch_id": beat,
                    "beat_ids": [beat],
                    "expected_outputs": [
                        matched_rel,
                        "artifacts/review_overview.json",
                    ],
                    "status": STATUS_DONE,
                    "engine": "paid_video",
                    "tier": "heavy",
                    "provider": provider,
                    "model": model,
                    "beat": beat,
                    "reused": True,
                    "friendly_zh": f"第 {index}/{total} 段复用当前版本证据。",
                },
                projects_dir=projects_dir,
            )
            continue
        dest_rel = _seg_rel(beat, artifact_revision)
        dest = project / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        still_abs = str((project / str(row["still"])).resolve())
        extras = _video_extras(provider, still_abs, float(row["span"]), aspect)
        if model:
            extras["model"] = model
        friendly = f"第 {index}/{total} 段正在生成。{wait_copy}"
        write_job(
            project_id,
            {
                "stage": "segment_build",
                "kind": "segment",
                "artifact_revision": artifact_revision,
                "batch_id": beat,
                "beat_ids": [beat],
                "expected_outputs": [
                    dest_rel,
                    "artifacts/review_overview.json",
                ],
                "status": STATUS_RUNNING,
                "engine": "paid_video",
                "tier": "heavy",
                "provider": provider,
                "model": model,
                "beat": beat,
                "friendly_zh": friendly,
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(project_id, friendly, projects_dir=projects_dir)
        result = call_video_generate_with_retries(
            generate,
            provider,
            str(row["prompt"]),
            _sandbox_rel(project_id, dest_rel),
            json.dumps(extras, ensure_ascii=False),
            True,
            True,
            dest=dest,
        )
        if not dest.is_file() or dest.stat().st_size <= 0:
            raise ProduceJobError(
                f"分段 {row['beat']} 生成结束但没有视频文件，未换渠道。",
                code="segment_missing",
            )
        _materialize_review_overview(
            project_id,
            beats,
            provider=provider,
            model=model,
            artifact_revision=artifact_revision,
            projects_dir=projects_dir,
            completed=False,
        )
        cost_snapshot = {}
        if isinstance(result, dict):
            cost_snapshot = {
                key: result[key]
                for key in ("estimated_cost_usd", "cost_usd")
                if result.get(key) is not None
            }
        write_job(
            project_id,
            {
                "stage": "segment_build",
                "kind": "segment",
                "artifact_revision": artifact_revision,
                "batch_id": beat,
                "beat_ids": [beat],
                "expected_outputs": [
                    dest_rel,
                    "artifacts/review_overview.json",
                ],
                "status": STATUS_DONE,
                "engine": "paid_video",
                "tier": "heavy",
                "provider": provider,
                "model": model,
                "beat": beat,
                "cost_snapshot": cost_snapshot,
                "friendly_zh": f"第 {index}/{total} 段已生成。",
            },
            projects_dir=projects_dir,
        )
    _materialize_review_overview(
        project_id,
        beats,
        provider=provider,
        model=model,
        artifact_revision=artifact_revision,
        projects_dir=projects_dir,
        completed=True,
    )
    if not compose:
        return
    launched = _start_compose(
        project_id,
        marker,
        projects_dir=projects_dir,
        compose_start=compose_start,
        engine="paid_video",
        wait_copy=wait_copy,
    )
    if launched.get("status") == STATUS_FAILED:
        raise ProduceJobError(
            str((launched.get("job") or {}).get("friendly_zh") or "合成失败。"),
            code=str((launched.get("job") or {}).get("code") or "compose_start_failed"),
        )
    started = launched.get("started") if isinstance(launched.get("started"), dict) else {}
    _wait_compose_done(
        project_id,
        started,
        projects_dir=projects_dir,
        job_status=job_status,
    )
    _materialize_final_evidence(project_id, projects_dir=projects_dir)

def maybe_start(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    paid_inline: bool = False,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if _has_final(project_id, projects_dir=projects_dir):
        project = _project_dir(project_id, projects_dir)
        try:
            if production_run.read_production_run(project) is not None:
                _materialize_final_evidence(project_id, projects_dir=projects_dir)
        except (
            production_run.ProductionRunError,
            ProduceJobError,
            CheckpointValidationError,
            OSError,
        ) as exc:
            return _fail_job(
                project_id,
                projects_dir=projects_dir,
                engine="compose",
                tier=_tier(_profile(marker)),
                code="final_evidence_failed",
                friendly_zh=f"成片存在，但终稿证据写入失败，未开放交付：{exc}",
            )
        return {"action": "", "status": STATUS_DONE, "skipped": True}
    if not is_produce_preset(marker) or not assets_gate_completed(
        project_id, projects_dir=projects_dir
    ):
        return {"action": "", "status": STATUS_SKIPPED, "skipped": True}
    existing = read_job(project_id, projects_dir=projects_dir) or {}
    status = str(existing.get("status") or "")
    if status in {STATUS_QUEUED, STATUS_RUNNING, STATUS_FAILED}:
        return {"action": "", "status": status, "job": existing, "skipped": True}
    if status == STATUS_PAUSED and str(existing.get("code") or "") in {
        "orphaned",
        "run_state_invalid",
    }:
        return {"action": "", "status": status, "job": existing, "skipped": True}

    gated = key_gate(project_id, marker, projects_dir=projects_dir)
    if status == STATUS_PAUSED and gated is not None:
        return {"action": "", "status": STATUS_PAUSED, "job": existing, "skipped": True}
    if gated is not None:
        job = write_job(project_id, gated, projects_dir=projects_dir)
        _refresh_overlay(
            project_id,
            str(gated.get("friendly_zh") or ""),
            projects_dir=projects_dir,
            paused=True,
        )
        return {"action": "produce_paused", "status": STATUS_PAUSED, "job": job}

    profile = _profile(marker)
    tier = _tier(profile)
    wait_copy = _wait_copy(project_id, marker, projects_dir=projects_dir)
    if tier != "heavy":
        if _review_preset(marker) == "normal":
            return {"action": "", "status": STATUS_SKIPPED, "skipped": True}
        return _start_compose(
            project_id,
            marker,
            projects_dir=projects_dir,
            compose_start=compose_start,
            engine="compose",
            wait_copy=COMPOSE_WAIT_ZH,
        )

    sample_only = False
    segments_only = False
    if _review_preset(marker) == "normal":
        if not sample_ready(project_id, projects_dir=projects_dir):
            sample_only = True
        elif not sample_review_completed(project_id, projects_dir=projects_dir):
            return {"action": "", "status": STATUS_SKIPPED, "skipped": True}
        elif not draft_review_completed(project_id, projects_dir=projects_dir):
            if _segments_ready(project_id, projects_dir=projects_dir):
                return {"action": "", "status": STATUS_SKIPPED, "skipped": True}
            segments_only = True

    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    artifact_revision = _locked_artifact_revision(
        _project_dir(project_id, projects_dir)
    )
    sample_rel = _sample_rel(artifact_revision)
    if sample_only:
        reservation = {
            "stage": "sample_review",
            "kind": "sample",
            "output_path": sample_rel,
            "expected_outputs": [sample_rel, "artifacts/sample_reel.json"],
            "friendly_zh": "正在生成试片，请留在本页。",
        }
    elif segments_only:
        reservation = {
            "stage": "draft_review",
            "kind": "draft",
            "output_path": "artifacts/full_draft_pro.json",
            "expected_outputs": [
                "artifacts/review_overview.json",
                "artifacts/full_draft_pro.json",
            ],
            "friendly_zh": "正在生成其余分段，请留在本页。",
        }
    else:
        reservation = {
            "stage": "final_compose",
            "kind": "final",
            "output_path": OUTPUT_REL,
            "expected_outputs": [OUTPUT_REL, "artifacts/final_review.json"],
            "friendly_zh": wait_copy,
        }
    reservation = {
        "artifact_revision": artifact_revision,
        "batch_id": "",
        "beat_ids": [],
        "status": STATUS_QUEUED,
        "engine": "paid_video",
        "tier": "heavy",
        "provider": provider,
        "job_id": "",
        **reservation,
    }
    try:
        write_job(project_id, reservation, projects_dir=projects_dir)
    except (production_run.ProductionRunError, OSError) as exc:
        message = "生产任务无法安全登记，未调用视频模型。请先修复生产状态文件。"
        _refresh_overlay(project_id, message, projects_dir=projects_dir, paused=True)
        return {
            "action": "produce_paused",
            "status": STATUS_PAUSED,
            "job": {
                "status": STATUS_PAUSED,
                "code": "run_state_invalid",
                "friendly_zh": message,
                "error": str(exc),
            },
        }

    def worker(_job_id: str = "") -> None:
        try:
            if sample_only:
                dest_rel = _run_paid_sample(
                    project_id,
                    marker,
                    projects_dir=projects_dir,
                    video_generate=video_generate,
                )
                write_job(
                    project_id,
                    {
                        "status": STATUS_DONE,
                        "engine": "paid_video",
                        "tier": "heavy",
                        "provider": provider,
                        "kind": "sample",
                        "output_path": dest_rel,
                        "friendly_zh": "试片已就绪，请确认后再继续生成其余分段。",
                    },
                    projects_dir=projects_dir,
                )
                return
            if segments_only:
                _run_paid_pipeline(
                    project_id,
                    marker,
                    projects_dir=projects_dir,
                    compose_start=compose_start,
                    video_generate=video_generate,
                    job_status=job_status,
                    compose=False,
                )
                dest_rel = _write_draft_from_segments(
                    project_id, projects_dir=projects_dir
                )
                write_job(
                    project_id,
                    {
                        "status": STATUS_DONE,
                        "engine": "paid_video",
                        "tier": "heavy",
                        "provider": provider,
                        "kind": "draft",
                        "output_path": dest_rel,
                        "friendly_zh": "分段已齐，请确认初稿后再合成终稿。",
                    },
                    projects_dir=projects_dir,
                )
                return
            _run_paid_pipeline(
                project_id,
                marker,
                projects_dir=projects_dir,
                compose_start=compose_start,
                video_generate=video_generate,
                job_status=job_status,
            )
            if _has_final(project_id, projects_dir=projects_dir):
                write_job(
                    project_id,
                    {
                        "status": STATUS_DONE,
                        "engine": "paid_video",
                        "tier": "heavy",
                        "provider": provider,
                        "friendly_zh": "成片已就绪，请在本页预览并导出。",
                    },
                    projects_dir=projects_dir,
                )
        except ProduceJobError as exc:
            extra = dict(exc.extra or {})
            _fail_job(
                project_id,
                projects_dir=projects_dir,
                engine="paid_video",
                tier="heavy",
                code=exc.code,
                friendly_zh=exc.safe_message,
                extra=extra or None,
            )
            raise
        except Exception as exc:
            _fail_job(
                project_id,
                projects_dir=projects_dir,
                engine="paid_video",
                tier="heavy",
                code="paid_pipeline_failed",
                friendly_zh=f"分段生成失败，未换渠道：{exc}",
                extra={"error": str(exc)},
            )
            raise

    if paid_inline:
        try:
            worker()
        except Exception:
            job = read_job(project_id, projects_dir=projects_dir) or {}
            return {
                "action": "produce_failed",
                "status": str(job.get("status") or STATUS_FAILED),
                "job": job,
            }
        job = read_job(project_id, projects_dir=projects_dir) or {}
        return {
            "action": "produce_start",
            "status": str(job.get("status") or STATUS_QUEUED),
            "job": job,
        }

    from openmontage.mcp.common.jobs import create_job, start_background

    try:
        media_job = create_job("board_paid_video", meta={"project_id": project_id})
    except Exception as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine="paid_video",
            tier="heavy",
            code="background_job_start_failed",
            friendly_zh=f"本机无法登记后台任务，未调用视频模型：{exc}",
        )
    job = write_job(
        project_id,
        {
            "status": STATUS_QUEUED,
            "engine": "paid_video",
            "tier": "heavy",
            "provider": provider,
            "job_id": str(media_job.get("job_id") or ""),
            "friendly_zh": wait_copy,
        },
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, wait_copy, projects_dir=projects_dir)
    try:
        start_background(str(media_job["job_id"]), worker)
    except Exception as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine="paid_video",
            tier="heavy",
            code="background_job_start_failed",
            friendly_zh=f"本机无法启动后台任务，未调用视频模型：{exc}",
        )
    return {"action": "produce_start", "status": STATUS_QUEUED, "job": job}

def _is_in_process_paid_job(job: dict[str, Any]) -> bool:
    engine = str(job.get("engine") or "")
    status = str(job.get("status") or "")
    return engine == "paid_video" and status in {STATUS_QUEUED, STATUS_RUNNING}

def _reconcile_missing_background(
    project_id: str,
    job: dict[str, Any],
    *,
    projects_dir: Path | None,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    recovered = production_run.reconcile_orphaned_job(
        job,
        project,
        background_job_exists=False,
    )
    written = write_job(project_id, recovered, projects_dir=projects_dir)
    status = str(written.get("status") or "")
    if status == STATUS_DONE:
        return {"action": "produce_done", "status": status, "job": written}
    friendly = (
        "原后台任务记录已失联，证据尚不完整。已暂停且不会自动重试或重复收费。"
    )
    written = write_job(
        project_id,
        {**written, "friendly_zh": friendly},
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, friendly, projects_dir=projects_dir, paused=True)
    return {"action": "produce_paused", "status": STATUS_PAUSED, "job": written}

def _finalize_completed_job(
    project_id: str,
    job: dict[str, Any],
    *,
    projects_dir: Path | None,
) -> dict[str, Any]:
    try:
        _materialize_final_evidence(project_id, projects_dir=projects_dir)
    except (
        production_run.ProductionRunError,
        ProduceJobError,
        CheckpointValidationError,
        OSError,
    ) as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine=str(job.get("engine") or "compose"),
            tier=str(job.get("tier") or "light"),
            code="final_evidence_failed",
            friendly_zh=f"成片存在，但终稿证据写入失败，未开放交付：{exc}",
        )
    written = write_job(
        project_id,
        {
            **job,
            "status": STATUS_DONE,
            "friendly_zh": "成片已就绪，请在本页预览并导出。",
        },
        projects_dir=projects_dir,
    )
    return {"action": "produce_done", "status": STATUS_DONE, "job": written}

def poll(
    project_id: str,
    *,
    projects_dir: Path | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    job = read_job(project_id, projects_dir=projects_dir)
    if not job:
        return {"action": "", "status": ""}
    if _has_final(project_id, projects_dir=projects_dir):
        return _finalize_completed_job(
            project_id,
            job,
            projects_dir=projects_dir,
        )
    if job.get("status") in {STATUS_PAUSED, STATUS_FAILED, STATUS_DONE}:
        return {"action": "", "status": str(job.get("status") or ""), "job": job}
    compose_id = str(job.get("job_id") or "")
    if not compose_id:
        if _is_in_process_paid_job(job):
            return {
                "action": "",
                "status": str(job.get("status") or ""),
                "job": job,
            }
        return _reconcile_missing_background(
            project_id,
            job,
            projects_dir=projects_dir,
        )
    reader = job_status
    if reader is None:
        from openmontage.mcp.media.tools import job_status as reader
    try:
        remote = reader(compose_id)
    except Exception as exc:
        error_code = str(getattr(exc, "code", "") or "").lower()
        error_text = str(exc).lower()
        if error_code == "not_found" or "job not found" in error_text:
            return _reconcile_missing_background(
                project_id,
                job,
                projects_dir=projects_dir,
            )
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "compose_status_failed",
                "friendly_zh": f"无法读取合成进度：{exc}",
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(
            project_id,
            job["friendly_zh"],
            projects_dir=projects_dir,
            paused=True,
        )
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    if not isinstance(remote, dict):
        remote = {}
    remote_status = str(remote.get("status") or "")
    if remote_status in {"failed", "error"}:
        friendly = str(remote.get("error") or "合成失败，请留在本页重试。")
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "compose_failed",
                "friendly_zh": friendly,
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(project_id, friendly, projects_dir=projects_dir, paused=True)
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    if remote_status in {"completed", "done", "succeeded"}:
        if _has_final(project_id, projects_dir=projects_dir):
            return _finalize_completed_job(
                project_id,
                projects_dir=projects_dir,
                job=job,
            )
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "final_missing",
                "friendly_zh": "合成报告完成，但还没有成片文件。请留在本页重试。",
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(
            project_id, job["friendly_zh"], projects_dir=projects_dir, paused=True
        )
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    progress = remote.get("progress")
    engine = str(job.get("engine") or "compose")
    if engine == "paid_video":
        marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
        friendly = str(job.get("friendly_zh") or "") or _wait_copy(
            project_id, marker, projects_dir=projects_dir
        )
    else:
        friendly = "本机正在合成成片，大约 1–3 分钟。请留在本页。"
        if progress not in (None, ""):
            try:
                friendly = (
                    f"本机正在合成成片（{int(float(progress) * 100)}%），"
                    "大约还需要一两分钟。请留在本页。"
                )
            except (TypeError, ValueError):
                pass
    job = write_job(
        project_id,
        {**job, "status": STATUS_RUNNING, "friendly_zh": friendly},
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, friendly, projects_dir=projects_dir)
    return {"action": "produce_poll", "status": STATUS_RUNNING, "job": job}

def sync_produce(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    paid_inline: bool = False,
) -> dict[str, Any]:
    started = maybe_start(
        project_id,
        marker,
        projects_dir=projects_dir,
        compose_start=compose_start,
        video_generate=video_generate,
        paid_inline=paid_inline,
        job_status=job_status,
    )
    if started.get("action"):
        return started
    return poll(project_id, projects_dir=projects_dir, job_status=job_status)
