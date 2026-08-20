"""Pure builders and validators for commercial review-stage artifacts.

The helpers in this module do not read or write project files. They validate
the persisted artifact shape plus the board-specific path rules that JSON
Schema alone cannot express, and they reject media reused across distinct
review stages.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from pathlib import PurePosixPath
import posixpath
import re
from typing import Any

from jsonschema import ValidationError

from schemas.artifacts import validate_artifact


STAGE_ARTIFACT_ORDER = (
    "sample_reel",
    "review_overview",
    "full_draft_pro",
    "final_review",
)

_VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov", ".m4v", ".mkv"})
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_FINAL_CHECK_NAMES = (
    "technical_probe",
    "visual_spotcheck",
    "audio_spotcheck",
    "promise_preservation",
    "subtitle_check",
)


class StageArtifactValidationError(ValueError):
    """Raised when a review-stage artifact violates the board contract."""


def validate_relative_media_path(raw_path: Any, *, field: str = "path") -> str:
    """Validate and return an unchanged project-relative video path."""
    if not isinstance(raw_path, str) or not raw_path:
        raise StageArtifactValidationError(f"{field} must be a non-empty string")
    if raw_path != raw_path.strip():
        raise StageArtifactValidationError(
            f"{field} must not contain leading or trailing whitespace"
        )
    if "\x00" in raw_path:
        raise StageArtifactValidationError(f"{field} must not contain NUL bytes")
    if _WINDOWS_DRIVE.match(raw_path) or _URI_SCHEME.match(raw_path):
        raise StageArtifactValidationError(
            f"{field} must be a project-relative media path"
        )

    normalized = raw_path.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//"):
        raise StageArtifactValidationError(
            f"{field} must be a project-relative media path"
        )
    if ".." in PurePosixPath(normalized).parts:
        raise StageArtifactValidationError(f"{field} must not traverse outside the project")
    if PurePosixPath(normalized).suffix.lower() not in _VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(_VIDEO_EXTENSIONS))
        raise StageArtifactValidationError(
            f"{field} must reference a reviewable video ({allowed})"
        )
    return raw_path


def _path_identity(path: str) -> str:
    """Return a Windows-safe identity without changing the persisted path."""
    return posixpath.normpath(path.replace("\\", "/")).casefold()


def _mapping_copy(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StageArtifactValidationError(f"{field} must contain objects")
    return deepcopy(dict(value))


def _mapping_list(
    values: Iterable[Mapping[str, Any]] | None,
    *,
    field: str,
) -> list[dict[str, Any]]:
    if values is None:
        return []
    if isinstance(values, (str, bytes, Mapping)):
        raise StageArtifactValidationError(f"{field} must be an iterable of objects")
    return [
        _mapping_copy(value, field=f"{field}[{index}]")
        for index, value in enumerate(values)
    ]


def _merge_extra(
    payload: dict[str, Any],
    extra: Mapping[str, Any] | None,
    *,
    artifact_name: str,
) -> None:
    if extra is None:
        return
    if not isinstance(extra, Mapping):
        raise StageArtifactValidationError(f"{artifact_name} extra must be an object")
    overlap = sorted(set(payload).intersection(extra))
    if overlap:
        names = ", ".join(overlap)
        raise StageArtifactValidationError(
            f"{artifact_name} extra cannot replace protected fields: {names}"
        )
    payload.update(deepcopy(dict(extra)))


def _beat_ids(values: Iterable[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise StageArtifactValidationError("beat_ids must be an iterable of strings")
    beat_ids = list(values)
    if not beat_ids:
        raise StageArtifactValidationError("beat_ids must contain at least one beat")
    if any(not isinstance(item, str) or not item.strip() for item in beat_ids):
        raise StageArtifactValidationError("beat_ids must contain non-empty strings")
    if len(set(beat_ids)) != len(beat_ids):
        raise StageArtifactValidationError("beat_ids must not contain duplicates")
    return beat_ids


def _string_list(values: Iterable[str] | None, *, field: str) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes, Mapping)):
        raise StageArtifactValidationError(f"{field} must be an iterable of strings")
    result = list(values)
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise StageArtifactValidationError(f"{field} must contain non-empty strings")
    return result


def build_sample_reel(
    path: str,
    beat_ids: Iterable[str],
    *,
    duration_seconds: float | None = None,
    status: str = "pending",
    version: str = "1.0",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical sample review summary."""
    payload: dict[str, Any] = {
        "version": version,
        "path": validate_relative_media_path(path, field="sample_reel.path"),
        "beat_ids": _beat_ids(beat_ids),
        "status": status,
    }
    if duration_seconds is not None:
        payload["duration_seconds"] = duration_seconds
    _merge_extra(payload, extra, artifact_name="sample_reel")
    validate_stage_artifact("sample_reel", payload)
    return payload


