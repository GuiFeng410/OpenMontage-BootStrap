"""Tests for checkpoint artifact merge + materialize."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from lib.checkpoint import (
    CheckpointValidationError,
    _materialize_artifacts,
    _project_checkpoint_lock,
    merge_checkpoint_artifacts,
    merge_write_checkpoint,
    read_checkpoint,
    write_checkpoint,
)


def _brief_locked_artifacts() -> dict:
    return {
        "brief": {
            "theme": "银手镯",
            "duration_seconds": 15,
            "images": {},
        },
        "asset_precheck": {
            "version": "1.0",
            "entries": [],
            "summary": {
                "total_images": 0,
                "low_resolution_count": 0,
                "duplicate_group_count": 0,
                "needs_user_attention": True,
            },
        },
        "video_plan": {"segments": [{"id": "beat_01", "t": "0-5", "method": "camera_move"}]},
        "segment_cards": {
            "version": "1.0",
            "duration_seconds": 5,
            "overall_prompt_zh": "开场→细节→收尾",
            "segments": [{
                "beat": "b1",
                "time": "0-5",
                "copy_plan_zh": "亮相",
                "shot_plan_zh": "缓慢推进",
                "asset_plan_zh": "使用商品主图",
            }],
        },
    }


def _decision_log(project_id: str, decision_id: str, selected: str) -> dict:
    return {
        "version": "1.0",
        "project_id": project_id,
        "decisions": [
            {
                "decision_id": decision_id,
                "stage": "brief_locked",
                "category": "asset_decision",
                "subject": "事务测试",
                "options_considered": [
                    {
                        "option_id": selected,
                        "label": selected,
                        "score": 1.0,
                        "reason": "事务测试",
                    }
                ],
                "selected": selected,
                "reason": "事务测试",
            }
        ],
    }


def _seed_decision_logs(project: Path, project_id: str) -> tuple[bytes, bytes]:
    payload = json.dumps(
        _decision_log(project_id, "d-old", "old"),
        ensure_ascii=False,
        indent=2,
    ).encode()
    root = project / "decision_log.json"
    artifact = project / "artifacts" / "decision_log.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    root.write_bytes(payload)
    artifact.write_bytes(payload)
    return root.read_bytes(), artifact.read_bytes()


def _seed_old_materialized_state(
    tmp_path: Path, project_id: str
) -> tuple[Path, Path, bytes, dict[str, bytes]]:
    project = tmp_path / project_id
    project.mkdir()
    (project / "project.json").write_text(
        json.dumps({"pipeline_type": "bootstrap-commercial", "title": "t"}),
        encoding="utf-8",
    )
    checkpoint = write_checkpoint(
        tmp_path,
        project_id,
        "brief_locked",
        "in_progress",
        {},
        pipeline_type="bootstrap-commercial",
    )
    checkpoint_before = checkpoint.read_bytes()

    old_artifacts = _brief_locked_artifacts()
    old_artifacts["brief"]["theme"] = "旧银手镯"
    artifact_dir = project / "artifacts"
    artifact_dir.mkdir()
    before: dict[str, bytes] = {}
    for name, payload in old_artifacts.items():
        target = artifact_dir / f"{name}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        before[target.name] = target.read_bytes()
    return project, checkpoint, checkpoint_before, before


def _assert_old_materialized_state(
    artifact_dir: Path,
    checkpoint: Path,
    checkpoint_before: bytes,
    artifacts_before: dict[str, bytes],
) -> None:
    assert checkpoint.read_bytes() == checkpoint_before
    assert {path.name for path in artifact_dir.iterdir()} == set(artifacts_before)
    for filename, content in artifacts_before.items():
        assert (artifact_dir / filename).read_bytes() == content


def test_merge_checkpoint_artifacts_keeps_prior_keys():
    merged = merge_checkpoint_artifacts(
        {"brief": {"theme": "A"}, "video_plan": {"segments": [1]}},
        {"asset_ledger": {"entries": []}},
    )
    assert "brief" in merged
    assert "video_plan" in merged
    assert "asset_ledger" in merged


def test_write_checkpoint_materializes_artifacts_json(tmp_path: Path):
    project_id = "seal-demo"
    (tmp_path / project_id).mkdir()
    (tmp_path / project_id / "project.json").write_text(
        json.dumps({"pipeline_type": "bootstrap-commercial", "title": "t"}),
        encoding="utf-8",
    )
    artifacts = _brief_locked_artifacts()
    write_checkpoint(
        tmp_path,
        project_id,
        "brief_locked",
        "awaiting_human",
        artifacts,
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
    )
    art = tmp_path / project_id / "artifacts"
    assert (art / "brief.json").exists()
    assert (art / "video_plan.json").exists()
    assert (art / "segment_cards.json").exists()
    brief = json.loads((art / "brief.json").read_text(encoding="utf-8"))
    assert brief["theme"] == "银手镯"


def test_materialize_skips_path_strings(tmp_path: Path):
    written = _materialize_artifacts(
        tmp_path,
        {"brief": {"ok": True}, "video_plan": "artifacts/video_plan.json"},
    )
    assert written == ["brief"]
    assert (tmp_path / "artifacts" / "brief.json").exists()


def test_required_inline_artifact_materialize_failure_keeps_current_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = "materialize-failure"
    project = tmp_path / project_id
    project.mkdir()
    (project / "project.json").write_text(
        json.dumps({"pipeline_type": "bootstrap-commercial", "title": "t"}),
        encoding="utf-8",
    )
    write_checkpoint(
        tmp_path,
        project_id,
        "brief_locked",
        "in_progress",
        {},
        pipeline_type="bootstrap-commercial",
    )

    original_write_text = Path.write_text

    def fail_artifact_write(path: Path, *args, **kwargs):
        if path.parent.name == "artifacts":
            raise OSError("disk unavailable")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_artifact_write)

    with pytest.raises(CheckpointValidationError, match="required.*material"):
        write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "completed",
            _brief_locked_artifacts(),
            pipeline_type="bootstrap-commercial",
            human_approved=True,
        )

    current = read_checkpoint(tmp_path, project_id, "brief_locked")
    assert current is not None
    assert current["status"] == "in_progress"


def test_required_artifact_second_prepare_failure_rolls_back_all_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = "materialize-prepare-rollback"
    project, checkpoint, checkpoint_before, artifacts_before = (
        _seed_old_materialized_state(tmp_path, project_id)
    )
    artifact_dir = project / "artifacts"
    original_write_text = Path.write_text
    artifact_writes = 0

    def fail_second_artifact_write(path: Path, *args, **kwargs):
        nonlocal artifact_writes
        if path.parent == artifact_dir:
            artifact_writes += 1
            if artifact_writes == 2:
                raise OSError("second artifact prepare failed")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_second_artifact_write)

    with pytest.raises(CheckpointValidationError, match="required.*material"):
        write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "completed",
            _brief_locked_artifacts(),
            pipeline_type="bootstrap-commercial",
            human_approved=True,
        )

    _assert_old_materialized_state(
        artifact_dir,
        checkpoint,
        checkpoint_before,
        artifacts_before,
    )


def test_required_artifact_second_replace_failure_rolls_back_all_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = "materialize-replace-rollback"
    project, checkpoint, checkpoint_before, artifacts_before = (
        _seed_old_materialized_state(tmp_path, project_id)
    )
    artifact_dir = project / "artifacts"
    absent_before = "asset_precheck.json"
    (artifact_dir / absent_before).unlink()
    artifacts_before.pop(absent_before)
    target_names = {
        "asset_precheck.json",
        "brief.json",
        "segment_cards.json",
        "video_plan.json",
    }
    original_replace = os.replace
    artifact_replaces = 0

    def fail_second_artifact_replace(src, dst):
        nonlocal artifact_replaces
        destination = Path(dst)
        if destination.parent == artifact_dir and destination.name in target_names:
            artifact_replaces += 1
            if artifact_replaces == 2:
                raise OSError("second artifact replace failed")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_second_artifact_replace)

    with pytest.raises(CheckpointValidationError, match="required.*material"):
        write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "completed",
            _brief_locked_artifacts(),
            pipeline_type="bootstrap-commercial",
            human_approved=True,
        )

    _assert_old_materialized_state(
        artifact_dir,
        checkpoint,
        checkpoint_before,
        artifacts_before,
    )


def test_required_artifact_success_ignores_transaction_temp_cleanup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = "materialize-temp-cleanup-window"
    project, checkpoint, _, _ = _seed_old_materialized_state(tmp_path, project_id)
    artifact_dir = project / "artifacts"
    original_unlink = Path.unlink
    injected_cleanup_paths: list[Path] = []
    transaction_temp = re.compile(
        r"^\.[a-z0-9_]+\.json\.[0-9a-f]{32}(?:\.rollback)?\.tmp$"
    )

    def fail_first_transaction_temp_unlink(path: Path, *args, **kwargs):
        if (
            not injected_cleanup_paths
            and path.parent == artifact_dir
            and transaction_temp.fullmatch(path.name)
        ):
            injected_cleanup_paths.append(path)
            raise OSError("simulated stale transaction temp lock")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_first_transaction_temp_unlink)

    result = write_checkpoint(
        tmp_path,
        project_id,
        "brief_locked",
        "completed",
        _brief_locked_artifacts(),
        pipeline_type="bootstrap-commercial",
        human_approved=True,
    )

    assert result == checkpoint
    current = read_checkpoint(tmp_path, project_id, "brief_locked")
    assert current is not None
    assert current["status"] == "completed"
    assert json.loads((artifact_dir / "brief.json").read_text(encoding="utf-8"))[
        "theme"
    ] == "银手镯"
    assert len(injected_cleanup_paths) == 1
    assert not list(artifact_dir.glob("*.bak"))


def test_decision_log_validation_failure_is_fully_transactional(
    tmp_path: Path,
) -> None:
    project_id = "decision-validation-rollback"
    project = tmp_path / project_id
    project.mkdir()
    (project / "project.json").write_text(
        json.dumps({"pipeline_type": "bootstrap-commercial", "title": "t"}),
        encoding="utf-8",
    )
    root_before, artifact_before = _seed_decision_logs(project, project_id)
    artifacts = _brief_locked_artifacts()
    artifacts["brief"] = {"invalid": True}
    artifacts["decision_log"] = _decision_log(project_id, "d-new", "new")

    with pytest.raises(CheckpointValidationError):
        write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "awaiting_human",
            artifacts,
            pipeline_type="bootstrap-commercial",
        )

    assert (project / "decision_log.json").read_bytes() == root_before
    assert (
        project / "artifacts" / "decision_log.json"
    ).read_bytes() == artifact_before
    assert not (project / "checkpoint_brief_locked.json").exists()


def test_decision_log_materialize_failure_is_fully_transactional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "decision-materialize-rollback"
    project, checkpoint, checkpoint_before, artifacts_before = (
        _seed_old_materialized_state(tmp_path, project_id)
    )
    root_before, artifact_before = _seed_decision_logs(project, project_id)
    artifacts_before["decision_log.json"] = artifact_before
    original_write_text = Path.write_text

    def fail_required_prepare(path: Path, *args, **kwargs):
        if path.parent == project / "artifacts" and path.name.endswith(".tmp"):
            raise OSError("required prepare failed")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_required_prepare)
    artifacts = _brief_locked_artifacts()
    artifacts["decision_log"] = _decision_log(project_id, "d-new", "new")

    with pytest.raises(CheckpointValidationError, match="required.*material"):
        write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "completed",
            artifacts,
            pipeline_type="bootstrap-commercial",
            human_approved=True,
        )

    _assert_old_materialized_state(
        project / "artifacts",
        checkpoint,
        checkpoint_before,
        artifacts_before,
    )
    assert (project / "decision_log.json").read_bytes() == root_before


def test_decision_log_checkpoint_swap_failure_is_fully_transactional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "decision-checkpoint-rollback"
    project, checkpoint, checkpoint_before, artifacts_before = (
        _seed_old_materialized_state(tmp_path, project_id)
    )
    root_before, artifact_before = _seed_decision_logs(project, project_id)
    artifacts_before["decision_log.json"] = artifact_before
    original_replace = os.replace

    def fail_checkpoint_replace(src, dst):
        if Path(dst) == checkpoint:
            raise OSError("checkpoint swap failed")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_checkpoint_replace)
    artifacts = _brief_locked_artifacts()
    artifacts["decision_log"] = _decision_log(project_id, "d-new", "new")

    with pytest.raises(CheckpointValidationError, match="prior state was restored"):
        write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "completed",
            artifacts,
            pipeline_type="bootstrap-commercial",
            human_approved=True,
        )

    _assert_old_materialized_state(
        project / "artifacts",
        checkpoint,
        checkpoint_before,
        artifacts_before,
    )
    assert (project / "decision_log.json").read_bytes() == root_before


def test_project_marker_rolls_back_when_checkpoint_swap_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "marker-rollback"
    project = tmp_path / project_id
    project.mkdir()
    marker = project / "project.json"
    marker.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "pipeline_type": "bootstrap-commercial",
                "production_profile": {"production_tier": "light"},
            }
        ),
        encoding="utf-8",
    )
    checkpoint = write_checkpoint(
        tmp_path,
        project_id,
        "brief_locked",
        "in_progress",
        {},
        pipeline_type="bootstrap-commercial",
    )
    checkpoint_before = checkpoint.read_bytes()
    marker_before = marker.read_bytes()
    original_replace = os.replace

    def fail_checkpoint_swap(src, dst):
        if Path(dst) == checkpoint:
            raise OSError("forced checkpoint swap failure")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_checkpoint_swap)

    with pytest.raises(CheckpointValidationError, match="prior state was restored"):
        merge_write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "in_progress",
            {"production_profile": {"production_tier": "heavy"}},
            pipeline_type="bootstrap-commercial",
            project_marker_builder=lambda artifacts: {
                "project_id": project_id,
                "pipeline_type": "bootstrap-commercial",
                "production_profile": artifacts["production_profile"],
            },
        )

    assert checkpoint.read_bytes() == checkpoint_before
    assert marker.read_bytes() == marker_before


def test_project_marker_builder_failure_does_not_commit_checkpoint(
    tmp_path: Path,
) -> None:
    project_id = "marker-builder-failure"
    project = tmp_path / project_id
    project.mkdir()
    marker = project / "project.json"
    marker.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "pipeline_type": "bootstrap-commercial",
                "production_profile": {"production_tier": "light"},
            }
        ),
        encoding="utf-8",
    )
    checkpoint = write_checkpoint(
        tmp_path,
        project_id,
        "brief_locked",
        "in_progress",
        {},
        pipeline_type="bootstrap-commercial",
    )
    checkpoint_before = checkpoint.read_bytes()
    marker_before = marker.read_bytes()

    def fail_builder(_artifacts):
        raise RuntimeError("forced marker builder failure")

    with pytest.raises(RuntimeError, match="forced marker builder failure"):
        merge_write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "in_progress",
            {"production_profile": {"production_tier": "heavy"}},
            pipeline_type="bootstrap-commercial",
            project_marker_builder=fail_builder,
        )

    assert checkpoint.read_bytes() == checkpoint_before
    assert marker.read_bytes() == marker_before


def test_project_lock_preserves_success_against_concurrent_failed_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "concurrent-transaction"
    project, checkpoint, _, _ = _seed_old_materialized_state(tmp_path, project_id)
    _seed_decision_logs(project, project_id)
    original_replace = os.replace
    failing_at_swap = threading.Event()
    release_failure = threading.Event()
    success_done = threading.Event()
    errors: list[BaseException] = []

    def block_failing_checkpoint_swap(src, dst):
        if (
            Path(dst) == checkpoint
            and threading.current_thread().name == "failing-checkpoint-writer"
        ):
            failing_at_swap.set()
            assert release_failure.wait(timeout=5)
            raise OSError("forced failed transaction")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", block_failing_checkpoint_swap)

    def write_version(theme: str, decision_id: str) -> None:
        artifacts = _brief_locked_artifacts()
        artifacts["brief"]["theme"] = theme
        artifacts["decision_log"] = _decision_log(
            project_id,
            decision_id,
            theme,
        )
        write_checkpoint(
            tmp_path,
            project_id,
            "brief_locked",
            "completed",
            artifacts,
            pipeline_type="bootstrap-commercial",
            human_approved=True,
        )

    def failing_writer() -> None:
        try:
            write_version("失败事务", "d-failed")
        except CheckpointValidationError:
            return
        except BaseException as exc:
            errors.append(exc)
        else:
            errors.append(AssertionError("failing transaction unexpectedly succeeded"))

    def successful_writer() -> None:
        try:
            write_version("成功事务", "d-success")
        except BaseException as exc:
            errors.append(exc)
        finally:
            success_done.set()

    failed_thread = threading.Thread(
        target=failing_writer,
        name="failing-checkpoint-writer",
    )
    failed_thread.start()
    assert failing_at_swap.wait(timeout=5)
    success_thread = threading.Thread(
        target=successful_writer,
        name="successful-checkpoint-writer",
    )
    success_thread.start()
    success_done.wait(timeout=0.5)
    release_failure.set()
    failed_thread.join(timeout=5)
    success_thread.join(timeout=5)

    assert errors == []
    assert not failed_thread.is_alive()
    assert not success_thread.is_alive()
    current = json.loads(checkpoint.read_text(encoding="utf-8"))
    materialized = json.loads(
        (project / "artifacts" / "brief.json").read_text(encoding="utf-8")
    )
    root_log = json.loads(
        (project / "decision_log.json").read_text(encoding="utf-8")
    )
    artifact_log = json.loads(
        (project / "artifacts" / "decision_log.json").read_text(encoding="utf-8")
    )
    decision_ids = {item["decision_id"] for item in root_log["decisions"]}

    assert current["artifacts"]["brief"]["theme"] == "成功事务"
    assert materialized["theme"] == "成功事务"
    assert decision_ids == {"d-old", "d-success"}
    assert artifact_log == root_log
    assert (project / ".checkpoint.lock").exists()


def test_project_os_lock_is_released_when_holder_process_is_terminated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "terminated-lock-holder"
    script = """
