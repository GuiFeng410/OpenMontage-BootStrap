"""C0A contracts for staged production run persistence and recovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import lib.board_production_run as production_run

NOW = "2026-08-19T08:00:00+00:00"


def _project(tmp_path: Path, *, review: str = "normal", tier: str = "heavy") -> Path:
    project = tmp_path / "projects" / "shop-demo"
    (project / "artifacts").mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "project_id": "shop-demo",
                "pipeline_type": "bootstrap-commercial",
                "production_profile": {
                    "review_mode_preset": review,
                    "production_tier": tier,
                    "provider": "agnes",
                    "video_model": "agnes-v1",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project


def _job(**overrides) -> dict:
    values = {
        "project_id": "shop-demo",
        "run_revision": "3",
        "stage": "sample_review",
        "kind": "sample",
        "artifact_revision": "sample-r2",
        "authorization_revision": "auth-r4",
        "provider": "agnes",
        "model": "agnes-v1",
        "batch_id": "batch-01",
        "beat_ids": ["beat_01"],
        "expected_outputs": [
            "assets/video/sample_r2.mp4",
            "artifacts/sample_reel.json",
        ],
        "now": NOW,
    }
    values.update(overrides)
    return production_run.build_produce_job(**values)


def test_stable_job_key_is_deterministic_and_revision_sensitive() -> None:
    first = production_run.stable_job_key(
        "shop-demo", "3", "sample_review", "sample", "sample-r2", "batch-01"
    )
    assert first == production_run.stable_job_key(
        "shop-demo", "3", "sample_review", "sample", "sample-r2", "batch-01"
    )
    assert first != production_run.stable_job_key(
        "shop-demo", "3", "sample_review", "sample", "sample-r3", "batch-01"
    )
    assert first != production_run.stable_job_key(
        "shop-demo", "4", "sample_review", "sample", "sample-r2", "batch-01"
    )


def test_build_v2_job_contains_frozen_projection_fields() -> None:
    job = _job(cost_snapshot={"estimated_usd": 0.4})
    assert job["version"] == "2.0"
    assert job["stage"] == "sample_review"
    assert job["kind"] == "sample"
    assert job["artifact_revision"] == "sample-r2"
    assert job["authorization_revision"] == "auth-r4"
    assert job["attempt"] == 1
    assert job["batch_id"] == "batch-01"
    assert job["beat_ids"] == ["beat_01"]
    assert job["cost_snapshot"] == {"estimated_usd": 0.4}
    assert job["created_at"] == NOW
    assert job["updated_at"] == NOW


def test_normalize_legacy_v1_job_preserves_ui_fields_and_infers_final() -> None:
    legacy = {
        "version": "1.0",
        "project_id": "shop-demo",
        "status": "running",
        "engine": "paid_video",
        "provider": "agnes",
        "job_id": "legacy-job-7",
        "output_path": "renders/final.mp4",
        "friendly_zh": "正在制作",
        "updated_at": NOW,
    }
    normalized = production_run.normalize_produce_job(
        legacy, run_revision="2", now=NOW
    )
    assert normalized["version"] == "2.0"
    assert normalized["migrated_from_version"] == "1.0"
    assert normalized["stage"] == "final_compose"
    assert normalized["kind"] == "final"
    assert normalized["artifact_revision"] == "legacy-v1"
    assert normalized["authorization_revision"] is None
    assert normalized["expected_outputs"] == ["renders/final.mp4"]
    assert normalized["friendly_zh"] == "正在制作"
    assert normalized["job_id"] == "legacy-job-7"


def test_normalize_v2_rejects_wrong_supplied_job_key() -> None:
    job = _job()
    job["job_key"] = "job_wrong"
    with pytest.raises(production_run.ProductionRunConflictError, match="job_key"):
        production_run.normalize_produce_job(job, now=NOW)


def test_v2_empty_beat_ids_are_not_backfilled_from_legacy_beat_field() -> None:
    job = _job(beat_ids=[])
    updated = production_run.normalize_produce_job(
        {**job, "beat": "beat_01", "status": "running"},
        now=NOW,
    )
    assert updated["beat_ids"] == []
    assert updated["job_key"] == job["job_key"]


def test_job_paths_stay_project_relative() -> None:
    with pytest.raises(production_run.ProductionRunError, match="project-relative"):
        _job(expected_outputs=["../outside.mp4"])
    with pytest.raises(production_run.ProductionRunError, match="project-relative"):
        _job(expected_outputs=["C:/outside.mp4"])


def test_new_v2_job_requires_canonical_artifact_in_expected_outputs() -> None:
    with pytest.raises(
        production_run.ProductionRunError, match="canonical artifacts"
    ):
        _job(expected_outputs=["assets/video/sample_r2.mp4"])


def test_job_atomic_write_round_trip_and_v1_compatibility(tmp_path: Path) -> None:
    project = _project(tmp_path)
    legacy_path = project / "artifacts" / "produce_job.json"
    legacy_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "shop-demo",
                "status": "queued",
                "job_id": "j1",
                "output_path": "renders/final.mp4",
            }
        ),
        encoding="utf-8",
    )
    read = production_run.read_produce_job(project, run_revision="9")
    assert read is not None
    assert read["run_revision"] == "9"
    written = production_run.write_produce_job(project, read)
    assert written["version"] == "2.0"
    assert json.loads(legacy_path.read_text(encoding="utf-8"))["version"] == "2.0"


def test_new_run_only_stores_references_and_not_required_reason() -> None:
    run = production_run.new_production_run(
        project_id="shop-demo",
        run_revision="3",
        review_mode_preset="minimal",
        production_tier="heavy",
        locked_provider="agnes",
        locked_model="agnes-v1",
        now=NOW,
    )
    updated = production_run.mark_stage_not_required(
        run, "sample_review", "minimal_review_policy", now=NOW
    )
    assert updated["stage_results"]["sample_review"] == {
        "status": "not_required",
        "reason": "minimal_review_policy",
        "checkpoint_refs": [],
        "evidence_refs": [],
    }
    assert "artifact" not in updated["stage_results"]["sample_review"]
    assert run["stage_results"] == {}


def test_record_stage_result_stores_references_without_artifact_payload() -> None:
    run = production_run.new_production_run(
        project_id="shop-demo", review_mode_preset="minimal", now=NOW
    )
    updated = production_run.record_stage_result(
        run,
        "segment_build",
        "completed",
        checkpoint_refs=["checkpoint_segment_build.json"],
        evidence_refs=["artifacts/review_overview.json"],
        human_approved=False,
        now=NOW,
    )
    assert updated["stage_results"]["segment_build"] == {
        "status": "completed",
        "checkpoint_refs": ["checkpoint_segment_build.json"],
        "evidence_refs": ["artifacts/review_overview.json"],
        "human_approved": False,
    }
    assert "artifact" not in updated["stage_results"]["segment_build"]


def test_authorization_refs_are_idempotent_and_conflict_on_reuse() -> None:
    run = production_run.new_production_run(
        project_id="shop-demo", review_mode_preset="normal", now=NOW
    )
    once = production_run.add_authorization_ref(
        run,
        authorization_revision="auth-1",
        scope="sample",
        intent_ref="intents/approve-sample.json",
        decision_ref="decision_log.json",
        now=NOW,
    )
    twice = production_run.add_authorization_ref(
        once,
        authorization_revision="auth-1",
        scope="sample",
        intent_ref="intents/approve-sample.json",
        decision_ref="decision_log.json",
        now="2026-08-19T09:00:00+00:00",
    )
    assert len(twice["authorization_refs"]) == 1
    assert twice["authorization_refs"][0]["created_at"] == NOW
    with pytest.raises(production_run.ProductionRunConflictError):
        production_run.add_authorization_ref(
            twice,
            authorization_revision="auth-1",
            scope="batch",
            intent_ref="intents/approve-batch.json",
            now=NOW,
        )


def test_job_summary_deduplicates_same_key_and_allows_status_progress() -> None:
    run = production_run.new_production_run(
        project_id="shop-demo",
        run_revision="3",
        review_mode_preset="normal",
        production_tier="heavy",
        now=NOW,
    )
    job = _job()
    queued = production_run.register_job_summary(run, job, now=NOW)
    running_job = {**job, "status": "running", "job_id": "provider-j1"}
    running = production_run.register_job_summary(queued, running_job, now=NOW)
    assert running["job_keys"] == [job["job_key"]]
    assert len(running["task_summaries"]) == 1
    assert running["task_summaries"][0]["status"] == "running"
    assert running["task_summaries"][0]["job_id"] == "provider-j1"


def test_job_summary_rejects_same_key_with_different_content() -> None:
    run = production_run.new_production_run(
        project_id="shop-demo",
        run_revision="3",
        review_mode_preset="normal",
        production_tier="heavy",
        now=NOW,
    )
    job = _job()
    recorded = production_run.register_job_summary(run, job, now=NOW)
    conflicting = {**job, "model": "other-model"}
    with pytest.raises(production_run.ProductionRunConflictError, match="different"):
        production_run.register_job_summary(recorded, conflicting, now=NOW)


def test_job_summary_allows_new_authorization_only_on_later_attempt() -> None:
    run = production_run.new_production_run(
        project_id="shop-demo",
        run_revision="3",
        review_mode_preset="normal",
        production_tier="heavy",
        now=NOW,
    )
    first = _job(authorization_revision="auth-r4", attempt=1)
    recorded = production_run.register_job_summary(run, first, now=NOW)

    same_attempt = {**first, "authorization_revision": "auth-r5"}
    with pytest.raises(
        production_run.ProductionRunConflictError, match="later attempt"
    ):
        production_run.register_job_summary(recorded, same_attempt, now=NOW)

    retry = {**first, "authorization_revision": "auth-r5", "attempt": 2}
    retried = production_run.register_job_summary(recorded, retry, now=NOW)
    assert retried["job_keys"] == [first["job_key"]]
    assert retried["task_summaries"][0]["attempt"] == 2
    assert retried["task_summaries"][0]["authorization_revision"] == "auth-r5"

    with pytest.raises(
        production_run.ProductionRunConflictError, match="stale attempt"
    ):
        production_run.register_job_summary(retried, first, now=NOW)


def test_lazy_initialization_does_not_write_until_explicitly_persisted(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, review="minimal")
    (project / "checkpoint_assets_gate.json").write_text(
        json.dumps(
            {
                "stage": "assets_gate",
                "status": "completed",
                "human_approved": True,
            }
        ),
        encoding="utf-8",
    )
    (project / "artifacts" / "sample_reel.json").write_text("{}", encoding="utf-8")

    initialized, created = production_run.load_or_initialize_production_run(
        project, persist=False, now=NOW
    )
    assert created is True
    assert not (project / "production_run.json").exists()
    assert initialized["source"] == "legacy_lazy_init"
    assert initialized["stage_results"]["assets_gate"]["status"] == "completed"
    assert initialized["stage_results"]["sample_review"]["status"] == "not_required"
    assert initialized["stage_results"]["sample_review"]["evidence_refs"] == [
        "artifacts/sample_reel.json"
    ]

    persisted, created = production_run.load_or_initialize_production_run(
        project, persist=True, now=NOW
    )
    assert created is True
    assert (project / "production_run.json").is_file()
    assert persisted == production_run.read_production_run(project)


def test_legacy_final_is_never_regressed_to_incomplete(tmp_path: Path) -> None:
    project = _project(tmp_path, review="minimal")
    (project / "renders").mkdir()
    (project / "renders" / "final.mp4").write_bytes(b"real-final")
    run = production_run.initialize_legacy_production_run(project, now=NOW)
    assert run["legacy_final_detected"] is True
    assert run["stage_results"]["final_compose"]["status"] == "completed"
    assert run["stage_results"]["final_compose"]["evidence_refs"] == [
        "renders/final.mp4"
    ]


def test_legacy_job_is_summarized_without_copying_media_payload(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "artifacts" / "produce_job.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "shop-demo",
                "status": "done",
                "job_id": "old-j1",
                "output_path": "renders/final.mp4",
                "friendly_zh": "成片完成",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    run = production_run.initialize_legacy_production_run(project, now=NOW)
    summary = run["task_summaries"][0]
    assert summary["job_id"] == "old-j1"
    assert "friendly_zh" not in summary
    assert "artifact" not in summary


def test_existing_invalid_run_fails_closed_and_is_not_overwritten(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    path = project / "production_run.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(production_run.ProductionRunError, match="invalid JSON"):
        production_run.load_or_initialize_production_run(project, persist=True, now=NOW)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_atomic_replace_failure_preserves_existing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    run = production_run.new_production_run(
        project_id="shop-demo", review_mode_preset="normal", now=NOW
    )
    production_run.write_production_run(project, run)
    before = (project / "production_run.json").read_bytes()

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr("lib.persistence.json_store.os.replace", fail_replace)
    changed = {**run, "updated_at": "2026-08-19T09:00:00+00:00"}
    with pytest.raises(OSError, match="replace failed"):
        production_run.write_production_run(project, changed)
    assert (project / "production_run.json").read_bytes() == before
    assert list(project.glob(".production_run.json.*.tmp")) == []


@pytest.mark.parametrize("status", ["queued", "running"])
def test_orphan_with_complete_outputs_converges_done_without_retry(
    tmp_path: Path, status: str
) -> None:
    project = _project(tmp_path)
    for rel in ("assets/video/sample_r2.mp4", "artifacts/sample_reel.json"):
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"evidence")
    job = _job(status=status)
    recovered = production_run.reconcile_orphaned_job(
        job, project, background_job_exists=False, now=NOW
    )
    assert recovered["status"] == "done"
    assert recovered["orphaned"] is False
    assert recovered["recovered_without_retry"] is True
    assert recovered["recovery_code"] == "expected_outputs_complete"


def test_orphan_with_missing_output_pauses_and_never_claims_retry(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    media = project / "assets" / "video" / "sample_r2.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"clip")
    job = _job(status="running", attempt=2)
    recovered = production_run.reconcile_orphaned_job(
        job, project, background_job_exists=False, now=NOW
    )
    assert recovered["status"] == "paused"
    assert recovered["orphaned"] is True
    assert recovered["code"] == "orphaned"
    assert recovered["attempt"] == 2
    assert recovered["missing_outputs"] == ["artifacts/sample_reel.json"]
    assert "retry" not in recovered


def test_live_or_terminal_job_is_not_reclassified(tmp_path: Path) -> None:
    project = _project(tmp_path)
    running = _job(status="running")
    assert production_run.reconcile_orphaned_job(
        running, project, background_job_exists=True, now=NOW
    )["status"] == "running"
    done = _job(status="done")
    assert production_run.reconcile_orphaned_job(
        done, project, background_job_exists=False, now=NOW
    )["status"] == "done"