def build_review_overview(
    overview: Iterable[Mapping[str, Any]],
    *,
    batches: Iterable[Mapping[str, Any]] | None = None,
    review_mode: str | None = None,
    version: str = "1.0",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the aggregate segment review summary.

    Reference-only batch rows remain valid for compatibility; their canonical
    media may live in the corresponding ``batchNN_review`` artifact.
    """
    payload: dict[str, Any] = {
        "version": version,
        "overview": _mapping_list(overview, field="review_overview.overview"),
        "batches": _mapping_list(batches, field="review_overview.batches"),
    }
    if review_mode is not None:
        payload["review_mode"] = review_mode
    _merge_extra(payload, extra, artifact_name="review_overview")
    validate_stage_artifact("review_overview", payload)
    return payload


def build_full_draft_pro(
    path: str,
    *,
    issue_segments: Iterable[Mapping[str, Any]] | None = None,
    modification_list: Iterable[str] | None = None,
    status: str | None = None,
    approved: bool | None = None,
    cuts_revision: str | None = None,
    duration_probe: float | None = None,
    version: str = "1.0",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an independent full-draft review summary."""
    modifications = _string_list(
        modification_list,
        field="full_draft_pro.modification_list",
    )
    payload: dict[str, Any] = {
        "version": version,
        "path": validate_relative_media_path(path, field="full_draft_pro.path"),
        "issue_segments": _mapping_list(
            issue_segments,
            field="full_draft_pro.issue_segments",
        ),
        "modification_list": modifications,
    }
    if status is not None:
        payload["status"] = status
    if approved is not None:
        payload["approved"] = approved
    if cuts_revision is not None:
        payload["cuts_revision"] = cuts_revision
    if duration_probe is not None:
        payload["duration_probe"] = duration_probe
    _merge_extra(payload, extra, artifact_name="full_draft_pro")
    validate_stage_artifact("full_draft_pro", payload)
    return payload


def build_final_review(
    output_path: str,
    *,
    status: str,
    checks: Mapping[str, Any] | None = None,
    cuts_revision: str | None = None,
    issues_found: Iterable[str] | None = None,
    recommended_action: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a schema-complete final review for a candidate or final render."""
    if checks is not None and not isinstance(checks, Mapping):
        raise StageArtifactValidationError("final_review.checks must be an object")
    checks_copy = deepcopy(dict(checks or {}))
    for name in _FINAL_CHECK_NAMES:
        checks_copy.setdefault(name, {})
    payload: dict[str, Any] = {
        "version": "1.0",
        "output_path": validate_relative_media_path(
            output_path,
            field="final_review.output_path",
        ),
        "status": status,
        "checks": checks_copy,
    }
    if cuts_revision is not None:
        payload["cuts_revision"] = cuts_revision
    if issues_found is not None:
        payload["issues_found"] = _string_list(
            issues_found,
            field="final_review.issues_found",
        )
    if recommended_action is not None:
        payload["recommended_action"] = recommended_action
    if metadata is not None:
        payload["metadata"] = _mapping_copy(metadata, field="final_review.metadata")
    validate_stage_artifact("final_review", payload)
    return payload


def validate_stage_artifact(
    artifact_name: str,
    artifact: Mapping[str, Any],
) -> None:
    """Validate one stage artifact against schema and path semantics."""
    if artifact_name not in STAGE_ARTIFACT_ORDER:
        raise StageArtifactValidationError(f"unsupported stage artifact: {artifact_name}")
    if not isinstance(artifact, Mapping):
        raise StageArtifactValidationError(f"{artifact_name} must be an object")
    payload = dict(artifact)
    try:
        validate_artifact(artifact_name, payload)
    except ValidationError as exc:
        raise StageArtifactValidationError(
            f"{artifact_name} failed schema validation: {exc.message}"
        ) from exc

    if artifact_name == "sample_reel":
        validate_relative_media_path(payload.get("path"), field="sample_reel.path")
        _beat_ids(payload.get("beat_ids") or [])
        return
    if artifact_name == "review_overview":
        for group_name in ("overview", "batches"):
            for index, row in enumerate(payload.get(group_name) or []):
                if not isinstance(row, Mapping):
                    continue
                if row.get("output_path") is not None:
                    validate_relative_media_path(
                        row.get("output_path"),
                        field=f"review_overview.{group_name}[{index}].output_path",
                    )
        return
    if artifact_name == "full_draft_pro":
        validate_relative_media_path(
            payload.get("path"),
            field="full_draft_pro.path",
        )
        return
    validate_relative_media_path(
        payload.get("output_path"),
        field="final_review.output_path",
    )


def media_paths_for_artifact(
    artifact_name: str,
    artifact: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return unique persisted media paths represented by one stage artifact."""
    validate_stage_artifact(artifact_name, artifact)
    if artifact_name == "sample_reel":
        raw_paths = [artifact["path"]]
    elif artifact_name == "review_overview":
        raw_paths = [
            row["output_path"]
            for group_name in ("overview", "batches")
            for row in artifact.get(group_name, [])
            if isinstance(row, Mapping) and row.get("output_path")
        ]
    elif artifact_name == "full_draft_pro":
        raw_paths = [artifact["path"]]
    else:
        raw_paths = [artifact["output_path"]]

    unique: list[str] = []
    seen: set[str] = set()
    for path in raw_paths:
        identity = _path_identity(path)
        if identity not in seen:
            seen.add(identity)
            unique.append(path)
    return tuple(unique)


def validate_stage_artifact_set(
    artifacts: Mapping[str, Mapping[str, Any]],
) -> None:
    """Reject one canonical media path reused by distinct review stages.

    Unrelated artifacts are ignored so callers may pass the complete project
    artifact mapping. Repeated paths inside one segment-stage aggregate are
    allowed because one batch video can legitimately cover multiple beats.
    """
    if not isinstance(artifacts, Mapping):
        raise StageArtifactValidationError("artifacts must be an object")
    owner_by_path: dict[str, tuple[str, str]] = {}
    for artifact_name in STAGE_ARTIFACT_ORDER:
        artifact = artifacts.get(artifact_name)
        if artifact is None:
            continue
        for path in media_paths_for_artifact(artifact_name, artifact):
            identity = _path_identity(path)
            previous = owner_by_path.get(identity)
            if previous is not None and previous[0] != artifact_name:
                previous_name, previous_path = previous
                raise StageArtifactValidationError(
                    "canonical media path conflict: "
                    f"{previous_name} ({previous_path}) and "
                    f"{artifact_name} ({path}) represent distinct review stages"
                )
            owner_by_path[identity] = (artifact_name, path)
