"""Install-state snapshot and video-key scan (no secrets)."""

from __future__ import annotations

from openmontage.mcp.bootstrap.install_state import (
    parse_dotenv_filled_names,
    scan_video_keys,
    snapshot_install_state,
    video_channel_names_from_example,
)


EXAMPLE = """
## 【二、视频生成专项服务】

AGNES_API_KEY=
TOKENHUB_API_KEY=
TOKENHUB_BASE_URL=https://example.invalid
FAL_KEY=
KLING_API_KEY=

## 【三、配音服务】

OPENAI_API_KEY=
ELEVENLABS_API_KEY=
"""


def test_video_section_names_are_keyish_only() -> None:
    names = video_channel_names_from_example(EXAMPLE)
    assert names == ["AGNES_API_KEY", "TOKENHUB_API_KEY", "FAL_KEY", "KLING_API_KEY"]
    assert "TOKENHUB_BASE_URL" not in names
    assert "OPENAI_API_KEY" not in names


def test_empty_and_placeholder_env_values_are_absent() -> None:
    text = "TOKENHUB_API_KEY=\nAGNES_API_KEY=changeme\nFAL_KEY=\"\"\nKLING_API_KEY=real-secret-value\n"
    filled = parse_dotenv_filled_names(
        text, ["AGNES_API_KEY", "TOKENHUB_API_KEY", "FAL_KEY", "KLING_API_KEY"]
    )
    assert filled == ["KLING_API_KEY"]


def test_scan_and_snapshot_never_write_secret_values(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=th-secret-do-not-leak-123\nAGNES_API_KEY=\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KLING_API_KEY", "kling-secret-do-not-leak-456")
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))

    scan = scan_video_keys(repo_root=tmp_path)
    assert scan["video_key_present"] is True
    assert "TOKENHUB_API_KEY" in scan["video_key_names_present"]
    assert "KLING_API_KEY" in scan["video_key_names_present"]
    dumped = str(scan)
    assert "th-secret-do-not-leak-123" not in dumped
    assert "kling-secret-do-not-leak-456" not in dumped

    snap = snapshot_install_state(
        repo_root=tmp_path,
        verify_ready=True,
        latest_project_id="shop-demo",
    )
    text = (tmp_path / ".openmontage" / "install-state.json").read_text(encoding="utf-8")
    assert "th-secret-do-not-leak-123" not in text
    assert "kling-secret-do-not-leak-456" not in text
    assert snap["state"]["verify_ready"] is True
    assert snap["state"]["latest_project_id"] == "shop-demo"
    assert snap["state"]["existing_project_count"] == 0
    assert snap["state"]["video_key_present"] is True
    assert "TOKENHUB_API_KEY" in snap["state"]["video_key_names_present"]


def test_snapshot_counts_existing_projects(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    project = tmp_path / "projects" / "used-before"
    project.mkdir(parents=True)
    (project / "project.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    snap = snapshot_install_state(repo_root=tmp_path)
    assert snap["state"]["existing_project_count"] == 1
    assert snap["state"]["verify_ready"] is False


def test_snapshot_keeps_project_id_when_rescan(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    monkeypatch.delenv("OPENMONTAGE_PROJECTS_DIR", raising=False)
    snapshot_install_state(repo_root=tmp_path, latest_project_id="keep-me")
    again = snapshot_install_state(repo_root=tmp_path, verify_ready=False)
    assert again["state"]["latest_project_id"] == "keep-me"
    assert again["state"]["verify_ready"] is False
    assert again["state"]["existing_project_count"] == 0


def test_repo_env_example_excludes_oss_and_includes_aliases() -> None:
    from pathlib import Path

    from openmontage.mcp.bootstrap.tools import REPO_ROOT

    text = (Path(REPO_ROOT) / ".env-example.md").read_text(encoding="utf-8")
    names = video_channel_names_from_example(text)
    assert "AGNES_API_KEY" in names
    assert "AGNES_AI_API_KEY" in names
    assert "TOKENHUB_API_KEY" in names
    assert "TENCENT_TOKENHUB_API_KEY" in names
    assert "OSS_ACCESS_KEY_ID" not in names
    assert "OSS_ACCESS_KEY_SECRET" not in names
    assert "OPENAI_API_KEY" not in names
