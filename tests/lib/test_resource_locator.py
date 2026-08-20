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
    assert loc.bootstrap_skills() == (loc.repo_root / "skills" / "bootstrap").resolve()
    assert loc.remotion_composer() == (loc.repo_root / "runtimes" / "remotion").resolve()
    assert loc.pipeline_defs() == (loc.repo_root / "product" / "pipelines").resolve()
    assert loc.styles() == (loc.repo_root / "product" / "styles").resolve()
    assert loc.artifact_schemas() == (loc.repo_root / "product" / "schemas" / "artifacts").resolve()


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


def test_bootstrap_skills_prefers_new_layout_when_present(tmp_path: Path) -> None:
    new_root = tmp_path / "skills" / "bootstrap"
    old_root = tmp_path / "openmontage" / "skills"
    new_root.mkdir(parents=True)
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.bootstrap_skills() == new_root.resolve()


def test_bootstrap_skills_falls_back_to_openmontage_skills(tmp_path: Path) -> None:
    old_root = tmp_path / "openmontage" / "skills"
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.bootstrap_skills() == old_root.resolve()
    assert not (tmp_path / "skills" / "bootstrap").exists()


def test_remotion_prefers_runtimes_layout_when_present(tmp_path: Path) -> None:
    new_root = tmp_path / "runtimes" / "remotion"
    old_root = tmp_path / "remotion-composer"
    new_root.mkdir(parents=True)
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.remotion_composer() == new_root.resolve()


def test_remotion_falls_back_to_remotion_composer(tmp_path: Path) -> None:
    old_root = tmp_path / "remotion-composer"
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.remotion_composer() == old_root.resolve()
    assert not (tmp_path / "runtimes" / "remotion").exists()


def test_pipelines_prefers_product_layout_when_present(tmp_path: Path) -> None:
    new_root = tmp_path / "product" / "pipelines"
    old_root = tmp_path / "pipeline_defs"
    new_root.mkdir(parents=True)
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.pipeline_defs() == new_root.resolve()


def test_pipelines_falls_back_to_pipeline_defs(tmp_path: Path) -> None:
    old_root = tmp_path / "pipeline_defs"
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.pipeline_defs() == old_root.resolve()
    assert not (tmp_path / "product" / "pipelines").exists()


def test_styles_prefers_product_layout_when_present(tmp_path: Path) -> None:
    new_root = tmp_path / "product" / "styles"
    old_root = tmp_path / "styles"
    new_root.mkdir(parents=True)
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.styles() == new_root.resolve()


def test_styles_falls_back_to_styles(tmp_path: Path) -> None:
    old_root = tmp_path / "styles"
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.styles() == old_root.resolve()
    assert not (tmp_path / "product" / "styles").exists()


def test_schemas_prefers_product_layout_when_present(tmp_path: Path) -> None:
    new_root = tmp_path / "product" / "schemas"
    old_root = tmp_path / "schemas"
    new_root.mkdir(parents=True)
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.artifact_schemas() == (new_root / "artifacts").resolve()


def test_schemas_falls_back_to_schemas(tmp_path: Path) -> None:
    old_root = tmp_path / "schemas"
    old_root.mkdir(parents=True)
    loc = get_resources(WorkspacePaths(repo_root=tmp_path))
    assert loc.artifact_schemas() == (old_root / "artifacts").resolve()
    assert not (tmp_path / "product" / "schemas").exists()
