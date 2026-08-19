from __future__ import annotations

from copy import deepcopy

import pytest

from lib.board_stage_artifacts import (
    StageArtifactValidationError,
    build_final_review,
    build_full_draft_pro,
    build_review_overview,
    build_sample_reel,
    media_paths_for_artifact,
    validate_relative_media_path,
    validate_stage_artifact,
    validate_stage_artifact_set,
)
from schemas.artifacts import validate_artifact


def _final(path: str = "renders/final.mp4") -> dict:
    return build_final_review(
        path,
        status="pass",
        checks={"technical_probe": {"valid_container": True}},
        recommended_action="present_to_user",
    )


def test_sample_builder_preserves_relative_path_and_supports_run_metadata() -> None:
    path = "assets/video/sample_r2.mp4"
    artifact = build_sample_reel(
        path,
        ["beat_02"],
        duration_seconds=12.5,
        extra={
            "provider": "locked-provider",
            "model": "locked-model",
            "artifact_revision": "sample-r2",
            "cost_snapshot": {"actual": 1.25},
        },
    )

    assert artifact["path"] == path
    assert artifact["beat_ids"] == ["beat_02"]
    assert artifact["artifact_revision"] == "sample-r2"
    validate_artifact("sample_reel", artifact)


@pytest.mark.parametrize(
    "path",
    [
        "C:/project/sample.mp4",
        "C:project/sample.mp4",
        "/project/sample.mp4",
        "../sample.mp4",
        "assets/video/../../sample.mp4",
        "https://example.test/sample.mp4",
        "assets/video/sample.png",
        " assets/video/sample.mp4",
    ],
)
def test_relative_media_path_rejects_noncanonical_paths(path: str) -> None:
    with pytest.raises(StageArtifactValidationError):
        validate_relative_media_path(path)


def test_sample_requires_nonempty_unique_beat_ids() -> None:
    with pytest.raises(StageArtifactValidationError, match="at least one"):
        build_sample_reel("assets/video/sample.mp4", [])
    with pytest.raises(StageArtifactValidationError, match="duplicates"):
        build_sample_reel("assets/video/sample.mp4", ["beat_01", "beat_01"])


def test_review_overview_builder_is_nonmutating_and_preserves_paths() -> None:
    rows = [{
        "beat": "beat_01",
        "time": "0-4",
        "output_path": "assets/video/beat_01.MP4",
    }]
    before = deepcopy(rows)

    artifact = build_review_overview(rows, batches=[], review_mode="normal")

    assert rows == before
    assert artifact["overview"][0]["output_path"] == rows[0]["output_path"]
    assert media_paths_for_artifact("review_overview", artifact) == (
        "assets/video/beat_01.MP4",
    )
    validate_artifact("review_overview", artifact)


def test_review_overview_allows_reference_only_batch_for_legacy_compatibility() -> None:
    artifact = build_review_overview(
        [],
        batches=[{"id": "batch_01", "span": "0-8"}],
        review_mode="pro",
    )

    assert artifact["batches"] == [{"id": "batch_01", "span": "0-8"}]
    assert media_paths_for_artifact("review_overview", artifact) == ()


def test_full_draft_builder_materializes_user_visible_review_lists() -> None:
    artifact = build_full_draft_pro(
        "renders/draft_r3.mp4",
        issue_segments=[{"beat": "beat_02", "issue": "slow pacing"}],
        modification_list=["shorten beat_02"],
        cuts_revision="cuts-r3",
        extra={"cost_snapshot": {"actual": 3.5}},
    )

    assert artifact["path"] == "renders/draft_r3.mp4"
    assert artifact["issue_segments"][0]["beat"] == "beat_02"
    assert artifact["modification_list"] == ["shorten beat_02"]
    validate_artifact("full_draft_pro", artifact)


def test_full_draft_rejects_string_as_modification_list() -> None:
    with pytest.raises(StageArtifactValidationError, match="iterable of strings"):
        build_full_draft_pro(
            "renders/draft.mp4",
            modification_list="shorten beat_02",
        )