import sys
import time
from pathlib import Path
from lib.checkpoint import _project_checkpoint_lock

root = Path(sys.argv[1])
project_id = sys.argv[2]
with _project_checkpoint_lock(root, project_id):
    print("LOCKED", flush=True)
    time.sleep(60)
"""
    holder = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path), project_id],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "LOCKED"
        holder.terminate()
        holder.wait(timeout=5)
        monkeypatch.setattr(
            "lib.checkpoint.CHECKPOINT_LOCK_TIMEOUT_SECONDS",
            0.3,
        )

        path = write_checkpoint(
            tmp_path,
            project_id,
            "proposal",
            "in_progress",
            {},
        )
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)

    assert path.exists()


def test_contended_project_os_lock_times_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "contended-lock"
    locked = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with _project_checkpoint_lock(tmp_path, project_id):
            locked.set()
            assert release.wait(timeout=5)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert locked.wait(timeout=5)
    monkeypatch.setattr(
        "lib.checkpoint.CHECKPOINT_LOCK_TIMEOUT_SECONDS",
        0.05,
    )
    try:
        with pytest.raises(CheckpointValidationError, match="lock timeout"):
            write_checkpoint(
                tmp_path,
                project_id,
                "research",
                "in_progress",
                {},
            )
    finally:
        release.set()
        holder.join(timeout=5)

    assert not holder.is_alive()
