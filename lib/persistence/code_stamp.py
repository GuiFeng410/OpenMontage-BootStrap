"""Runner code stamp: mtime concatenation for process reuse."""

from __future__ import annotations

from pathlib import Path

# Keep the original seven first, then modules split out during G1/G2.
RUNNER_STAMP_MODULES: tuple[str, ...] = (
    "backlot/runner.py",
    "lib/approval_bundle.py",
    "lib/board_runner.py",
    "lib/board_produce.py",
    "lib/produce/__init__.py",
    "lib/produce/job_store.py",
    "lib/produce/compose_adapter.py",
    "lib/produce/video_adapter.py",
    "lib/produce/orchestrator.py",
    "lib/board_advance.py",
    "lib/board_gap_plan.py",
    "lib/board_assets_gate.py",
    "backlot/read_models/__init__.py",
    "backlot/read_models/common.py",
    "backlot/read_models/commercial.py",
    "lib/paths.py",
    "lib/resources.py",
    "lib/persistence/json_store.py",
    "lib/persistence/file_lock.py",
    "lib/persistence/code_stamp.py",
    "lib/checkpoint.py",
    "lib/checkpoint_validate.py",
    "lib/checkpoint_commercial.py",
    "lib/checkpoint_store.py",
    "lib/application/export_project.py",
    "lib/interaction_intents.py",
    "lib/board_production_run.py",
    "lib/project_export.py",
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