def test_final_review_builder_supplies_all_required_check_sections() -> None:
    checks = {"technical_probe": {"valid_container": True}}
    artifact = build_final_review(
        "renders/final_candidate_r4.mp4",
        status="pass",
        checks=checks,
        metadata={"candidate_revision": "r4"},
    )

    assert checks == {"technical_probe": {"valid_container": True}}
    assert set(artifact["checks"]) >= {
        "technical_probe",
        "visual_spotcheck",
        "audio_spotcheck",
        "promise_preservation",
        "subtitle_check",
    }
    assert artifact["output_path"] == "renders/final_candidate_r4.mp4"
    validate_artifact("final_review", artifact)


def test_final_review_rejects_unknown_status_via_existing_schema() -> None:
    with pytest.raises(StageArtifactValidationError, match="schema validation"):
        build_final_review("renders/final.mp4", status="approved")


def test_extra_fields_cannot_override_canonical_builder_fields() -> None:
    with pytest.raises(StageArtifactValidationError, match="protected fields"):
        build_sample_reel(
            "assets/video/sample.mp4",
            ["beat_01"],
            extra={"path": "renders/final.mp4"},
        )


@pytest.mark.parametrize(
    ("earlier_name", "earlier", "later_name", "later"),
    [
        (
            "sample_reel",
            build_sample_reel("assets/video/shared.mp4", ["beat_01"]),
            "review_overview",
            build_review_overview([{
                "beat": "beat_01",
                "output_path": "assets/video/shared.mp4",
            }]),
        ),
        (
            "review_overview",
            build_review_overview([{
                "beat": "beat_01",
                "output_path": "assets/video/shared.mp4",
            }]),
            "full_draft_pro",
            build_full_draft_pro("assets/video/shared.mp4"),
        ),
        (
            "full_draft_pro",
            build_full_draft_pro("renders/shared.mp4"),
            "final_review",
            _final("renders/shared.mp4"),
        ),
    ],
)
def test_artifact_set_rejects_media_impersonating_multiple_review_stages(
    earlier_name: str,
    earlier: dict,
    later_name: str,
    later: dict,
) -> None:
    with pytest.raises(StageArtifactValidationError, match="distinct review stages"):
        validate_stage_artifact_set({earlier_name: earlier, later_name: later})


def test_path_conflicts_use_normalized_case_insensitive_identity() -> None:
    sample = build_sample_reel("assets/video/SHARED.mp4", ["beat_01"])
    draft = build_full_draft_pro("assets\\video\\.\\shared.mp4")

    with pytest.raises(StageArtifactValidationError, match="canonical media path conflict"):
        validate_stage_artifact_set({
            "sample_reel": sample,
            "full_draft_pro": draft,
        })


def test_repeated_path_inside_one_segment_stage_is_allowed() -> None:
    overview = build_review_overview([
        {"beat": "beat_01", "output_path": "assets/video/batch_01.mp4"},
        {"beat": "beat_02", "output_path": "assets/video/batch_01.mp4"},
    ])

    validate_stage_artifact_set({"review_overview": overview})
    assert media_paths_for_artifact("review_overview", overview) == (
        "assets/video/batch_01.mp4",
    )


def test_distinct_stage_paths_accept_full_project_artifact_mapping() -> None:
    artifacts = {
        "brief": {"theme": "ignored"},
        "sample_reel": build_sample_reel(
            "assets/video/sample.mp4",
            ["beat_01"],
        ),
        "review_overview": build_review_overview([{
            "beat": "beat_01",
            "output_path": "assets/video/beat_01.mp4",
        }]),
        "full_draft_pro": build_full_draft_pro("renders/draft.mp4"),
        "final_review": _final(),
    }

    validate_stage_artifact_set(artifacts)


def test_direct_validator_rejects_unknown_artifact_name() -> None:
    with pytest.raises(StageArtifactValidationError, match="unsupported"):
        validate_stage_artifact("brief", {"theme": "ignored"})
