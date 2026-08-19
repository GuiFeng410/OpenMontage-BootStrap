"""JsonStore atomic write and read behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.persistence.json_store import JsonStore


def test_write_atomic_adds_trailing_newline(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    JsonStore.write_atomic(target, {"ok": True})
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == {"ok": True}


def test_write_atomic_without_newline(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    JsonStore.write_atomic(target, {"ok": True}, newline=False)
    text = target.read_text(encoding="utf-8")
    assert not text.endswith("\n")
    assert json.loads(text) == {"ok": True}


def test_replace_failure_preserves_original_and_drops_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lib.persistence.json_store as json_store

    target = tmp_path / "state.json"
    JsonStore.write_atomic(target, {"keep": 1})
    before = target.read_bytes()

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(json_store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        JsonStore.write_atomic(target, {"keep": 2})
    assert target.read_bytes() == before
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_replace_retries_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lib.persistence.json_store as json_store

    target = tmp_path / "state.json"
    original_replace = json_store.os.replace
    attempts = 0

    def flaky_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise PermissionError("transient sharing violation")
        return original_replace(source, destination)

    monkeypatch.setattr(json_store.os, "replace", flaky_replace)
    JsonStore.write_atomic(target, {"ready": True}, replace_retries=3)
    assert attempts == 4
    assert json.loads(target.read_text(encoding="utf-8")) == {"ready": True}


def test_read_object_missing_modes(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    assert JsonStore.read_object(missing) == {}
    assert JsonStore.read_object(missing, missing="none") is None
    JsonStore.write_atomic(tmp_path / "obj.json", {"a": 1})
    assert JsonStore.read_object(tmp_path / "obj.json") == {"a": 1}
