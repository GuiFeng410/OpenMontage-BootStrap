"""Copy .env.example to .env when missing."""

from __future__ import annotations

import pytest

from openmontage.mcp.bootstrap.env_file import ensure_env_file
from openmontage.mcp.common.errors import ConfigError


def test_ensure_env_file_dry_run_when_missing(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("FOO=bar\n", encoding="utf-8")
    result = ensure_env_file(repo_root=tmp_path, dry_run=True, confirm_execute=False)
    assert result["executed"] is False
    assert result["skipped"] is False
    assert not (tmp_path / ".env").exists()


def test_ensure_env_file_copies_once(tmp_path):
    (tmp_path / ".env.example").write_text("FOO=bar\n", encoding="utf-8")
    first = ensure_env_file(repo_root=tmp_path, dry_run=False, confirm_execute=True)
    assert first["executed"] is True
    env = tmp_path / ".env"
    assert env.read_text(encoding="utf-8") == "FOO=bar\n"
    env.write_text("FOO=secret\n", encoding="utf-8")
    second = ensure_env_file(repo_root=tmp_path, dry_run=False, confirm_execute=True)
    assert second["skipped"] is True
    assert env.read_text(encoding="utf-8") == "FOO=secret\n"


def test_ensure_env_file_requires_confirm(tmp_path):
    (tmp_path / ".env.example").write_text("FOO=bar\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="confirm_execute"):
        ensure_env_file(repo_root=tmp_path, dry_run=False, confirm_execute=False)
