"""Runner code stamp: mtime concatenation for process reuse."""

from __future__ import annotations

from pathlib import Path

# Keep the original seven first, then modules split out during G1/G2.
RUNNER_STAMP_MODULES: tuple[str, ...] = (
    "backlot/runner.py",
    "src/openmontage/lib/approval_bundle.py",
    "src/openmontage/lib/board_runner.py",
    "src/openmontage/lib/board_produce.py",
    "src/openmontage/lib/produce/__init__.py",
    "src/openmontage/lib/produce/job_store.py",
    "src/openmontage/lib/produce/compose_adapter.py",
    "src/openmontage/lib/produce/video_adapter.py",
    "src/openmontage/lib/produce/orchestrator.py",
    "src/openmontage/lib/board_advance.py",
    "src/openmontage/lib/board_draft_review.py",
    "src/openmontage/lib/board_gap_plan.py",
    "src/openmontage/lib/board_assets_gate.py",
    "backlot/read_models/__init__.py",
    "backlot/read_models/common.py",
    "backlot/read_models/commercial.py",
    "src/openmontage/lib/paths.py",
    "src/openmontage/lib/resources.py",
    "src/openmontage/lib/persistence/json_store.py",
    "src/openmontage/lib/persistence/file_lock.py",
    "src/openmontage/lib/persistence/code_stamp.py",
    "src/openmontage/lib/checkpoint.py",
    "src/openmontage/lib/checkpoint_validate.py",
    "src/openmontage/lib/checkpoint_commercial.py",
    "src/openmontage/lib/checkpoint_store.py",
    "src/openmontage/lib/application/export_project.py",
    "src/openmontage/lib/interaction_intents.py",
    "src/openmontage/lib/board_production_run.py",
    "src/openmontage/lib/project_export.py",
)


def runner_code_stamp(repo_root: Path) -> str:
    parts: list[str] = []
    root = Path(repo_root)
    for rel in RUNNER_STAMP_MODULES:
        path = root / rel
        try:
            parts.append(f"{rel}:{path.stat().st_mtime_ns}")
        except OSError:
            parts.append(f"{rel}:0")
    return ";".join(parts)
