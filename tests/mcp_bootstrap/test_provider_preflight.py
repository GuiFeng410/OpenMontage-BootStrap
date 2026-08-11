"""Read-only provider and OSS preflight for locked BootStrap projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import openmontage.mcp.bootstrap.server as S
import openmontage.mcp.bootstrap.tools as T


PIXVERSE_MODEL = "pixverse-video-v6.0"
OSS_ENV_KEYS = (
    "OSS_ACCESS_KEY_ID",
    "OSS_ACCESS_KEY_SECRET",
    "ALIYUN_OSS_ACCESS_KEY_ID",
    "ALIYUN_OSS_ACCESS_KEY_SECRET",
    "ALIYUN_OSS_BUCKET",
    "ALIYUN_OSS_REGION",
    "ALIYUN_OSS_ENDPOINT",
    "OSS_SIGNED_URL_EXPIRES_SEC",
)


@pytest.fixture
def sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    for key in OSS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def _write_project(
    root: Path,
    project_id: str,
    *,
    profile: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    video_plan: dict[str, Any] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    materialize_local_images: bool = True,
) -> None:
    project = root / project_id
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": project_id,
                "pipeline_type": "bootstrap-commercial",
                "production_profile": profile or {},
            }
        ),
        encoding="utf-8",
    )
    if brief is not None:
        (artifacts / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    if video_plan is not None:
        (artifacts / "video_plan.json").write_text(
            json.dumps(video_plan), encoding="utf-8"
        )
    if decisions is not None:
        (project / "decision_log.json").write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "project_id": project_id,
                    "decisions": decisions,
                }
            ),
            encoding="utf-8",
        )
    if materialize_local_images and isinstance(video_plan, dict):
        raw_segments = video_plan.get("segments") or video_plan.get("beats") or []
        segments = raw_segments if isinstance(raw_segments, list) else []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            for field in ("image_path", "ref_image", "reference_image", "ref"):
                raw_path = str(segment.get(field) or "").strip()
                if not raw_path or raw_path.lower().startswith(("http://", "https://")):
                    continue
                candidate = Path(raw_path)
                if not candidate.is_absolute():
                    candidate = project / candidate
                try:
                    candidate.resolve().relative_to(
                        (project / "assets" / "images").resolve()
                    )
                except ValueError:
                    continue
                image_format = {
                    ".jpg": "JPEG",
                    ".jpeg": "JPEG",
                    ".png": "PNG",
                    ".webp": "WEBP",
                }.get(candidate.suffix.lower())
                if image_format:
                    _write_valid_image(candidate, image_format)
                break


def _channel(model: str = PIXVERSE_MODEL, channel: str = "tokenhub") -> dict[str, Any]:
    return {
        "theme": "provider preflight",
        "duration_seconds": 5,
        "images": {},
        "channel": {
            "video_channel": channel,
            "video_model": model,
        },
    }


def _upload_decision(selected: str, decision_id: str) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "stage": "brief_locked",
        "category": "asset_decision",
        "subject": "Pixverse local image temporary OSS upload",
        "options_considered": [],
        "selected": selected,
        "reason": "test",
        "user_approved": selected == "approved",
        "user_response_text": "同意临时上传" if selected == "approved" else "不同意上传",
    }


def _preflight(project_id: str) -> dict[str, Any]:
    fn = getattr(T, "produce_provider_preflight", None)
    assert callable(fn), "produce_provider_preflight must be implemented"
    return fn(project_id)


def _configure_oss(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, str, str]:
    values = (
        "TEST_AK_ID_DO_NOT_LEAK",
        "TEST_AK_SECRET_DO_NOT_LEAK",
        "test-private-bucket-do-not-leak",
        "cn-test-region-do-not-leak",
    )
    for key, value in zip(
        (
            "OSS_ACCESS_KEY_ID",
            "OSS_ACCESS_KEY_SECRET",
            "ALIYUN_OSS_BUCKET",
            "ALIYUN_OSS_REGION",
        ),
        values,
        strict=True,
    ):
        monkeypatch.setenv(key, value)
    return values


def _write_valid_image(path: Path, image_format: str = "PNG") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(path, format=image_format)


def test_preflight_is_exposed_on_facade_and_capability_list() -> None:
    assert callable(getattr(T, "produce_provider_preflight", None))
    assert callable(getattr(S, "produce_provider_preflight", None))
    assert "produce_provider_preflight" in T.list_bootstrap_tools()["produce_minimal"]


def test_pixverse_t2v_is_ready_without_oss(sandbox: Path) -> None:
    _write_project(
        sandbox,
        "pixverse-t2v",
        brief=_channel(),
        video_plan={"segments": [{"id": "beat_01", "mode": "t2v"}]},
    )
    result = _preflight("pixverse-t2v")

    assert result["video_channel"] == "tokenhub"
    assert result["video_model"] == PIXVERSE_MODEL
    assert result["modes"] == [
        {"beat_id": "beat_01", "mode": "t2v", "image_source": "none"}
    ]
    assert result["oss_required"] is False
    assert result["oss_configured"] is False
    assert result["ready"] is True
    assert result["blockers"] == []
    serialized = json.dumps(result).lower()
    assert "t2i" not in serialized
    assert "i2i" not in serialized


def test_pixverse_public_i2v_is_ready_without_oss(sandbox: Path) -> None:
    public_url = "https://cdn.example.test/product.png?signature=do-not-return"
    _write_project(
        sandbox,
        "pixverse-public-i2v",
        brief=_channel(),
        video_plan={
            "segments": [
                {"id": "beat_01", "mode": "i2v", "ref_image": public_url}
            ]
        },
    )
    result = _preflight("pixverse-public-i2v")

    assert result["modes"] == [
        {"beat_id": "beat_01", "mode": "i2v", "image_source": "public_url"}
    ]
    assert result["oss_required"] is False
    assert result["ready"] is True
    assert public_url not in json.dumps(result)


@pytest.mark.parametrize(
    ("fixture_kind", "image_path"),
    [
        ("missing", "assets/images/missing.png"),
        ("directory", "assets/images/folder.png"),
        ("json", "assets/images/product.json"),
        ("empty", "assets/images/empty.png"),
        ("forged", "assets/images/forged.png"),
    ],
)
def test_pixverse_local_i2v_rejects_non_reviewable_project_image(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture_kind: str,
    image_path: str,
) -> None:
    _configure_oss(monkeypatch)
    project_id = f"invalid-local-{fixture_kind}"
    _write_project(
        sandbox,
        project_id,
        brief=_channel(),
        video_plan={
            "segments": [
                {"id": "beat_01", "mode": "i2v", "image_path": image_path}
            ]
        },
        decisions=[_upload_decision("approved", "d-invalid")],
        materialize_local_images=False,
    )
    candidate = sandbox / project_id / image_path
    if fixture_kind == "directory":
        candidate.mkdir(parents=True)
    elif fixture_kind == "json":
        candidate.parent.mkdir(parents=True)
        candidate.write_text('{"not":"an image"}', encoding="utf-8")
    elif fixture_kind == "empty":
        candidate.parent.mkdir(parents=True)
        candidate.touch()
    elif fixture_kind == "forged":
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"not-a-real-png")

    result = _preflight(project_id)

    assert result["ready"] is False
    assert result["oss_required"] is False
    assert "image_source_invalid" in {
        item["code"] for item in result["blockers"]
    }


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("ALIYUN_OSS_ENDPOINT", "https://secret-internal.invalid-internal.aliyuncs.com"),
        ("OSS_SIGNED_URL_EXPIRES_SEC", "secret-invalid-expiry"),
    ],
)
def test_pixverse_local_i2v_uses_full_oss_config_validation_without_leaks(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    unsafe_value: str,
) -> None:
    secret_values = _configure_oss(monkeypatch)
    monkeypatch.setenv(field, unsafe_value)
    project_id = f"invalid-oss-{field.lower().replace('_', '-')}"
    image_path = sandbox / project_id / "assets" / "images" / "product.png"
    _write_project(
        sandbox,
        project_id,
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "image_path": "assets/images/product.png",
                }
            ]
        },
        decisions=[_upload_decision("approved", "d-invalid-oss")],
    )
    _write_valid_image(image_path)

    result = _preflight(project_id)
    serialized = json.dumps(result)

    assert result["ready"] is False
    assert result["oss_configured"] is False
    assert [item["code"] for item in result["blockers"]] == [
        "oss_not_configured"
    ]
    assert field in result["invalid_config_fields"]
    assert "invalid_config_fields" in result["next_action_zh"]
    assert unsafe_value not in serialized
    for secret in secret_values:
        assert secret not in serialized


@pytest.mark.parametrize("unsupported_mode", ["t2i", "i2i"])
def test_pixverse_never_claims_image_generation_modes(
    sandbox: Path, unsupported_mode: str
) -> None:
    project_id = f"pixverse-unsupported-{len(unsupported_mode)}-{unsupported_mode[0]}"
    _write_project(
        sandbox,
        project_id,
        brief=_channel(),
        video_plan={
            "segments": [{"id": "beat_01", "mode": unsupported_mode}]
        },
    )
    result = _preflight(project_id)

    assert result["modes"] == []
    assert result["ready"] is False
    assert [item["code"] for item in result["blockers"]] == [
        "pixverse_mode_unsupported"
    ]
    assert all(item["mode"] in {"t2v", "i2v"} for item in result["modes"])


def test_pixverse_local_i2v_blocks_when_oss_is_not_configured(
    sandbox: Path,
) -> None:
    _write_project(
        sandbox,
        "pixverse-local-no-config",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "method": "pixverse_i2v",
                    "ref_image": "assets/images/product.png",
                }
            ]
        },
        decisions=[_upload_decision("approved", "d-001")],
    )
    result = _preflight("pixverse-local-no-config")

    assert result["oss_required"] is True
    assert result["oss_configured"] is False
    assert result["oss_upload_approved"] is True
    assert result["ready"] is False
    assert [item["code"] for item in result["blockers"]] == [
        "oss_not_configured"
    ]


def test_pixverse_local_i2v_blocks_without_project_upload_approval(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_oss(monkeypatch)
    _write_project(
        sandbox,
        "pixverse-local-no-approval",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "image_path": "assets/images/product.png",
                }
            ]
        },
    )
    result = _preflight("pixverse-local-no-approval")

    assert result["oss_required"] is True
    assert result["oss_configured"] is True
    assert result["oss_upload_approved"] is False
    assert result["ready"] is False
    assert [item["code"] for item in result["blockers"]] == [
        "oss_upload_not_approved"
    ]


def test_pixverse_local_i2v_is_ready_with_oss_and_latest_approval(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_oss(monkeypatch)
    _write_project(
        sandbox,
        "pixverse-local-ready",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "ref": "assets/images/product.png",
                }
            ]
        },
        decisions=[
            _upload_decision("denied", "d-001"),
            _upload_decision("approved", "d-002"),
        ],
    )
    result = _preflight("pixverse-local-ready")

    assert result["oss_required"] is True
    assert result["oss_configured"] is True
    assert result["oss_upload_approved"] is True
    assert result["ready"] is True
    assert result["blockers"] == []


def test_pixverse_absolute_current_project_image_requires_oss(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_oss(monkeypatch)
    project_id = "pixverse-absolute-local"
    image_path = sandbox / project_id / "assets" / "images" / "product.png"
    _write_project(
        sandbox,
        project_id,
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "image_path": str(image_path),
                }
            ]
        },
        decisions=[_upload_decision("approved", "d-001")],
    )
    _write_valid_image(image_path)

    result = _preflight(project_id)

    assert result["modes"] == [
        {"beat_id": "beat_01", "mode": "i2v", "image_source": "local_project"}
    ]
    assert result["oss_required"] is True
    assert result["ready"] is True


def test_latest_upload_decision_can_revoke_approval(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_oss(monkeypatch)
    _write_project(
        sandbox,
        "pixverse-local-revoked",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "ref_image": "assets/images/product.png",
                }
            ]
        },
        decisions=[
            _upload_decision("approved", "d-001"),
            _upload_decision("denied", "d-002"),
        ],
    )
    result = _preflight("pixverse-local-revoked")

    assert result["oss_upload_approved"] is False
    assert [item["code"] for item in result["blockers"]] == [
        "oss_upload_not_approved"
    ]


def test_non_pixverse_local_i2v_never_requires_oss(sandbox: Path) -> None:
    _write_project(
        sandbox,
        "agnes-local",
        brief=_channel("agnes-video-v2.0", "agnes"),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "method": "agnes_i2v",
                    "ref_image": "assets/images/product.png",
                }
            ]
        },
    )
    result = _preflight("agnes-local")

    assert result["video_channel"] == "agnes"
    assert result["modes"][0]["mode"] == "i2v"
    assert result["oss_required"] is False
    assert result["ready"] is True


def test_artifacts_override_marker_and_result_never_leaks_oss_secrets(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_values = _configure_oss(monkeypatch)
    _write_project(
        sandbox,
        "artifact-priority",
        profile={
            "video_channel": "agnes",
            "video_model": "agnes-video-v2.0",
        },
        brief=_channel(),
        video_plan={"segments": [{"id": "beat_01", "mode": "t2v"}]},
    )
    result = _preflight("artifact-priority")
    serialized = json.dumps(result)

    assert result["video_channel"] == "tokenhub"
    assert result["video_model"] == PIXVERSE_MODEL
    for secret in secret_values:
        assert secret not in serialized


def test_insufficient_evidence_returns_blockers_without_guessing(
    sandbox: Path,
) -> None:
    _write_project(sandbox, "insufficient")

    result = _preflight("insufficient")

    assert result["provider"] == "unknown"
    assert result["model"] == "unknown"
    assert result["mode"] == "unknown"
    assert result["ready"] is False
    assert {
        "brief_missing",
        "video_plan_missing",
        "video_channel_missing",
        "video_model_missing",
        "video_mode_missing",
    } <= {item["code"] for item in result["blockers"]}
    assert result["next_action_zh"]


def test_pixverse_local_i2v_returns_only_missing_oss_field_names(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "present-but-never-returned")
    _write_project(
        sandbox,
        "missing-oss-fields",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "image_path": "assets/images/product.png",
                }
            ]
        },
        decisions=[_upload_decision("approved", "d-001")],
    )

    result = _preflight("missing-oss-fields")
    serialized = json.dumps(result)

    assert result["missing_config_fields"] == [
        "OSS_ACCESS_KEY_SECRET",
        "ALIYUN_OSS_BUCKET",
        "ALIYUN_OSS_REGION",
    ]
    assert "present-but-never-returned" not in serialized


@pytest.mark.parametrize(
    "image_path",
    [
        "../other-project/secret.png",
        "assets/images/../../other-project/secret.png",
    ],
)
def test_external_or_ambiguous_image_path_is_not_treated_as_project_local(
    sandbox: Path, image_path: str,
) -> None:
    _write_project(
        sandbox,
        "outside-image",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "image_path": image_path,
                }
            ]
        },
    )

    result = _preflight("outside-image")

    assert result["mode"] == "unknown"
    assert result["oss_required"] is False
    assert result["ready"] is False
    assert "image_source_invalid" in {
        item["code"] for item in result["blockers"]
    }


def test_artifact_decision_is_fallback_when_root_has_no_target(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_oss(monkeypatch)
    unrelated = _upload_decision("denied", "d-root-unrelated")
    unrelated["subject"] = "Different asset decision"
    _write_project(
        sandbox,
        "artifact-decision",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "ref_image": "assets/images/product.png",
                }
            ]
        },
        decisions=[unrelated],
    )
    project = sandbox / "artifact-decision"
    (project / "artifacts" / "decision_log.json").write_text(
        json.dumps(
            {
                "decisions": [_upload_decision("approved", "d-artifact")],
                "api_key": "must-not-leak",
            }
        ),
        encoding="utf-8",
    )

    result = _preflight("artifact-decision")

    assert result["upload_consent"] is True
    assert result["ready"] is True
    assert "must-not-leak" not in json.dumps(result)
    assert "image provider" in result["capability_note_zh"]


def test_rematerialized_old_artifact_cannot_override_root_denial(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_oss(monkeypatch)
    _write_project(
        sandbox,
        "rematerialized-artifact",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "ref_image": "assets/images/product.png",
                }
            ]
        },
        decisions=[
            _upload_decision("approved", "d-root-old"),
            _upload_decision("denied", "d-root-new"),
        ],
    )
    project = sandbox / "rematerialized-artifact"
    (project / "artifacts" / "decision_log.json").write_text(
        json.dumps(
            {"decisions": [_upload_decision("approved", "d-artifact-old")]}
        ),
        encoding="utf-8",
    )

    result = _preflight("rematerialized-artifact")

    assert result["upload_consent"] is False
    assert result["ready"] is False
    assert "oss_upload_not_approved" in {
        item["code"] for item in result["blockers"]
    }


def test_decision_logs_merge_and_later_root_denial_wins(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_oss(monkeypatch)
    approved = _upload_decision("approved", "d-artifact-old")
    approved["decided_at"] = "2026-08-11T08:00:00+00:00"
    denied = _upload_decision("denied", "d-root-new")
    denied["decided_at"] = "2026-08-11T09:00:00+00:00"
    _write_project(
        sandbox,
        "merged-decisions",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "ref_image": "assets/images/product.png",
                }
            ]
        },
        decisions=[denied],
    )
    project = sandbox / "merged-decisions"
    (project / "artifacts" / "decision_log.json").write_text(
        json.dumps({"decisions": [approved]}),
        encoding="utf-8",
    )

    result = _preflight("merged-decisions")

    assert result["upload_consent"] is False
    assert result["ready"] is False
    assert "oss_upload_not_approved" in {
        item["code"] for item in result["blockers"]
    }


@pytest.mark.parametrize(
    "decision_patch",
    [
        {"user_approved": False},
        {"user_response_text": ""},
        {"user_response_text": "   "},
    ],
)
def test_upload_approval_requires_flag_and_nonempty_user_response(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision_patch: dict[str, Any],
) -> None:
    _configure_oss(monkeypatch)
    decision = _upload_decision("approved", "d-invalid-approval")
    decision.update(decision_patch)
    _write_project(
        sandbox,
        f"approval-fields-{len(str(decision_patch))}",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    "ref_image": "assets/images/product.png",
                }
            ]
        },
        decisions=[decision],
    )
    project_id = f"approval-fields-{len(str(decision_patch))}"

    result = _preflight(project_id)

    assert result["upload_consent"] is False
    assert result["ready"] is False
    assert "oss_upload_not_approved" in {
        item["code"] for item in result["blockers"]
    }


@pytest.mark.parametrize(
    "field",
    ["image_path", "ref_image", "reference_image", "ref"],
)
def test_all_local_aliases_reject_path_traversal(
    sandbox: Path, field: str
) -> None:
    _write_project(
        sandbox,
        f"traversal-{field}",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    field: "../assets/images/product.png",
                }
            ]
        },
    )

    result = _preflight(f"traversal-{field}")

    assert result["mode"] == "unknown"
    assert result["oss_required"] is False
    assert result["ready"] is False
    assert "image_source_invalid" in {
        item["code"] for item in result["blockers"]
    }


@pytest.mark.parametrize(
    "field",
    ["image_path", "ref_image", "reference_image", "ref"],
)
def test_all_local_aliases_accept_absolute_current_project_image(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    _configure_oss(monkeypatch)
    project_id = f"absolute-alias-{field}"
    image_path = sandbox / project_id / "assets" / "images" / "product.png"
    _write_project(
        sandbox,
        project_id,
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "mode": "i2v",
                    field: str(image_path),
                }
            ]
        },
        decisions=[_upload_decision("approved", "d-absolute")],
    )

    result = _preflight(project_id)

    assert result["mode"] == "i2v_local"
    assert result["oss_required"] is True
    assert result["ready"] is True


def test_image_reference_without_explicit_video_mode_is_blocked(
    sandbox: Path,
) -> None:
    _write_project(
        sandbox,
        "image-without-mode",
        brief=_channel(),
        video_plan={
            "segments": [
                {
                    "id": "beat_01",
                    "ref_image": "assets/images/product.png",
                }
            ]
        },
    )

    result = _preflight("image-without-mode")

    assert result["modes"] == []
    assert result["mode"] == "unknown"
    assert result["oss_required"] is False
    assert result["ready"] is False
    assert "video_mode_missing" in {
        item["code"] for item in result["blockers"]
    }


def test_pixverse_is_normalized_from_provider_and_model_alias(
    sandbox: Path,
) -> None:
    _write_project(
        sandbox,
        "pixverse-alias",
        brief={
            "selected_video": {
                "provider": "Pixverse",
                "model": "v6",
            }
        },
        video_plan={"segments": [{"id": "beat_01", "capability": "t2v"}]},
    )

    result = _preflight("pixverse-alias")

    assert result["provider"] == "pixverse"
    assert result["video_channel"] == "Pixverse"
    assert result["video_model"] == "v6"
    assert result["mode"] == "t2v"
    assert result["ready"] is True
