"""ResourceLocator maps logical names to current checkout paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.paths import WorkspacePaths
from lib.resources import get_resources


def test_locator_points_at_existing_product_paths() -> None:
    loc = get_resources()
    assert loc.pipeline_defs().is_dir()
    assert loc.styles().is_dir()
    assert loc.release_manifest().is_file()
    assert loc.remotion_composer().is_dir()
    assert (loc.remotion_composer() / "package.json").is_file()
    assert loc.config_yaml().is_file()
    assert loc.checkpoint_schema().is_file()
    assert loc.artifact_schemas().is_dir()
    assert loc.bootstrap_skills().is_dir()


def test_locator_follows_workspace_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifests = tmp_path / "distribution" / "manifests"
    manifests.mkdir(parents=True)
    (manifests / "release-manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pipeline_defs").mkdir()
    (tmp_path / "remotion-composer").mkdir()
    monkeypatch.setenv("OPENMONTAGE_REPO_ROOT", str(tmp_path))
    loc = get_resources()
    assert loc.repo_root == tmp_path.resolve()
    assert loc.pipeline_defs() == (tmp_path / "pipeline_defs").resolve()
    assert loc.remotion_composer() == (tmp_path / "remotion-composer").resolve()
    assert loc.release_manifest() == (manifests / "release-manifest.json").resolve()


def test_get_resources_accepts_explicit_workspace(tmp_path: Path) -> None:
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.styles() == (tmp_path / "styles").resolve()


def test_unknown_logical_name_raises() -> None:
    with pytest.raises(KeyError, match="unknown resource logical name"):
        get_resources().resolve("runtimes.hyperframes")
