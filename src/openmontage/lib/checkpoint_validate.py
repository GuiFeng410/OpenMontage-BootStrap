"""Checkpoint schema and canonical artifact validation. Does not write files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import jsonschema

from lib.resources import get_resources
from schemas.artifacts import ARTIFACT_NAMES, validate_artifact

CHECKPOINT_SCHEMA_PATH = get_resources().checkpoint_schema()

ALL_KNOWN_STAGES = frozenset([
    "research", "proposal", "idea", "script", "scene_plan",
    "assets", "edit", "compose", "publish",
])

STAGES = ["research", "proposal", "idea", "script", "scene_plan",
          "assets", "edit", "compose", "publish"]

CANONICAL_STAGE_ARTIFACTS = {
    "research": "research_brief",
    "proposal": "proposal_packet",
    "idea": "brief",
    "script": "script",
    "scene_plan": "scene_plan",
    "assets": "asset_manifest",
    "edit": "edit_decisions",
    "compose": "render_report",
    "publish": "publish_log",
}

SUPPLEMENTARY_ARTIFACTS = {
    "source_media_review",  # Required before first planning stage when user media exists
    "final_review",         # Required by compose stage before presenting to user
    "video_analysis_brief", # Reference-video grounding artifact carried alongside stages
}

def get_pipeline_stages(pipeline_type: str | None) -> list[str]:
    """Return the ordered stage list for a specific pipeline.

    Falls back to STAGES (deterministic canonical order) when pipeline_type
    is not provided or the manifest cannot be loaded.

    Previous versions used a set intersection here, which produced
    nondeterministic ordering. The fallback now uses a stable list.
    """
    if pipeline_type is None:
        # Deterministic canonical fallback — sorted to ensure stable ordering
        import logging
        logging.getLogger(__name__).warning(
            "get_pipeline_stages called without pipeline_type — "
            "using canonical fallback order. Pass pipeline_type for correctness."
        )
        return list(STAGES)

    try:
        from lib.pipeline_loader import load_pipeline_readonly, get_stage_order
        manifest = load_pipeline_readonly(pipeline_type)
        return get_stage_order(manifest)
    except (FileNotFoundError, Exception):
        # Graceful fallback: return all known stages in canonical order
        return list(STAGES)

PROJECT_MARKER_FILENAME = "project.json"

class CheckpointValidationError(ValueError):
    """Raised when a checkpoint or its canonical artifacts are invalid."""


@lru_cache(maxsize=1)
def _load_checkpoint_schema() -> dict[str, Any]:
    with open(CHECKPOINT_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)

def _validate_artifacts_for_stage(
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    project_dir: Optional[Path] = None,
) -> None:
    # Valid stages come from the pipeline manifest (get_pipeline_stages), which
    # can declare stages beyond the 9 canonical ones (e.g. character-animation's
    # `character_design`/`rig_plan`, screen-demo's `real_capture`). Those have no
    # canonical artifact, so look it up defensively — a missing entry means the
    # stage simply has no required artifact, not a crash.
    required_artifact = CANONICAL_STAGE_ARTIFACTS.get(stage)
    if (
        required_artifact is not None
        and status in {"completed", "awaiting_human"}
        and required_artifact not in artifacts
    ):
        raise CheckpointValidationError(
            f"Stage {stage!r} with status {status!r} must include "
            f"canonical artifact {required_artifact!r}"
        )

    for artifact_name, artifact_data in artifacts.items():
        if artifact_name not in ARTIFACT_NAMES:
            continue
        if isinstance(artifact_data, str):
            if project_dir is None:
                raise CheckpointValidationError(
                    f"Artifact {artifact_name!r} uses a path reference but no project directory was provided"
                )
            ref = Path(artifact_data)
            if not ref.is_absolute():
                ref = project_dir / ref
            try:
                ref = ref.resolve()
                ref.relative_to(project_dir.resolve())
            except (OSError, ValueError) as exc:
                raise CheckpointValidationError(
                    f"Artifact {artifact_name!r} path must stay inside the project directory"
                ) from exc
            try:
                with open(ref, encoding="utf-8") as f:
                    artifact_data = json.load(f)
            except (OSError, json.JSONDecodeError, UnicodeError) as exc:
                raise CheckpointValidationError(
                    f"Artifact {artifact_name!r} path could not be read as UTF-8 JSON: {ref}"
                ) from exc
        if not isinstance(artifact_data, dict):
            raise CheckpointValidationError(
                f"Artifact {artifact_name!r} must be a JSON object or project-local JSON path"
            )
        try:
            validate_artifact(artifact_name, artifact_data)
        except Exception as exc:
            raise CheckpointValidationError(
                f"Artifact {artifact_name!r} failed schema validation: {exc}"
            ) from exc

def validate_checkpoint(
    checkpoint: dict[str, Any],
    *,
    project_dir: Optional[Path] = None,
    enforce_pipeline_outputs: bool = False,
) -> None:
    """Validate checkpoint structure and canonical artifact payloads.

    Uses pipeline_type (if present) to resolve the valid stage list.
    Falls back to ALL_KNOWN_STAGES when pipeline_type is absent.
    """
    stage = checkpoint.get("stage")
    status = checkpoint.get("status")
    artifacts = checkpoint.get("artifacts")
    pipeline_type = checkpoint.get("pipeline_type")

    valid_stages = (
        set(get_pipeline_stages(pipeline_type)) if pipeline_type
        else ALL_KNOWN_STAGES
    )

    if not isinstance(stage, str) or stage not in valid_stages:
        raise CheckpointValidationError(
            f"Invalid stage: {stage!r} for pipeline {pipeline_type!r}. "
            f"Valid stages: {sorted(valid_stages)}"
        )
    if not isinstance(status, str):
        raise CheckpointValidationError(f"Invalid status: {status!r}")
    if not isinstance(artifacts, dict):
        raise CheckpointValidationError("Checkpoint artifacts must be a dictionary")

    if (
        enforce_pipeline_outputs
        and pipeline_type not in {None, "", "unknown"}
        and status in {"completed", "awaiting_human"}
    ):
        from lib.pipeline_loader import load_pipeline_readonly

        manifest = load_pipeline_readonly(pipeline_type)
        stage_def = next(
            (item for item in manifest.get("stages", []) if item.get("name") == stage),
            {},
        )
        missing = [name for name in stage_def.get("produces", []) if name not in artifacts]
        if missing:
            raise CheckpointValidationError(
                f"Stage {stage!r} must include manifest outputs: {missing}"
            )

    _validate_artifacts_for_stage(stage, status, artifacts, project_dir)
    _validate_commercial_media_file(
        pipeline_type,
        stage,
        status,
        artifacts,
        project_dir,
    )
    _validate_commercial_asset_assignment_gate(
        checkpoint.get("project_id"),
        pipeline_type,
        stage,
        status,
        artifacts,
        project_dir,
    )

    try:
        jsonschema.validate(instance=checkpoint, schema=_load_checkpoint_schema())
    except jsonschema.ValidationError as exc:
        raise CheckpointValidationError(f"Checkpoint failed schema validation: {exc.message}") from exc


from lib.checkpoint_commercial import (  # noqa: E402
    _validate_commercial_asset_assignment_gate,
    _validate_commercial_media_file,
)
