"""Unit tests for Backlot BoardState derivation (backlot/state.py)."""

import json
import time
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

from backlot import state as state_mod
from backlot.state import list_projects, load_board_state, summarize_project
from lib.asset_precheck import build_asset_ledger
from lib.edit_apply import cuts_digest


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", root)
    return root


def _make_project(root: Path, pid: str) -> Path:
    p = root / pid
    (p / "artifacts").mkdir(parents=True)
    (p / "assets" / "images").mkdir(parents=True)
    (p / "renders").mkdir()
    return p


def _write(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def _make_six_beat_legacy_assignment_project(root: Path) -> Path:
    p = _make_project(root, "commercial-six-beat-legacy-assignment")
    _write(p / "project.json", {
        "project_id": p.name,
        "pipeline_type": "bootstrap-commercial",
        "production_profile": {"duration_seconds": 30},
    })
    for index in range(1, 6):
        (p / "assets" / "images" / f"{index:02d}.png").write_bytes(b"image")
    _write(p / "artifacts" / "video_plan.json", {
        "segments": [
            {"id": f"S{index}", "t": f"{(index - 1) * 5}-{index * 5}"}
            for index in range(1, 7)
        ],
    })
    _write(p / "artifacts" / "segment_cards.json", {
        "duration_seconds": 30,
        "segments": [
            {"beat": f"S{index}", "time": f"{(index - 1) * 5}-{index * 5}"}
            for index in range(1, 7)
        ],
    })
    _write(p / "artifacts" / "asset_ledger.json", {
        "entries": [
            {
                "file": "01.png",
                "path": "assets/images/01.png",
                "kind": "image",
                "beat": "S1,S4",
                "selected": True,
            },
            {
                "file": "02.png",
                "path": "assets/images/02.png",
                "kind": "image",
                "beat": "S2,S6",
                "selected": True,
            },
            {
                "file": "03.png",
                "path": "assets/images/03.png",
                "kind": "image",
                "beat": "S5",
                "selected": True,
            },
            {
                "file": "04.png",
                "path": "assets/images/04.png",
                "kind": "image",
                "beat": "S3",
                "selected": True,
            },
            {
                "file": "05.png",
                "path": "assets/images/05.png",
                "kind": "image",
                "selected": False,
            },
        ],
    })
    return p


SCENE_PLAN = {
    "version": "1.0",
    "scenes": [
        {"id": "sc1", "type": "generated", "description": "opening",
         "start_seconds": 0, "end_seconds": 4, "script_section_id": "s1",
         "hero_moment": False},
        {"id": "sc2", "type": "generated", "description": "climax",
         "start_seconds": 4, "end_seconds": 10, "hero_moment": True},
    ],
}

SCRIPT = {
    "version": "1.0", "title": "Test Film", "total_duration_seconds": 10,
    "sections": [
        {"id": "s1", "text": "It begins.", "start_seconds": 0, "end_seconds": 4},
        {"id": "s2", "text": "It ends.", "start_seconds": 4, "end_seconds": 10},
    ],
}


class TestBoardState:
    def test_full_project(self, projects_root):
        p = _make_project(projects_root, "film")
        _write(p / "project.json", {"project_id": "film", "title": "My Film",
                                    "pipeline_type": "cinematic", "created_at": "2026-01-01T00:00:00Z"})
        _write(p / "artifacts" / "scene_plan.json", SCENE_PLAN)
        _write(p / "artifacts" / "script.json", SCRIPT)
        img = p / "assets" / "images" / "sc1.png"
        img.write_bytes(b"fake")
        _write(p / "artifacts" / "asset_manifest.json", {
            "version": "1.0",
            "assets": [
                {"id": "a1", "type": "image", "path": "assets/images/sc1.png",
                 "scene_id": "sc1", "source_tool": "t", "cost_usd": 0.1},
                {"id": "a2", "type": "image", "path": "assets/images/missing.png",
                 "scene_id": "sc2", "source_tool": "t"},
            ],
            "total_cost_usd": 0.1,
        })
        _write(p / "checkpoint_script.json", {
            "version": "1.0", "project_id": "film", "pipeline_type": "cinematic",
            "stage": "script", "status": "completed", "timestamp": "2026-01-01T01:00:00Z",
            "human_approved": True, "artifacts": {},
        })

        s = load_board_state(p)
        assert s["title"] == "My Film"
        assert s["pipeline"]["pipeline_type"] == "cinematic"
        assert s["pipeline"]["known"] is True
        board = s["storyboard"]
        assert len(board["scenes"]) == 2
        sc1, sc2 = board["scenes"]
        assert sc1["narration"] == "It begins."
        assert sc1["visual"]["exists"] is True
        # sc2 has no script_section_id -> joined by timing overlap
        assert sc2["narration"] == "It ends."
        assert sc2["hero_moment"] is True
        assert sc2["visual"]["exists"] is False  # missing file flagged
        script_stage = next(x for x in s["stages"] if x["name"] == "script")
        assert script_stage["status"] == "completed"

    def test_gate_skip_detection(self, projects_root):
        p = _make_project(projects_root, "sneaky")
        # completed on a gated stage with no awaiting_human history and no
        # human_approved -> gate_skipped flag
        _write(p / "checkpoint_script.json", {
            "version": "1.0", "project_id": "sneaky", "pipeline_type": "cinematic",
            "stage": "script", "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        s = load_board_state(p)
        script_stage = next(x for x in s["stages"] if x["name"] == "script")
        assert script_stage["gate_skipped"] is True

        # with an archived awaiting_human version, the gate was honored
        _write(p / "history" / "checkpoint_script_20260101.json", {
            "stage": "script", "status": "awaiting_human",
        })
        s2 = load_board_state(p)
        script_stage2 = next(x for x in s2["stages"] if x["name"] == "script")
        assert script_stage2["gate_skipped"] is False

    def test_generating_state_from_events(self, projects_root):
        p = _make_project(projects_root, "live")
        _write(p / "artifacts" / "scene_plan.json", SCENE_PLAN)
        events = [
            {"ts": "t1", "tool": "img", "event": "start", "scene_id": "sc1"},
            {"ts": "t2", "tool": "img", "event": "finish", "scene_id": "sc1"},
            {"ts": "t3", "tool": "img", "event": "start", "scene_id": "sc2"},
        ]
        (p / "events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        s = load_board_state(p)
        cards = {c["id"]: c for c in s["storyboard"]["scenes"]}
        assert cards["sc1"]["generating"] is False
        assert cards["sc2"]["generating"] is True
        assert cards["sc2"]["generating_tool"] == "img"

    def test_degraded_project_never_crashes(self, projects_root):
        p = projects_root / "bare"
        p.mkdir()
        (p / "something.mp4").write_bytes(b"x")
        (p / "artifacts").mkdir()
        (p / "artifacts" / "script.json").write_text("NOT JSON", encoding="utf-8")
        s = load_board_state(p)
        assert s["has_pipeline_state"] is False
        assert s["storyboard"] is None
        assert s["media"]["renders"][0]["path"] == "something.mp4"
        assert s["media"]["renders"][0]["at_root"] is True

    def test_undeclared_stage_surfaces(self, projects_root):
        p = _make_project(projects_root, "legacy")
        _write(p / "checkpoint_idea.json", {
            "version": "1.0", "project_id": "legacy", "pipeline_type": "cinematic",
            "stage": "idea", "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        s = load_board_state(p)
        idea = next(x for x in s["stages"] if x["name"] == "idea")
        assert idea.get("undeclared") is True

    def test_commercial_intermediate_decision_and_dynamic_batch(self, projects_root):
        p = _make_project(projects_root, "commercial")
        _write(p / "project.json", {
            "project_id": "commercial",
            "title": "商品测试",
            "pipeline_type": "bootstrap-commercial",
            "production_profile": {"review_mode": "pro", "duration_seconds": 60},
        })
        _write(p / "artifacts" / "brief.json", {
            "theme": "商品测试",
            "duration_seconds": 60,
            "images": {
                "detail.png": {"path": "assets/images/detail.png", "role": "product_detail"},
            },
        })
        _write(p / "artifacts" / "asset_precheck.json", {
            "version": "1.0",
            "entries": [
                {
                    "file": "detail.png",
                    "path": "assets/images/detail.png",
                    "suggested_class": "product_detail",
                    "issues": [],
                }
            ],
            "summary": {
                "total_images": 1,
                "low_resolution_count": 0,
                "duplicate_group_count": 0,
                "needs_user_attention": False,
            },
        })
        _write(p / "artifacts" / "review_overview.json", {
            "review_mode": "pro",
            "overview": [{"beat": "beat_01", "time": "00:00-00:20"}],
            "batches": [{"id": "batch_03", "span": "00:40-01:00"}],
        })
        _write(p / "artifacts" / "batch03_review.json", {
            "batch_id": "batch_03", "status": "in_review",
        })
        (p / "renders" / "batch03_40_60.mp4").write_bytes(b"video")
        _write(p / "checkpoint_sample_review.json", {
            "version": "1.0",
            "project_id": "commercial",
            "pipeline_type": "bootstrap-commercial",
            "stage": "sample_review",
            "status": "in_progress",
            "timestamp": "2026-08-07T10:00:00Z",
            "artifacts": {},
            "metadata": {
                "needs_user_decision": True,
                "decision_title_zh": "试片是否通过",
                "decision_prompt_zh": "请选择是否继续",
                "decision_options": [{"id": "continue", "label_zh": "继续"}],
            },
        })

        state = load_board_state(p)
        commercial = state["commercial"]
        assert commercial["decision"]["title_zh"] == "试片是否通过"
        assert commercial["decision"]["options"][0]["id"] == "continue"
        assert commercial["assets"][0]["role_zh"] == "细节图"
        assert commercial["asset_precheck"]["summary"]["total_images"] == 1
        assert commercial["asset_precheck"]["entries"][0]["suggested_class"] == "product_detail"
        assert "batch_03" in commercial["batch_reviews"]
        assert commercial["players"][0]["label"] == "第3批预览"

    def test_commercial_state_keeps_legacy_checkpoints_out_of_seven_stage_rail(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-evidence")
        _write(p / "project.json", {
            "project_id": "commercial-evidence",
            "title": "七阶段证据",
            "pipeline_type": "bootstrap-commercial",
            "production_profile": {"duration_seconds": 10},
        })
        for name in (
            "brief_locked",
            "assets_gate",
            "sample_review",
            "segment_build",
            "draft_review",
            "final_compose",
            "delivery_signoff",
        ):
            _write(p / f"checkpoint_{name}.json", {
                "version": "1.0",
                "project_id": "commercial-evidence",
                "pipeline_type": "bootstrap-commercial",
                "stage": name,
                "status": "completed",
                "timestamp": "2026-08-10T10:00:00Z",
                "artifacts": {},
            })
        for legacy in ("sample_gate", "full_production"):
            _write(p / f"checkpoint_{legacy}.json", {
                "version": "1.0",
                "project_id": "commercial-evidence",
                "pipeline_type": "bootstrap-commercial",
                "stage": legacy,
                "status": "completed",
                "timestamp": "2026-08-10T10:00:00Z",
                "artifacts": {},
            })

        for rel in (
            "assets/video/sample.mp4",
            "assets/video/beat_01.mp4",
            "assets/images/reference.png",
            "renders/draft.mp4",
            "renders/final.mp4",
        ):
            media = p / rel
            media.parent.mkdir(parents=True, exist_ok=True)
            media.write_bytes(b"video")

        _write(p / "artifacts" / "video_plan.json", {
            "version": "1.0",
            "segments": [{
                "id": "beat_01",
                "t": "00:00-00:10",
                "purpose": "商品亮相",
                "method": "慢推镜",
                "ref_image": "assets/images/reference.png",
            }],
        })
        _write(p / "artifacts" / "sample_reel.json", {
            "version": "1.0",
            "path": "assets/video/sample.mp4",
            "duration_seconds": 5,
            "status": "approved",
            "user_confirmation_text": "试片通过，继续全片。",
        })
        _write(p / "artifacts" / "full_draft_pro.json", {
            "version": "1.0",
            "path": "renders/draft.mp4",
            "status": "review",
            "issue_segments": [{
                "beat": "beat_01",
                "time": "00:02-00:04",
                "issue_zh": "高光过曝",
            }],
            "modification_list": ["降低高光，保留镜头节奏"],
        })
        _write(p / "artifacts" / "final_review.json", {
            "version": "1.0",
            "output_path": "renders/final.mp4",
            "status": "pass",
            "checks": {
                "technical_probe": {
                    "duration_seconds": 10,
                    "resolution": "1080x1920",
                    "fps": 30,
                    "has_audio": True,
                    "issues": [],
                },
                "visual_spotcheck": {},
                "audio_spotcheck": {},
                "promise_preservation": {},
                "subtitle_check": {},
            },
        })
        _write(p / "artifacts" / "decision_log.json", {
            "version": "1.0",
            "decisions": [{
                "category": "delivery_signoff",
                "subject": "最终交付",
                "selected": "confirmed",
                "user_response_text": "确认交付",
            }],
        })

        state = load_board_state(p)
        commercial = state["commercial"]

        assert [stage["name"] for stage in state["stages"]] == [
            "brief_locked",
            "assets_gate",
            "sample_review",
            "segment_build",
            "draft_review",
            "final_compose",
            "delivery_signoff",
        ]
        assert [item["stage"] for item in commercial["legacy_checkpoints"]] == [
            "full_production",
            "sample_gate",
        ]
        assert commercial["beats"][0]["time"] == "00:00-00:10"
        assert commercial["beats"][0]["reference_path"] == "assets/images/reference.png"
        assert commercial["stage_evidence"]["sample"]["path"] == "assets/video/sample.mp4"
        assert commercial["stage_evidence"]["sample"]["user_confirmation_text"] == "试片通过，继续全片。"
        assert commercial["stage_evidence"]["draft"]["path"] == "renders/draft.mp4"
        assert commercial["stage_evidence"]["draft"]["issue_segments"][0]["beat"] == "beat_01"
        assert commercial["stage_evidence"]["compose"]["path"] == "renders/final.mp4"
        assert commercial["stage_evidence"]["delivery"]["decision"] == "confirmed"

    def test_commercial_missing_media_never_becomes_playable_path(self, projects_root):
        p = _make_project(projects_root, "commercial-missing-media")
        _write(p / "project.json", {
            "project_id": "commercial-missing-media",
            "title": "缺失媒体",
            "pipeline_type": "bootstrap-commercial",
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "version": "1.0",
            "duration_seconds": 5,
            "overall_prompt_zh": "商品亮相",
            "segments": [{
                "beat": "beat_01",
                "time": "0-5",
                "copy_plan_zh": "商品亮相",
                "shot_plan_zh": "慢推",
                "asset_plan_zh": "使用试片",
            }],
        })
        _write(p / "artifacts" / "review_overview.json", {
            "overview": [{
                "beat": "beat_01",
                "time": "0-5",
                "asset": "missing-beat.mp4",
            }],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "beat_01",
                "kind": "video",
                "path": "assets/video/missing-ledger.mp4",
                "selected": True,
            }],
        })
        _write(p / "artifacts" / "sample_reel.json", {
            "path": "assets/video/missing-sample.mp4",
            "status": "review",
        })
        _write(p / "checkpoint_sample_review.json", {
            "stage": "sample_review",
            "status": "in_progress",
            "timestamp": "2026-08-11T00:00:00Z",
            "artifacts": {},
        })

        commercial = load_board_state(p)["commercial"]
        beat = commercial["beats"][0]

        assert beat["asset_path"] is None
        assert beat["asset_missing_path"] == "missing-beat.mp4"
        assert beat["ledger"][0]["exists"] is False
        assert commercial["stage_evidence"]["sample"]["exists"] is False
        assert commercial["stage_evidence"]["sample"]["path"] is None
        assert commercial["stage_evidence"]["sample"]["missing_path"] == (
            "assets/video/missing-sample.mp4"
        )

    def test_commercial_beat_join_uses_overview_id_and_merges_plan_sources(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-beat-join")
        _write(p / "project.json", {
            "project_id": "commercial-beat-join",
            "title": "Beat 合并",
            "pipeline_type": "bootstrap-commercial",
        })
        _write(p / "artifacts" / "video_plan.json", {
            "version": "1.0",
            "segments": [{
                "id": "beat_01",
                "t": "00:00-00:05",
                "method": "视频生成",
                "provider": "fal",
                "model": "kling-v2.1",
                "video_prompt_zh": "保持商品身份，轻微环绕",
                "purpose": "建立商品身份",
            }],
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "version": "1.0",
            "segments": [{
                "beat": "beat_01",
                "copy_plan_zh": "五秒建立核心卖点",
                "shot_plan_zh": "中景环绕后推近",
                "generation_prompt_zh": "保持材质与标识，柔和运镜",
            }],
        })
        _write(p / "artifacts" / "review_overview.json", {
            "version": "1.0",
            "overview": [{
                "id": "beat_01",
                "status": "可以",
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["beat"] == "beat_01"
        assert beat["time"] == "00:00-00:05"
        assert beat["copy_plan_zh"] == "五秒建立核心卖点"
        assert beat["shot_plan_zh"] == "中景环绕后推近"
        assert beat["asset_plan_zh"] == "建立商品身份"
        assert beat["generation_prompt_zh"] == "保持材质与标识，柔和运镜"
        assert beat["method"] == "视频生成"
        assert beat["provider"] == "fal"
        assert beat["model"] == "kling-v2.1"

    def test_commercial_stage_evidence_keeps_artifact_path_and_labels_legacy_candidates(
        self, projects_root
    ):
        linked = _make_project(projects_root, "commercial-linked-evidence")
        _write(linked / "project.json", {
            "project_id": "commercial-linked-evidence",
            "pipeline_type": "bootstrap-commercial",
        })
        linked_sample = linked / "renders" / "linked_sample.mp4"
        linked_sample.write_bytes(b"video")
        _write(linked / "artifacts" / "sample_reel.json", {
            "path": "renders/linked_sample.mp4",
            "status": "review",
        })

        linked_evidence = load_board_state(linked)["commercial"]["stage_evidence"]["sample"]
        assert linked_evidence["artifact_path"] == "artifacts/sample_reel.json"
        assert linked_evidence["path"] == "renders/linked_sample.mp4"
        assert linked_evidence["evidence_attached"] is True
        assert linked_evidence["candidate"] is None

        legacy = _make_project(projects_root, "commercial-legacy-candidates")
        _write(legacy / "project.json", {
            "project_id": "commercial-legacy-candidates",
            "pipeline_type": "bootstrap-commercial",
        })
        (legacy / "renders" / "legacy_sample_preview.mp4").write_bytes(b"video")
        (legacy / "renders" / "legacy_full_draft_preview.mp4").write_bytes(b"video")

        legacy_evidence = load_board_state(legacy)["commercial"]["stage_evidence"]
        assert legacy_evidence["sample"]["path"] is None
        assert legacy_evidence["sample"]["evidence_attached"] is False
        assert legacy_evidence["sample"]["candidate"]["path"] == (
            "renders/legacy_sample_preview.mp4"
        )
        assert legacy_evidence["draft"]["path"] is None
        assert legacy_evidence["draft"]["evidence_attached"] is False
        assert legacy_evidence["draft"]["candidate"]["path"] == (
            "renders/legacy_full_draft_preview.mp4"
        )

    def test_commercial_groups_real_asset_ledger_entries_into_beats(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-ledger-groups")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        hero_path = "assets/images/hero.png"
        (p / hero_path).write_bytes(b"image")
        ledger = build_asset_ledger(
            project_id=p.name,
            precheck={
                "entries": [{
                    "file": "hero.png",
                    "path": hero_path,
                    "suggested_class": "product_hero",
                    "beat": "beat_01",
                    "kind": "image",
                    "origin": "user_upload",
                    "selected": True,
                    "label_zh": "商品身份主图",
                }]
            },
            user_classes={hero_path: "product_hero"},
        )
        _write(p / "artifacts" / "asset_ledger.json", ledger)
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })

        beats = {
            beat["beat"]: beat
            for beat in load_board_state(p)["commercial"]["beats"]
        }

        assert beats["beat_01"]["ledger"][0]["origin"] == "user_upload"
        assert beats["beat_01"]["ledger"][0]["path"] == hero_path

    def test_commercial_groups_planned_ledger_entries_into_beats(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-planned-ledger-groups")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        planned = {
            "beat": "beat_02",
            "kind": "video",
            "status": "generating",
            "source_paths": ["assets/images/hero.png"],
            "prompt_zh": "展示商品细节",
            "planned_output_path": "assets/video/beat_02.mp4",
            "output_path": "",
        }
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [],
            "planned_entries": [planned],
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_02", "time": "4-8"}],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["planned_entries"] == [planned]

    def test_commercial_legacy_multi_beat_assignment_keeps_only_canonical_six_cards(
        self, projects_root
    ):
        p = _make_six_beat_legacy_assignment_project(projects_root)

        beats = load_board_state(p)["commercial"]["beats"]

        assert [beat["beat"] for beat in beats] == [
            "S1", "S2", "S3", "S4", "S5", "S6",
        ]

    def test_commercial_legacy_multi_beat_assignment_reuses_each_real_image(
        self, projects_root
    ):
        p = _make_six_beat_legacy_assignment_project(projects_root)

        beats = {
            beat["beat"]: beat
            for beat in load_board_state(p)["commercial"]["beats"]
        }

        assert [item["path"] for item in beats["S1"]["ledger"]] == [
            "assets/images/01.png",
        ]
        assert [item["path"] for item in beats["S4"]["ledger"]] == [
            "assets/images/01.png",
        ]
        assert [item["path"] for item in beats["S2"]["ledger"]] == [
            "assets/images/02.png",
        ]
        assert [item["path"] for item in beats["S6"]["ledger"]] == [
            "assets/images/02.png",
        ]

    def test_commercial_unassigned_real_image_is_reported_as_unused_asset(
        self, projects_root
    ):
        p = _make_six_beat_legacy_assignment_project(projects_root)

        unused = load_board_state(p)["commercial"]["unused_assets"]

        assert [item["path"] for item in unused] == ["assets/images/05.png"]

    def test_commercial_reused_plan_reference_without_ledger_mapping_is_explicit(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-jade-reference-drift")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
            "production_profile": {"duration_seconds": 30},
        })
        for index in range(1, 6):
            (p / "assets" / "images" / f"{index:02d}.png").write_bytes(b"image")
        _write(p / "artifacts" / "video_plan.json", {
            "segments": [
                {
                    "id": f"beat_{index:02d}",
                    "t": f"{(index - 1) * 5}-{index * 5}",
                    "ref": (
                        "assets/images/01.png"
                        if index == 6
                        else f"assets/images/{index:02d}.png"
                    ),
                }
                for index in range(1, 7)
            ],
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "duration_seconds": 30,
            "segments": [
                {
                    "beat": f"beat_{index:02d}",
                    "time": f"{(index - 1) * 5}-{index * 5}",
                }
                for index in range(1, 7)
            ],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [
                {
                    "file": f"{index:02d}.png",
                    "path": f"assets/images/{index:02d}.png",
                    "kind": "image",
                    "beat": f"beat_{index:02d}",
                    "selected": True,
                }
                for index in range(1, 6)
            ],
        })

        beats = load_board_state(p)["commercial"]["beats"]
        beat_06 = next(beat for beat in beats if beat["beat"] == "beat_06")

        assert len(beats) == 6
        assert beat_06["reference_path"] == "assets/images/01.png"
        assert beat_06["ledger"] == []
        assert beat_06["assignment_status"] == "missing"
        assert beat_06["need_count"] == 1
        assert beat_06["have_count"] == 0
        assert beat_06["assignment_warnings"]

    def test_commercial_legacy_ready_user_upload_stays_user_asset(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-ready-user-upload")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        image_path = "assets/images/hero.png"
        (p / image_path).write_bytes(b"image")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-5"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "path": image_path,
                "kind": "image",
                "beat": "S1",
                "origin": "user_upload",
                "status": "ready",
                "selected": True,
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["assignment_status"] == "user_asset"
        assert beat["candidate_previews"] == []
        assert [item["path"] for item in beat["ledger"]] == [image_path]

    def test_commercial_board_uses_longer_root_decision_log_over_stale_artifact(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-stale-artifact-decisions")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        output_path = "assets/images/generated.png"
        (p / output_path).write_bytes(b"image")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-5"}],
        })
        approved = {
            "decision_id": "d-approved",
            "stage": "assets_gate",
            "category": "asset_decision",
            "subject": output_path,
            "asset_path": output_path,
            "beat_ids": ["S1"],
            "options_considered": [{
                "option_id": "approved",
                "label": "批准",
                "score": 1.0,
                "reason": "批准候选图。",
            }],
            "selected": "approved",
            "reason": "批准候选图。",
            "user_approved": True,
            "user_response_text": "批准。",
        }
        rejected = {
            **approved,
            "decision_id": "d-rejected",
            "options_considered": [{
                "option_id": "rejected",
                "label": "撤回",
                "score": 1.0,
                "reason": "撤回候选图。",
            }],
            "selected": "rejected",
            "reason": "撤回候选图。",
            "user_response_text": "撤回。",
        }
        stale_log = {
            "version": "1.0",
            "project_id": p.name,
            "decisions": [approved],
        }
        _write(p / "artifacts" / "decision_log.json", stale_log)
        _write(p / "decision_log.json", {
            **stale_log,
            "decisions": [approved, rejected],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [],
            "planned_entries": [{
                "beat": "S1",
                "kind": "image",
                "origin": "i2i",
                "status": "approved",
                "review_status": "approved",
                "decision_id": "d-approved",
                "provider": "provider",
                "model": "model",
                "candidate_paths": [output_path],
                "output_path": output_path,
            }],
        })

        commercial = load_board_state(p)["commercial"]

        assert commercial["decisions"][0]["selected"] == "rejected"
        assert commercial["beats"][0]["assignment_status"] != "approved"

    def test_commercial_board_rejects_cross_project_decision_log(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-cross-project-decisions")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        _write(p / "artifacts" / "decision_log.json", {
            "version": "1.0",
            "project_id": "other-project",
            "decisions": [{
                "decision_id": "d-other",
                "stage": "assets_gate",
                "category": "asset_decision",
                "subject": "assets/images/other.png",
                "options_considered": [{
                    "option_id": "approved",
                    "label": "批准",
                    "score": 1.0,
                    "reason": "其它项目决定。",
                }],
                "selected": "approved",
                "reason": "其它项目决定。",
            }],
        })

        commercial = load_board_state(p)["commercial"]

        assert commercial["decisions"] == []

    def test_commercial_board_rejects_cross_project_checkpoint_decision_log(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-cross-project-checkpoint-log")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        _write(p / "checkpoint_assets_gate.json", {
            "version": "1.0",
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
            "stage": "assets_gate",
            "status": "in_progress",
            "timestamp": "2026-08-13T00:00:00+00:00",
            "artifacts": {
                "decision_log": {
                    "version": "1.0",
                    "project_id": "other-project",
                    "decisions": [{
                        "decision_id": "d-other-checkpoint",
                        "stage": "assets_gate",
                        "category": "asset_decision",
                        "subject": "assets/images/other.png",
                        "options_considered": [{
                            "option_id": "approved",
                            "label": "批准",
                            "score": 1.0,
                            "reason": "其它项目决定。",
                        }],
                        "selected": "approved",
                        "reason": "其它项目决定。",
                    }],
                },
            },
        })

        commercial = load_board_state(p)["commercial"]

        assert commercial["decisions"] == []

    def test_commercial_empty_segments_fall_back_to_video_plan_beats(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-empty-segments-beats-fallback")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [],
        })
        _write(p / "artifacts" / "video_plan.json", {
            "segments": [],
            "beats": [
                {"id": "S1", "t": "0-4"},
                {"id": "S2", "t": "4-8"},
            ],
        })

        beats = load_board_state(p)["commercial"]["beats"]

        assert [beat["beat"] for beat in beats] == ["S1", "S2"]
        assert [beat["time"] for beat in beats] == ["0-4", "4-8"]

    @pytest.mark.parametrize(
        ("review_status", "provider", "expected_status"),
        [
            ("", "flux", "review_pending"),
            ("approved", "", "failed"),
        ],
    )
    def test_commercial_i2i_status_approved_requires_review_and_strong_closure(
        self,
        projects_root,
        review_status,
        provider,
        expected_status,
    ):
        p = _make_project(
            projects_root,
            f"commercial-i2i-approved-{review_status or 'missing'}-{provider or 'missing'}",
        )
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        candidate_path = "assets/images/candidate.png"
        (p / candidate_path).write_bytes(b"image")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "S1",
                "kind": "image",
                "path": candidate_path,
                "status": "approved",
                "review_status": review_status,
                "origin": "i2i",
                "provider": provider,
                "model": "flux-pro",
                "selected": True,
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["assignment_status"] == expected_status
        assert beat["assignment_status"] != "approved"
        assert beat["available_count"] == 0
        assert [item["path"] for item in beat["candidate_previews"]] == [
            candidate_path,
        ]

    @pytest.mark.parametrize(
        "source_alias",
        [
            "generated",
            "t2i",
            "text_to_image",
            "i2i",
            "image_to_image",
            "ai_generated",
        ],
    )
    @pytest.mark.parametrize("container", ["entries", "planned_entries"])
    def test_commercial_generated_aliases_use_matrix_beat_path_review_for_preview(
        self,
        projects_root,
        source_alias,
        container,
    ):
        p = _make_project(
            projects_root,
            f"commercial-{container}-{source_alias}",
        )
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        candidate_path = "assets/images/candidate.png"
        (p / candidate_path).write_bytes(b"candidate")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-4"}],
        })
        entry = {
            "beat": "S1",
            "kind": "image",
            "status": "approved",
            "review_status": "approved",
            "origin": source_alias,
            "provider": "provider",
            "model": "model",
        }
        if container == "entries":
            entry.update({"path": candidate_path, "selected": True})
        else:
            entry["output_path"] = candidate_path
        _write(p / "artifacts" / "asset_ledger.json", {
            container: [entry],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]
        preview = beat["ledger" if container == "entries" else "planned_entries"][0]

        assert preview["preview_kind"] == "candidate"
        assert beat["assignment_status"] != "approved"
        assert beat["available_count"] == 0
        assert [item["path"] for item in beat["candidate_previews"]] == [
            candidate_path,
        ]

    @pytest.mark.parametrize(
        "source_patch",
        [
            {"decision_id": "fake-decision"},
            {
                "provider": "provider",
                "origin": "user_upload",
                "asset_source": "reuse",
            },
        ],
    )
    def test_commercial_actual_generation_signal_source_issue_is_not_user_asset(
        self,
        projects_root,
        source_patch,
    ):
        p = _make_project(projects_root, "commercial-actual-source-issue")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        candidate_path = "assets/images/actual.png"
        (p / candidate_path).write_bytes(b"candidate")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "S1",
                "kind": "image",
                "path": candidate_path,
                "status": "confirmed",
                "selected": True,
                "label_zh": "来源声明异常素材",
                **source_patch,
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]
        preview = beat["ledger"][0]

        assert preview["preview_kind"] == "candidate"
        assert beat["assignment_status"] != "user_asset"
        assert beat["available_count"] == 0
        assert [item["path"] for item in beat["candidate_previews"]] == [
            candidate_path,
        ]

    def test_commercial_planned_image_without_source_cannot_preview_as_approved(
        self,
        projects_root,
    ):
        p = _make_project(projects_root, "commercial-planned-missing-source")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        candidate_path = "assets/images/planned.png"
        (p / candidate_path).write_bytes(b"candidate")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "planned_entries": [{
                "beat": "S1",
                "kind": "image",
                "status": "approved",
                "review_status": "approved",
                "output_path": candidate_path,
                "label_zh": "无来源计划图",
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]
        preview = beat["planned_entries"][0]

        assert preview["preview_kind"] == "candidate"
        assert beat["assignment_status"] != "approved"
        assert beat["available_count"] == 0
        assert [item["path"] for item in beat["candidate_previews"]] == [
            candidate_path,
        ]

    def test_commercial_closed_plan_backfills_reference_from_unique_matrix_path(
        self,
        projects_root,
    ):
        p = _make_project(projects_root, "commercial-reference-backfill")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        approved_path = "assets/images/approved.png"
        (p / approved_path).write_bytes(b"approved")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-4"}],
        })
        _write(p / "artifacts" / "video_plan.json", {
            "segments": [{
                "id": "S1",
                "assignment_status": "approved",
                "asset_source": "user_upload",
            }],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "S1",
                "kind": "image",
                "path": approved_path,
                "status": "confirmed",
                "origin": "user_upload",
                "selected": True,
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["reference_path"] == approved_path
        assert beat["ref"] == approved_path

    def test_commercial_matrix_approval_is_scoped_to_exact_beat_and_path(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-beat-path-pair-approval")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        shared_path = "assets/images/shared.png"
        (p / shared_path).write_bytes(b"image")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [
                {"beat": "S1", "time": "0-4"},
                {"beat": "S2", "time": "4-8"},
            ],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "S1",
                "kind": "image",
                "path": shared_path,
                "status": "confirmed",
                "origin": "user_upload",
                "selected": True,
            }],
            "planned_entries": [{
                "beat": "S2",
                "kind": "image",
                "output_path": shared_path,
                "status": "approved",
                "review_status": "review_pending",
                "origin": "i2i",
                "provider": "flux",
                "model": "flux-pro",
            }],
        })

        beats = {
            beat["beat"]: beat
            for beat in load_board_state(p)["commercial"]["beats"]
        }

        assert beats["S1"]["assignment_status"] == "user_asset"
        assert beats["S2"]["assignment_status"] == "review_pending"
        assert beats["S2"]["available_count"] == 0
        assert beats["S2"]["planned_entries"][0]["preview_kind"] == "candidate"
        assert [item["path"] for item in beats["S2"]["candidate_previews"]] == [
            shared_path,
        ]

    def test_commercial_user_asset_stays_primary_with_pending_i2i_candidate(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-user-primary-with-i2i-candidate")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        user_path = "assets/images/user.png"
        candidate_path = "assets/images/candidate.png"
        (p / user_path).write_bytes(b"user")
        (p / candidate_path).write_bytes(b"candidate")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "S1",
                "kind": "image",
                "path": user_path,
                "status": "confirmed",
                "origin": "user_upload",
                "selected": True,
            }],
            "planned_entries": [{
                "beat": "S1",
                "kind": "image",
                "status": "ready",
                "review_status": "review_pending",
                "origin": "i2i",
                "provider": "flux",
                "model": "flux-pro",
                "output_path": candidate_path,
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["assignment_status"] == "user_asset"
        assert beat["available_count"] == 1
        assert [item["path"] for item in beat["ledger"]] == [user_path]
        assert [item["path"] for item in beat["candidate_previews"]] == [
            candidate_path,
        ]

    def test_commercial_multiple_closed_assets_are_assignment_conflict(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-assignment-conflict")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        paths = ["assets/images/one.png", "assets/images/two.png"]
        for path in paths:
            (p / path).write_bytes(b"image")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [
                {
                    "beat": "S1",
                    "kind": "image",
                    "path": path,
                    "status": "confirmed",
                    "origin": "user_upload",
                    "selected": True,
                }
                for path in paths
            ],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["assignment_status"] == "assignment_conflict"
        assert beat["available_count"] == 2
        assert "冲突" in beat["assignment_reason"]
        assert any("多个闭环素材" in warning for warning in beat["assignment_warnings"])

    def test_commercial_i2i_candidate_is_not_reported_as_unused_upload(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-i2i-candidate-not-unused")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        candidate_path = "assets/images/candidate.png"
        unused_path = "assets/images/unused-upload.png"
        (p / candidate_path).write_bytes(b"candidate")
        (p / unused_path).write_bytes(b"unused")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_precheck.json", {
            "entries": [
                {"file": "candidate.png", "path": candidate_path},
                {"file": "unused-upload.png", "path": unused_path},
            ],
            "summary": {"total_images": 2},
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "S1",
                "kind": "image",
                "path": candidate_path,
                "status": "ready",
                "review_status": "review_pending",
                "origin": "i2i",
                "provider": "flux",
                "model": "flux-pro",
                "selected": True,
            }],
        })

        commercial = load_board_state(p)["commercial"]

        assert [item["path"] for item in commercial["beats"][0]["candidate_previews"]] == [
            candidate_path,
        ]
        assert [item["path"] for item in commercial["unused_assets"]] == [
            unused_path,
        ]

    def test_commercial_plan_reference_survives_missing_ledger_mapping_with_warning(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-reference-ledger-drift")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        reference_path = "assets/images/reference.png"
        (p / reference_path).write_bytes(b"image")
        _write(p / "artifacts" / "video_plan.json", {
            "segments": [{
                "id": "S1",
                "t": "0-5",
                "ref": reference_path,
            }],
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "S1", "time": "0-5"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "file": "reference.png",
                "path": reference_path,
                "kind": "image",
                "selected": True,
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["reference_path"] == reference_path
        assert beat["assignment_status"] == "missing"
        assert beat["assignment_warnings"]

    def test_commercial_beat_reference_uses_video_plan_then_brief_legacy_fallback(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-reference-fallback")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        for filename in ("explicit.png", "legacy.png"):
            (p / "assets" / "images" / filename).write_bytes(b"image")
        _write(p / "artifacts" / "video_plan.json", {
            "segments": [
                {
                    "id": "beat_01",
                    "t": "0-4",
                    "ref_image": "assets/images/explicit.png",
                },
                {"id": "beat_02", "t": "4-8"},
            ],
        })
        _write(p / "artifacts" / "brief.json", {
            "images": {
                "legacy.png": {
                    "path": "assets/images/legacy.png",
                    "role": "product_hero",
                    "beat": "beat_02",
                }
            }
        })

        beats = {
            beat["beat"]: beat
            for beat in load_board_state(p)["commercial"]["beats"]
        }

        assert beats["beat_01"]["reference_path"] == "assets/images/explicit.png"
        assert beats["beat_02"]["reference_path"] == "assets/images/legacy.png"

    def test_commercial_missing_ledger_path_is_not_exposed_as_display_path(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-missing-ledger-path")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "beat_01",
                "kind": "video",
                "path": "assets/video/missing.mp4",
                "selected": True,
            }],
        })

        item = load_board_state(p)["commercial"]["beats"][0]["ledger"][0]

        assert item["exists"] is False
        assert item["path"] is None
        assert item["missing_path"] == "assets/video/missing.mp4"

    def test_commercial_real_image_ledger_entry_must_live_under_assets_images(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-image-ledger-boundary")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        wrong_path = p / "assets" / "video" / "hero.png"
        wrong_path.parent.mkdir(parents=True, exist_ok=True)
        wrong_path.write_bytes(b"image")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "beat_01",
                "kind": "image",
                "path": "assets/video/hero.png",
                "selected": True,
            }],
        })

        item = load_board_state(p)["commercial"]["beats"][0]["ledger"][0]

        assert item["exists"] is False
        assert item["path"] is None
        assert item["missing_path"] == "assets/video/hero.png"

    def test_commercial_legacy_ledger_without_kind_infers_real_image(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-legacy-image-kind")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        image_path = "assets/images/legacy-hero.JPG"
        (p / image_path).write_bytes(b"image")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "beat_01",
                "path": image_path,
                "selected": True,
            }],
        })

        item = load_board_state(p)["commercial"]["beats"][0]["ledger"][0]

        assert item["kind"] == "image"
        assert item["exists"] is True
        assert item["path"] == image_path

    @pytest.mark.parametrize(
        "raw_path",
        ["project.json", "assets/images/not-an-image.txt"],
    )
    def test_commercial_legacy_ledger_without_kind_rejects_non_images(
        self, projects_root, raw_path
    ):
        p = _make_project(projects_root, "commercial-legacy-non-image")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        if raw_path != "project.json":
            candidate = p / raw_path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(b"not image")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{"beat": "beat_01", "path": raw_path}],
        })

        item = load_board_state(p)["commercial"]["beats"][0]["ledger"][0]

        assert item["exists"] is False
        assert item["path"] is None
        assert item["missing_path"] == raw_path

    @pytest.mark.parametrize(
        ("kind", "output_path"),
        [
            ("video", "project.json"),
            ("video", "assets/images/wrong-place.mp4"),
            ("video", "assets/video/not-a-video.txt"),
            ("image", "project.json"),
            ("image", "assets/video/wrong-place.png"),
            ("image", "assets/images/not-an-image.txt"),
        ],
    )
    def test_commercial_ready_planned_media_rejects_wrong_location_or_extension(
        self, projects_root, kind, output_path
    ):
        p = _make_project(projects_root, "commercial-ready-media-boundary")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        if output_path != "project.json":
            candidate = p / output_path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(b"media")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [],
            "planned_entries": [{
                "beat": "beat_01",
                "kind": kind,
                "status": "ready",
                "output_path": output_path,
            }],
        })

        item = load_board_state(p)["commercial"]["beats"][0]["planned_entries"][0]

        assert item["status"] == "failed"
        assert item["exists"] is False
        assert item.get("path") is None
        assert item["missing_output_path"] == output_path

    def test_commercial_ready_planned_media_accepts_allowed_media_files(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-ready-media-valid")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        paths = {
            "image": "assets/images/ready.webp",
            "video": "assets/video/ready.webm",
        }
        for output_path in paths.values():
            candidate = p / output_path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(b"media")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [],
            "planned_entries": [
                {
                    "beat": "beat_01",
                    "kind": kind,
                    "status": "ready",
                    "output_path": output_path,
                }
                for kind, output_path in paths.items()
            ],
        })

        items = load_board_state(p)["commercial"]["beats"][0]["planned_entries"]

        assert [(item["kind"], item["status"], item["path"]) for item in items] == [
            ("image", "ready", paths["image"]),
            ("video", "ready", paths["video"]),
        ]

    def test_commercial_repo_relative_current_project_image_path_is_supported(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-repo-relative-image")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        image_path = "assets/images/hero.png"
        (p / image_path).write_bytes(b"image")
        repo_relative = f"projects/{p.name}/{image_path}"
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "beat_01",
                "kind": "image",
                "path": repo_relative,
            }],
            "planned_entries": [{
                "beat": "beat_01",
                "kind": "image",
                "status": "ready",
                "output_path": repo_relative,
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["ledger"][0]["path"] == image_path
        assert beat["planned_entries"][0]["status"] == "ready"
        assert beat["planned_entries"][0]["path"] == image_path

    @pytest.mark.parametrize(
        "repo_relative",
        [
            "projects/other-project/assets/images/hero.png",
            "projects/{project_id}/assets/images/../images/hero.png",
        ],
    )
    def test_commercial_repo_relative_image_rejects_other_project_and_traversal(
        self, projects_root, repo_relative
    ):
        p = _make_project(projects_root, "commercial-repo-relative-rejected")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        (p / "assets" / "images" / "hero.png").write_bytes(b"current")
        other = projects_root / "other-project" / "assets" / "images" / "hero.png"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"other")
        raw_path = repo_relative.format(project_id=p.name)
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [{
                "beat": "beat_01",
                "kind": "image",
                "path": raw_path,
            }],
        })

        item = load_board_state(p)["commercial"]["beats"][0]["ledger"][0]

        assert item["exists"] is False
        assert item["path"] is None
        assert item["missing_path"] == raw_path

    def test_commercial_reference_traversal_never_falls_back_by_basename(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-reference-no-basename-guess")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        (p / "assets" / "images" / "hero.png").write_bytes(b"internal")
        outside = p.parent / "outside" / "hero.png"
        outside.parent.mkdir(parents=True)
        outside.write_bytes(b"outside")
        _write(p / "artifacts" / "video_plan.json", {
            "segments": [{
                "id": "beat_01",
                "t": "0-4",
                "ref_image": "../outside/hero.png",
            }],
        })

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["reference_path"] is None

    def test_commercial_missing_ready_output_is_downgraded_to_failed(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-ready-output-missing")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        output_path = "assets/images/planned-hero.png"
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [],
            "planned_entries": [{
                "beat": "beat_01",
                "kind": "image",
                "status": "ready",
                "planned_output_path": output_path,
                "output_path": output_path,
            }],
        })

        item = load_board_state(p)["commercial"]["beats"][0]["planned_entries"][0]

        assert item["status"] == "failed"
        assert item.get("path") is None
        assert item["missing_output_path"] == output_path
        assert item["error_zh"]

    @pytest.mark.parametrize(
        "images",
        [
            {
                "hero.png": {
                    "path": "assets/images/hero.png",
                    "role": "product_hero",
                }
            },
            ["assets/images/hero.png"],
        ],
    )
    def test_commercial_single_beat_single_brief_image_uses_unambiguous_fallback(
        self, projects_root, images
    ):
        p = _make_project(projects_root, "commercial-single-brief-image")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        (p / "assets" / "images" / "hero.png").write_bytes(b"image")
        _write(p / "artifacts" / "video_plan.json", {
            "segments": [{"id": "beat_01", "t": "0-4"}],
        })
        _write(p / "artifacts" / "brief.json", {"images": images})

        beat = load_board_state(p)["commercial"]["beats"][0]

        assert beat["reference_path"] == "assets/images/hero.png"

    def test_commercial_multiple_beats_do_not_guess_single_brief_image(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-multi-beat-no-image-guess")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        (p / "assets" / "images" / "hero.png").write_bytes(b"image")
        _write(p / "artifacts" / "video_plan.json", {
            "segments": [
                {"id": "beat_01", "t": "0-4"},
                {"id": "beat_02", "t": "4-8"},
            ],
        })
        _write(p / "artifacts" / "brief.json", {
            "images": ["assets/images/hero.png"],
        })

        beats = load_board_state(p)["commercial"]["beats"]

        assert [beat["reference_path"] for beat in beats] == [None, None]

    def test_commercial_segment_evidence_uses_only_review_outputs_and_real_batches(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-segment-evidence")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        for rel in (
            "assets/video/beat_01.mp4",
            "assets/video/beat_02.mp4",
            "assets/video/batch_01.mp4",
            "assets/video/sample_only.mp4",
        ):
            path = p / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"video")
        outside_video = projects_root.parent / "outside.mp4"
        outside_video.write_bytes(b"outside")
        _write(p / "artifacts" / "review_overview.json", {
            "overview": [
                {
                    "beat": "beat_01",
                    "time": "0-4",
                    "output_path": "assets/video/beat_01.mp4",
                },
                {
                    "beat": "beat_02",
                    "time": "4-8",
                    "output_path": "assets/video/beat_02.mp4",
                },
                {
                    "beat": "beat_03",
                    "time": "8-12",
                    "output_path": "assets/video/missing.mp4",
                },
                {
                    "beat": "beat_04",
                    "time": "12-16",
                    "output_path": str(outside_video.resolve()),
                },
            ],
            "batches": [
                {
                    "id": "batch_01",
                    "span": "0-8",
                    "output_path": "assets/video/batch_01.mp4",
                },
                {
                    "id": "batch_02",
                    "span": "8-12",
                    "output_path": "assets/video/missing_batch.mp4",
                },
                {
                    "id": "batch_03",
                    "span": "12-16",
                    "output_path": str(outside_video.resolve()),
                },
            ],
        })
        _write(p / "artifacts" / "sample_reel.json", {
            "path": "assets/video/sample_only.mp4",
            "beat_ids": ["beat_01"],
        })

        commercial = load_board_state(p)["commercial"]
        segment = commercial["stage_evidence"]["segment"]

        assert [
            (item.get("beat") or item.get("batch_id"), item["path"])
            for item in segment
        ] == [
            ("beat_01", "assets/video/beat_01.mp4"),
            ("beat_02", "assets/video/beat_02.mp4"),
            ("batch_01", "assets/video/batch_01.mp4"),
        ]
        assert commercial["stage_evidence"]["sample"]["beat_ids"] == ["beat_01"]

    def test_commercial_sample_evidence_exposes_its_beat_ids(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-sample-beat-ids")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        sample_path = p / "assets" / "video" / "sample.mp4"
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(b"video")
        _write(p / "artifacts" / "sample_reel.json", {
            "path": "assets/video/sample.mp4",
            "beat_ids": ["beat_01", "beat_03"],
        })

        sample = load_board_state(p)["commercial"]["stage_evidence"]["sample"]

        assert sample["beat_ids"] == ["beat_01", "beat_03"]

    @pytest.mark.parametrize(
        ("artifact_name", "field_name", "relative_path"),
        [
            ("sample_reel", "path", "assets/images/sample.png"),
            ("full_draft_pro", "path", "artifacts/draft.json"),
            ("final_review", "output_path", "renders/final.png"),
            ("sample_reel", "path", "assets/video/empty.mp4"),
        ],
    )
    def test_commercial_canonical_stage_media_must_be_nonempty_project_video(
        self,
        projects_root,
        artifact_name,
        field_name,
        relative_path,
    ):
        p = _make_project(projects_root, f"commercial-invalid-{artifact_name}")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        candidate = p / relative_path
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(b"" if relative_path.endswith("empty.mp4") else b"not-video")
        payload = {field_name: relative_path}
        if artifact_name == "full_draft_pro":
            payload.update({"issue_segments": [], "modification_list": []})
        if artifact_name == "final_review":
            payload.update({"status": "pass", "checks": {}})
        _write(p / "artifacts" / f"{artifact_name}.json", payload)

        evidence_name = {
            "sample_reel": "sample",
            "full_draft_pro": "draft",
            "final_review": "compose",
        }[artifact_name]
        evidence = load_board_state(p)["commercial"]["stage_evidence"][evidence_name]

        assert evidence["path"] is None
        assert evidence["exists"] is False
        assert evidence["missing_path"] == relative_path
        assert evidence["reason_code"] == "invalid_stage_media"
        assert "非空视频文件" in evidence["missing_reason_zh"]

    @pytest.mark.parametrize(
        ("later_artifact", "later_field", "invalidated_stage", "winner_stage"),
        [
            ("full_draft_pro", "path", "sample", "draft"),
            ("final_review", "output_path", "sample", "compose"),
            ("final_review", "output_path", "draft", "compose"),
        ],
    )
    def test_later_canonical_stage_media_invalidates_reused_earlier_path(
        self,
        projects_root,
        later_artifact,
        later_field,
        invalidated_stage,
        winner_stage,
    ):
        p = _make_project(
            projects_root,
            f"commercial-conflict-{invalidated_stage}-{winner_stage}",
        )
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        shared_path = "renders/shared.mp4"
        (p / shared_path).write_bytes(b"video")
        if invalidated_stage == "sample":
            _write(p / "artifacts" / "sample_reel.json", {"path": shared_path})
        else:
            _write(p / "artifacts" / "full_draft_pro.json", {
                "path": shared_path,
                "issue_segments": [],
                "modification_list": [],
            })
        later_payload = {later_field: shared_path}
        if later_artifact == "full_draft_pro":
            later_payload.update({"issue_segments": [], "modification_list": []})
        else:
            later_payload.update({"status": "pass", "checks": {}})
        _write(p / "artifacts" / f"{later_artifact}.json", later_payload)

        evidence = load_board_state(p)["commercial"]["stage_evidence"]
        invalidated = evidence[invalidated_stage]
        winner = evidence[winner_stage]

        assert invalidated["path"] is None
        assert invalidated["exists"] is False
        assert invalidated["missing_path"] == shared_path
        assert invalidated["reason_code"] == "canonical_path_conflict"
        assert invalidated["conflict_with"] == winner_stage
        assert "复用" in invalidated["missing_reason_zh"]
        assert winner["path"] == shared_path
        assert winner["exists"] is True

    @pytest.mark.parametrize(
        (
            "later_artifact",
            "later_field",
            "invalidated_stage",
            "winner_stage",
        ),
        [
            ("sample_reel", "path", "sample", "segment"),
            ("full_draft_pro", "path", "segment", "draft"),
            ("final_review", "output_path", "segment", "compose"),
        ],
    )
    def test_segment_canonical_path_conflicts_follow_stage_precedence(
        self,
        projects_root,
        later_artifact,
        later_field,
        invalidated_stage,
        winner_stage,
    ):
        p = _make_project(
            projects_root,
            f"commercial-segment-conflict-{winner_stage}",
        )
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        shared_path = "assets/video/shared.mp4"
        shared_video = p / shared_path
        shared_video.parent.mkdir(parents=True, exist_ok=True)
        shared_video.write_bytes(b"video")
        _write(p / "artifacts" / "review_overview.json", {
            "overview": [{
                "beat": "beat_01",
                "time": "0-4",
                "output_path": shared_path,
            }],
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        payload = {later_field: shared_path}
        if later_artifact == "sample_reel":
            payload["beat_ids"] = ["beat_01"]
        elif later_artifact == "full_draft_pro":
            payload.update({"issue_segments": [], "modification_list": []})
        else:
            payload.update({"status": "pass", "checks": {}})
        _write(p / "artifacts" / f"{later_artifact}.json", payload)

        evidence = load_board_state(p)["commercial"]
        segment = evidence["stage_evidence"]["segment"][0]
        invalidated = (
            evidence["stage_evidence"]["sample"]
            if invalidated_stage == "sample"
            else segment
        )
        winner = (
            segment
            if winner_stage == "segment"
            else evidence["stage_evidence"][winner_stage]
        )

        assert invalidated["path"] is None
        assert invalidated["exists"] is False
        assert invalidated["missing_path"] == shared_path
        assert invalidated["reason_code"] == "canonical_path_conflict"
        assert invalidated["conflict_with"] == winner_stage
        assert "复用" in invalidated["missing_reason_zh"]
        assert winner["path"] == shared_path
        assert winner["exists"] is True
        if invalidated_stage == "segment":
            assert evidence["beats"][0]["asset_path"] is None
            assert "canonical 路径冲突" in (
                evidence["beats"][0]["asset_conflict_reason_zh"]
            )

    def test_final_compose_and_delivery_share_one_valid_final_review_video(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-final-shared-evidence")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        final_path = "renders/final.mp4"
        (p / final_path).write_bytes(b"video")
        _write(p / "artifacts" / "final_review.json", {
            "output_path": final_path,
            "status": "pass",
            "checks": {},
        })

        evidence = load_board_state(p)["commercial"]["stage_evidence"]

        assert evidence["compose"]["path"] == final_path
        assert evidence["delivery"]["path"] == final_path
        assert evidence["compose"]["reason_code"] is None
        assert evidence["delivery"]["reason_code"] is None

    def test_commercial_each_beat_uses_its_own_review_output_path(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-beat-review-output")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        for beat in ("beat_01", "beat_02"):
            path = p / "assets" / "video" / f"{beat}.mp4"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"video")
        _write(p / "artifacts" / "review_overview.json", {
            "overview": [
                {
                    "beat": "beat_01",
                    "time": "0-4",
                    "output_path": "assets/video/beat_01.mp4",
                },
                {
                    "beat": "beat_02",
                    "time": "4-8",
                    "output_path": "assets/video/beat_02.mp4",
                },
            ]
        })
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [
                {"beat": "beat_01", "time": "0-4"},
                {"beat": "beat_02", "time": "4-8"},
            ],
        })

        beats = load_board_state(p)["commercial"]["beats"]

        assert [beat["asset_path"] for beat in beats] == [
            "assets/video/beat_01.mp4",
            "assets/video/beat_02.mp4",
        ]

    def test_commercial_ready_planned_media_never_becomes_stage_evidence(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-planned-is-not-evidence")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        planned_path = p / "assets" / "video" / "planned.mp4"
        planned_path.parent.mkdir(parents=True, exist_ok=True)
        planned_path.write_bytes(b"video")
        _write(p / "artifacts" / "segment_cards.json", {
            "segments": [{"beat": "beat_01", "time": "0-4"}],
        })
        _write(p / "artifacts" / "asset_ledger.json", {
            "entries": [],
            "planned_entries": [{
                "beat": "beat_01",
                "kind": "video",
                "status": "ready",
                "output_path": "assets/video/planned.mp4",
            }],
        })

        commercial = load_board_state(p)["commercial"]

        assert commercial["beats"][0]["planned_entries"][0]["path"] == (
            "assets/video/planned.mp4"
        )
        assert commercial["stage_evidence"]["segment"] == []
        assert commercial["stage_evidence"]["sample"]["path"] is None

    def test_commercial_batch_review_must_be_referenced_and_keeps_real_source_path(
        self, projects_root
    ):
        p = _make_project(projects_root, "commercial-batch-review-isolation")
        _write(p / "project.json", {
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        for rel in (
            "assets/video/current_batch.mp4",
            "assets/video/stale_batch.mp4",
        ):
            path = p / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"video")
        _write(p / "artifacts" / "review_overview.json", {
            "overview": [],
            "batches": [{"id": "batch_01", "span": "0-8"}],
        })
        _write(p / "artifacts" / "batch01_review.json", {
            "batch_id": "batch_01",
            "output_path": "assets/video/current_batch.mp4",
            "status": "approved",
        })
        _write(p / "artifacts" / "batch02_review.json", {
            "batch_id": "batch_02",
            "output_path": "assets/video/stale_batch.mp4",
            "status": "approved",
        })

        state = load_board_state(p)
        segment = state["commercial"]["stage_evidence"]["segment"]

        assert [
            (item["batch_id"], item["path"], item["artifact_path"])
            for item in segment
        ] == [(
            "batch_01",
            "assets/video/current_batch.mp4",
            "artifacts/batch01_review.json",
        )]
        assert "_batch_review_sources" not in state["artifacts"]
        assert all(
            "_source_path" not in review
            for review in state["artifacts"]["batch_reviews"].values()
        )


class TestCommercialArtifactSchemas:
    def test_review_overview_accepts_uppercase_video_extension(self):
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas" / "artifacts" / "review_overview.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        validate({
            "overview": [{
                "beat": "beat_01",
                "output_path": "assets/video/BEAT_01.MP4",
            }],
            "batches": [],
        }, schema)

    def test_full_draft_requires_user_visible_review_evidence(self):
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas" / "artifacts" / "full_draft_pro.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        with pytest.raises(ValidationError):
            validate({"path": "renders/draft.mp4"}, schema)

        validate({
            "path": "renders/draft.mp4",
            "issue_segments": [],
            "modification_list": [],
        }, schema)


class TestCommercialEditingGate:
    def _project(
        self,
        root: Path,
        *,
        stage: str = "draft_review",
        draft_path: str = "renders/draft.mp4",
        cuts: list[dict] | None = None,
    ) -> Path:
        p = _make_project(root, "commercial-editing-gate")
        _write(p / "project.json", {
            "version": "1.0",
            "project_id": p.name,
            "pipeline_type": "bootstrap-commercial",
        })
        default_cuts = [{
            "id": "cut_01",
            "source": "assets/video/cut_01.mp4",
            "in_seconds": 0,
            "out_seconds": 2,
        }]
        _write(p / "artifacts" / "edit_decisions.json", {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "cuts": default_cuts if cuts is None else cuts,
        })
        _write(p / "artifacts" / "full_draft_pro.json", {
            "version": "1.0",
            "path": draft_path,
            "issue_segments": [],
            "modification_list": [],
        })
        cut_file = p / "assets" / "video" / "cut_01.mp4"
        cut_file.parent.mkdir(parents=True, exist_ok=True)
        cut_file.write_bytes(b"video")
        for index, name in enumerate((
            "brief_locked",
            "assets_gate",
            "sample_review",
            "segment_build",
            "draft_review",
            "final_compose",
            "delivery_signoff",
        )):
            if name == stage:
                status = "in_progress"
            elif index < (
                "brief_locked",
                "assets_gate",
                "sample_review",
                "segment_build",
                "draft_review",
                "final_compose",
                "delivery_signoff",
            ).index(stage):
                status = "completed"
            else:
                continue
            _write(p / f"checkpoint_{name}.json", {
                "stage": name,
                "status": status,
                "timestamp": f"2026-08-12T00:{index:02d}:00Z",
                "human_approved": status == "completed",
                "artifacts": {},
            })
        return p

    def test_draft_review_gate_uses_canonical_full_draft_render(self, projects_root):
        p = self._project(projects_root)
        (p / "renders" / "draft.mp4").write_bytes(b"video")

        gate = load_board_state(p)["editing_gate"]

        assert gate["enabled"] is True
        assert gate["reason_codes"] == []
        assert gate["latest_render"]["path"] == "renders/draft.mp4"

    def test_render_directory_scan_cannot_unlock_missing_canonical_render(
        self, projects_root
    ):
        p = self._project(projects_root, draft_path="renders/missing.mp4")
        (p / "renders" / "stray-newer.mp4").write_bytes(b"video")

        gate = load_board_state(p)["editing_gate"]

        assert gate["enabled"] is False
        assert "latest_render_missing" in gate["reason_codes"]
        assert gate["latest_render"]["path"] is None

    @pytest.mark.parametrize(
        ("source", "create_file", "expected_code"),
        [
            ("assets/video/missing.mp4", False, "cut_source_missing"),
            ("../outside.mp4", True, "cut_source_outside_assets_video"),
            (
                "projects/other/assets/video/cut.mp4",
                True,
                "cut_source_outside_assets_video",
            ),
            ("project.json", False, "cut_source_outside_assets_video"),
            ("assets/video/cut.json", True, "cut_source_not_video"),
            ("assets/video/empty.mp4", True, "cut_source_empty"),
        ],
    )
    def test_every_cut_source_must_be_a_nonempty_project_video(
        self, projects_root, source, create_file, expected_code
    ):
        cuts = [
            {
                "id": "cut_01",
                "source": "assets/video/cut_01.mp4",
                "in_seconds": 0,
                "out_seconds": 2,
            },
            {
                "id": "cut_02",
                "source": source,
                "in_seconds": 0,
                "out_seconds": 2,
            },
        ]
        p = self._project(projects_root, cuts=cuts)
        (p / "renders" / "draft.mp4").write_bytes(b"video")
        if create_file:
            candidate = p / source
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(b"" if source.endswith("empty.mp4") else b"data")

        gate = load_board_state(p)["editing_gate"]

        assert gate["enabled"] is False
        assert expected_code in gate["reason_codes"]

    def test_delivery_revision_uses_canonical_final_review_render(self, projects_root):
        p = self._project(projects_root, stage="delivery_signoff")
        (p / "renders" / "draft.mp4").write_bytes(b"draft")
        (p / "renders" / "final.mp4").write_bytes(b"final")
        _write(p / "artifacts" / "final_review.json", {
            "version": "1.0",
            "output_path": "renders/final.mp4",
            "status": "revise",
            "checks": {},
        })

        state = load_board_state(p)

        assert state["editing_gate"]["enabled"] is True
        assert state["editing_gate"]["latest_render"]["path"] == "renders/final.mp4"
        assert [stage["name"] for stage in state["stages"]] == [
            "brief_locked",
            "assets_gate",
            "sample_review",
            "segment_build",
            "draft_review",
            "final_compose",
            "delivery_signoff",
        ]

    def test_delivery_revision_still_requires_valid_full_draft(self, projects_root):
        p = self._project(projects_root, stage="delivery_signoff")
        (p / "renders" / "final.mp4").write_bytes(b"final")
        _write(p / "artifacts" / "final_review.json", {
            "version": "1.0",
            "output_path": "renders/final.mp4",
            "status": "revise",
            "checks": {},
        })

        gate = load_board_state(p)["editing_gate"]

        assert gate["enabled"] is False
        assert "full_draft_invalid" in gate["reason_codes"]

    def test_applied_cuts_lock_old_render_until_compose_updates_revision(
        self, projects_root
    ):
        p = self._project(projects_root)
        (p / "renders" / "draft.mp4").write_bytes(b"old-render")
        decisions_path = p / "artifacts" / "edit_decisions.json"
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
        revision = cuts_digest(decisions["cuts"])
        decisions["requires_compose"] = True
        decisions["cuts_revision"] = revision
        _write(decisions_path, decisions)

        locked = load_board_state(p)["editing_gate"]

        assert locked["enabled"] is False
        assert "compose_required" in locked["reason_codes"]
        assert "重合成" in locked["friendly_zh"]

        draft_path = p / "artifacts" / "full_draft_pro.json"
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        draft["cuts_revision"] = revision
        _write(draft_path, draft)

        recovered = load_board_state(p)["editing_gate"]
        assert recovered["enabled"] is True
        assert recovered["reason_codes"] == []

    def test_dirty_delivery_gate_uses_final_review_cuts_revision(self, projects_root):
        p = self._project(projects_root, stage="delivery_signoff")
        (p / "renders" / "draft.mp4").write_bytes(b"draft")
        (p / "renders" / "final.mp4").write_bytes(b"final")
        decisions_path = p / "artifacts" / "edit_decisions.json"
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
        revision = cuts_digest(decisions["cuts"])
        decisions.update({"requires_compose": True, "cuts_revision": revision})
        _write(decisions_path, decisions)
        final_path = p / "artifacts" / "final_review.json"
        final = {
            "version": "1.0",
            "output_path": "renders/final.mp4",
            "status": "revise",
            "checks": {},
            "cuts_revision": "stale",
        }
        _write(final_path, final)

        assert "compose_required" in load_board_state(p)["editing_gate"]["reason_codes"]

        final["cuts_revision"] = revision
        _write(final_path, final)
        assert load_board_state(p)["editing_gate"]["enabled"] is True


class TestEditClosureRevisionSchemas:
    @pytest.mark.parametrize(
        ("schema_name", "payload"),
        [
            (
                "full_draft_pro",
                {
                    "path": "renders/draft.mp4",
                    "issue_segments": [],
                    "modification_list": [],
                    "cuts_revision": "h123",
                },
            ),
            (
                "final_review",
                {
                    "version": "1.0",
                    "output_path": "renders/final.mp4",
                    "status": "revise",
                    "checks": {
                        "technical_probe": {},
                        "visual_spotcheck": {},
                        "audio_spotcheck": {},
                        "promise_preservation": {},
                        "subtitle_check": {},
                    },
                    "cuts_revision": "h123",
                },
            ),
        ],
    )
    def test_render_artifacts_accept_optional_cuts_revision(self, schema_name, payload):
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas" / "artifacts" / f"{schema_name}.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        assert schema["properties"]["cuts_revision"] == {
            "type": "string",
            "minLength": 1,
        }
        validate(payload, schema)

    def test_edit_decisions_accepts_dirty_revision_contract(self):
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas" / "artifacts" / "edit_decisions.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        validate({
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "cuts": [],
            "requires_compose": True,
            "cuts_revision": "h123",
        }, schema)


class TestCommercialUIContract:
    def test_video_players_require_confirmed_existing_files(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "backlot"
            / "ui"
            / "board-commercial.js"
        ).read_text(encoding="utf-8")

        assert 'x.kind === "video" && x.path && x.exists === true' in source
        assert "stageEvidence?.path && stageEvidence?.exists === true" in source
        assert "stageEvidence.candidate?.exists === true" not in source
        assert "segment: evidence.sample" not in source
        assert 'if (!entries.length || view !== "assets") return null;' in source
        assert "媒体文件不存在" in source

    def test_edit_submit_distinguishes_gate_lock_from_duplicate_conflict(self):
        ui_dir = Path(__file__).resolve().parents[2] / "backlot" / "ui"
        source = "\n".join(
            (ui_dir / filename).read_text(encoding="utf-8")
            for filename in ("board-edit.js", "board-edit-errors.js")
        )

        assert 'detail?.kind === "editing_gate"' in source
        assert "detail?.reason_codes" in source
        assert "detail?.friendly_zh" in source
        assert "这组改动之前已经提交过了" in source

    def test_edit_submit_requires_nonempty_canonical_source_render(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "backlot"
            / "ui"
            / "board-edit.js"
        ).read_text(encoding="utf-8")

        guard = source.index("if (!baseRender)")
        request = source.index("fetch(EDIT_INTENTS_URL")
        assert guard < request
        assert "source_render: baseRender" in source


class TestLibrary:
    def test_list_projects_sorts_live_first(self, projects_root):
        old = _make_project(projects_root, "old-film")
        _write(old / "checkpoint_script.json", {"stage": "script", "status": "completed"})
        # backdate everything in old-film
        import os
        past = time.time() - 60 * 60 * 24 * 30
        for f in old.rglob("*"):
            if f.is_file():
                os.utime(f, (past, past))

        fresh = _make_project(projects_root, "fresh-film")
        _write(fresh / "checkpoint_script.json", {"stage": "script", "status": "in_progress"})

        projects = list_projects(projects_root)
        assert [p["project_id"] for p in projects][0] == "fresh-film"
        assert projects[0]["live"] is True
        assert projects[1]["live"] is False

    def test_underscore_dirs_skipped(self, projects_root):
        (projects_root / "_analysis").mkdir()
        _make_project(projects_root, "real")
        ids = [p["project_id"] for p in list_projects(projects_root)]
        assert ids == ["real"]

    def test_summary_shape(self, projects_root):
        p = _make_project(projects_root, "sum")
        _write(p / "project.json", {"title": "Sum", "pipeline_type": "cinematic"})
        _write(p / "checkpoint_script.json", {
            "stage": "script", "status": "awaiting_human",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        summary = summarize_project(p)
        assert summary["awaiting_human"] is True
        assert summary["active_stage"] == "script"


class TestFindingsFixes:
    """Regression tests for dogfood findings F-04/F-05."""

    def test_artifact_refs_outside_project_are_not_followed(self, projects_root, tmp_path):
        # F-04: a checkpoint pointing at JSON outside the project tree
        # must not surface that file on the board.
        secret = tmp_path / "secret.json"
        secret.write_text(json.dumps({"version": "1.0", "leaked": True}), encoding="utf-8")
        p = _make_project(projects_root, "sneaky-ref")
        _write(p / "checkpoint_script.json", {
            "stage": "script", "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z",
            "artifacts": {"script": str(secret)},
        })
        s = load_board_state(p)
        assert "script" not in s["artifacts"]

    def test_inside_project_absolute_refs_still_resolve(self, projects_root):
        p = _make_project(projects_root, "abs-ref")
        _write(p / "artifacts" / "inline_script.json", SCRIPT)
        _write(p / "checkpoint_script.json", {
            "stage": "script", "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z",
            "artifacts": {"script": str((p / "artifacts" / "inline_script.json").resolve())},
        })
        s = load_board_state(p)
        assert s["artifacts"]["script"]["title"] == "Test Film"

    def test_stalled_in_progress_stage_flagged(self, projects_root):
        # F-05: an in_progress stage with no recent activity reads stalled.
        import os
        p = _make_project(projects_root, "wedged")
        _write(p / "checkpoint_research.json", {
            "stage": "research", "status": "in_progress",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        past = time.time() - 30 * 60
        for f in p.rglob("*"):
            if f.is_file():
                os.utime(f, (past, past))
        s = load_board_state(p)
        research = next(x for x in s["stages"] if x["name"] == "research")
        assert research["stalled"] is True
        assert research["stalled_minutes"] >= 29

    def test_fresh_in_progress_not_stalled(self, projects_root):
        p = _make_project(projects_root, "busy")
        _write(p / "checkpoint_research.json", {
            "stage": "research", "status": "in_progress",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        s = load_board_state(p)
        research = next(x for x in s["stages"] if x["name"] == "research")
        assert "stalled" not in research


class TestStoryboardVisualSelection:
    """The renderable / snapshot / takes logic in _build_storyboard.

    Covers the atelier-thumbnail work: a .tsx composition asset is not a
    showable visual; a missing raster file still surfaces as an indicator;
    an existing SVG diagram IS showable; snapshots/<id>.png is the fallback.
    """

    def _project_with_scenes(self, root, scenes, assets):
        p = _make_project(root, "vis")
        _write(p / "project.json", {"pipeline_type": "cinematic"})
        _write(p / "artifacts" / "scene_plan.json", {"version": "1.0", "scenes": scenes})
        _write(p / "artifacts" / "asset_manifest.json", {"version": "1.0", "assets": assets})
        return p

    def _card(self, p, scene_id):
        s = load_board_state(p)
        return next(c for c in s["storyboard"]["scenes"] if c["id"] == scene_id)

    def test_existing_tsx_animation_is_not_a_visual(self, projects_root):
        # A bespoke composition asset exists on disk but can't be shown.
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "animation", "description": "morph",
              "start_seconds": 0, "end_seconds": 5}],
            [{"id": "a1", "type": "animation", "path": "Composition.tsx", "scene_id": "sc1",
              "source_tool": "atelier_remotion"}],
        )
        (p / "Composition.tsx").write_text("export const X = 1;", encoding="utf-8")
        card = self._card(p, "sc1")
        # No snapshot yet -> no renderable visual, falls to placeholder (None).
        assert card["visual"] is None
        assert card["takes"] == []

    def test_snapshot_is_the_fallback_for_animation_scene(self, projects_root):
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "animation", "description": "morph",
              "start_seconds": 0, "end_seconds": 5}],
            [{"id": "a1", "type": "animation", "path": "Composition.tsx", "scene_id": "sc1",
              "source_tool": "atelier_remotion"}],
        )
        (p / "Composition.tsx").write_text("x", encoding="utf-8")
        (p / "snapshots").mkdir()
        (p / "snapshots" / "sc1.png").write_bytes(b"\x89PNG")
        card = self._card(p, "sc1")
        assert card["visual"] is not None
        assert card["visual"]["snapshot"] is True
        assert card["visual"]["renderable"] is True
        assert card["visual"]["path"].endswith("sc1.png")

    def test_snapshot_matches_id_underscore_suffix(self, projects_root):
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "animation", "start_seconds": 0, "end_seconds": 5}],
            [],
        )
        (p / "snapshots").mkdir()
        (p / "snapshots" / "sc1_hero.png").write_bytes(b"\x89PNG")
        card = self._card(p, "sc1")
        assert card["visual"] is not None and card["visual"]["snapshot"] is True

    def test_existing_svg_diagram_is_renderable(self, projects_root):
        # Regression guard: an existing non-raster-but-showable image (.svg)
        # must remain a visual, not be dropped to a placeholder.
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "diagram", "start_seconds": 0, "end_seconds": 5}],
            [{"id": "a1", "type": "diagram", "path": "assets/images/d.svg", "scene_id": "sc1",
              "source_tool": "diagram_gen"}],
        )
        (p / "assets" / "images" / "d.svg").write_text("<svg/>", encoding="utf-8")
        card = self._card(p, "sc1")
        assert card["visual"] is not None
        assert card["visual"]["exists"] is True
        assert card["visual"]["renderable"] is True

    def test_missing_raster_file_still_flagged(self, projects_root):
        # The "asset in manifest, file missing" indicator must survive.
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "generated", "start_seconds": 0, "end_seconds": 5}],
            [{"id": "a1", "type": "image", "path": "assets/images/gone.png", "scene_id": "sc1",
              "source_tool": "t"}],
        )
        card = self._card(p, "sc1")
        assert card["visual"] is not None
        assert card["visual"]["exists"] is False

    def test_renderable_prefers_existing_and_takes_exclude_missing(self, projects_root):
        # Two takes: one real png, one missing. Active = the real one;
        # takes carries only renderable (showable) entries.
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "generated", "start_seconds": 0, "end_seconds": 5}],
            [
                {"id": "a1", "type": "image", "path": "assets/images/real.png", "scene_id": "sc1", "source_tool": "t"},
                {"id": "a2", "type": "image", "path": "assets/images/missing.png", "scene_id": "sc1", "source_tool": "t"},
            ],
        )
        (p / "assets" / "images" / "real.png").write_bytes(b"\x89PNG")
        card = self._card(p, "sc1")
        assert card["visual"]["exists"] is True
        assert card["visual"]["path"].endswith("real.png")
        assert [t["path"].split("/")[-1] for t in card["takes"]] == ["real.png"]
