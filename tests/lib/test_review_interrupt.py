from lib.review_interrupt import confirm_stop_ids, user_progress


def test_minimal_has_three_confirm_stops() -> None:
    assert confirm_stop_ids("minimal") == (
        "brief_locked",
        "assets_gate",
        "delivery_signoff",
    )
    assert len(confirm_stop_ids(None)) == 7


def test_minimal_progress_shows_generating_after_assets() -> None:
    stages = [
        {"name": "brief_locked", "status": "completed"},
        {"name": "assets_gate", "status": "completed"},
        {"name": "segment_build", "status": "in_progress"},
        {"name": "delivery_signoff", "status": "pending"},
    ]
    progress = user_progress(stages, "minimal")
    assert progress["label_zh"] == "生成中"


def test_legacy_preset_keeps_all_stops() -> None:
    assert "sample_review" in confirm_stop_ids("")
    assert "segment_build" in confirm_stop_ids(None)
