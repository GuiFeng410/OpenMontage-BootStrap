"""G4 ship-manifest contracts: positive core list vs forbidden runtime paths."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_pack_module():
    path = ROOT / "distribution" / "pack_runtime.py"
    spec = importlib.util.spec_from_file_location("om_pack_runtime", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PACK = _load_pack_module()

REQUIRED_CORE_DIRS = {
    "lib",
    "src/openmontage",
    "openmontage",
    "backlot",
    "product",
    "schemas",
    "styles",
    "tools",
    "skills",
    "runtimes/remotion",
    "distribution/manifests",
}
REQUIRED_CORE_FILES = {
    "AGENTS.md",
    "AGENT_GUIDE.md",
    ".env.example",
    "requirements.txt",
    "setup.py",
    "config.yaml",
}


def load_ship_manifest() -> dict:
    return PACK.load_ship_manifest(ROOT)


@pytest.fixture(scope="module")
def packed_runtime(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    dest = tmp_path_factory.mktemp("runtime")
    result = PACK.pack_runtime(ROOT, dest)
    return dest, result


def _core_entries(manifest: dict) -> set[str]:
    core = manifest["core"]
    return set(core["files"]) | set(core["dirs"])


def test_ship_manifest_exists_and_has_required_keys() -> None:
    manifest = load_ship_manifest()
    assert manifest["schema_version"] == 1
    assert manifest["layout"] == "tree-a"
    for key in (
        "core",
        "optional",
        "forbidden",
        "forbidden_globs",
        "developer_only",
        "remotion",
        "copy_skip_dir_names",
    ):
        assert key in manifest
    assert "files" in manifest["core"] and "dirs" in manifest["core"]


def test_core_paths_exist_in_factory_checkout() -> None:
    manifest = load_ship_manifest()
    missing: list[str] = []
    for rel in manifest["core"]["files"]:
        if not (ROOT / rel).is_file():
            missing.append(rel)
    for rel in manifest["core"]["dirs"]:
        if not (ROOT / rel).is_dir():
            missing.append(rel)
    assert missing == []


def test_required_core_entries_are_listed() -> None:
    entries = _core_entries(load_ship_manifest())
    assert REQUIRED_CORE_DIRS <= entries
    assert REQUIRED_CORE_FILES <= entries


def test_forbidden_paths_are_not_in_core() -> None:
    manifest = load_ship_manifest()
    core = _core_entries(manifest)
    overlap = core & set(manifest["forbidden"])
    assert overlap == set(), f"forbidden entries listed in core: {sorted(overlap)}"


def test_env_example_is_core_and_env_is_forbidden() -> None:
    manifest = load_ship_manifest()
    assert ".env.example" in manifest["core"]["files"]
    assert ".env" in manifest["forbidden"]
    assert ".env" not in manifest["core"]["files"]


def test_tests_and_agent_workspace_are_forbidden_not_core() -> None:
    manifest = load_ship_manifest()
    core = _core_entries(manifest)
    for name in ("tests", "Agent-Docs", "Agent-ReadMe", "Agent-Temp", "projects"):
        assert name in manifest["forbidden"]
        assert name not in core


def test_optional_does_not_include_forbidden() -> None:
    manifest = load_ship_manifest()
    optional = set(manifest["optional"]["files"]) | set(manifest["optional"]["dirs"])
    overlap = optional & set(manifest["forbidden"])
    assert overlap == set()


def test_copy_skip_covers_dependency_and_cache_dirs() -> None:
    skip = set(load_ship_manifest()["copy_skip_dir_names"])
    assert {"node_modules", "__pycache__", ".pytest_cache", ".git", ".venv"} <= skip


def test_remotion_excludes_are_recorded() -> None:
    remotion = load_ship_manifest()["remotion"]
    assert remotion["root"] == "runtimes/remotion"
    exclude_dirs = set(remotion["exclude_dirs"])
    assert {"node_modules", "out", ".cache", "projects"} <= exclude_dirs
    assert "src/Bangle*.tsx" in remotion["exclude_globs"]


def test_pack_runtime_copies_core_and_omits_forbidden(packed_runtime: tuple[Path, dict]) -> None:
    dest, result = packed_runtime
    assert Path(result["dest"]) == dest.resolve()
    assert result["files_copied"] > 0
    assert result["version"]
    assert (dest / "lib").is_dir()
    assert (dest / "src" / "openmontage").is_dir()
    assert (dest / "src" / "openmontage" / "__init__.py").is_file()
    assert (dest / "openmontage").is_dir()
    assert (dest / "openmontage" / "skills" / "README.md").is_file()
    assert (dest / "openmontage" / "__init__.py").is_file()
    assert (dest / "backlot").is_dir()
    assert (dest / "product" / "pipelines").is_dir()
    assert (dest / "product" / "schemas").is_dir()
    assert (dest / "product" / "styles").is_dir()
    assert (dest / "schemas").is_dir()
    assert (dest / "schemas" / "artifacts" / "__init__.py").is_file()
    assert (dest / "styles" / "playbook_loader.py").is_file()
    assert (dest / ".env.example").is_file()
    assert (dest / "distribution" / "manifests" / "release-manifest.json").is_file()
    for name in (".env", "projects", "tests", "Agent-Docs"):
        assert not (dest / name).exists()
    assert not (dest / "ink-theater").exists()
    assert not (dest / "requirements-gpu.txt").exists()


def test_pack_runtime_refuses_nonempty_dest(tmp_path: Path) -> None:
    dest = tmp_path / "runtime"
    dest.mkdir()
    (dest / "stale.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(PACK.PackError, match="empty"):
        PACK.pack_runtime(ROOT, dest)


def test_pack_runtime_skips_remotion_projects_and_bangle(
    packed_runtime: tuple[Path, dict],
) -> None:
    dest, _result = packed_runtime
    remotion_root = dest / "runtimes" / "remotion"
    assert not (remotion_root / "projects").exists()
    assert not (remotion_root / "node_modules").exists()
    src = remotion_root / "src"
    assert src.is_dir()
    assert list(src.glob("Bangle*.tsx")) == []
    assert not (dest / "openmontage" / "skills" / "openmontage-bootstrap-01-installer.zip").exists()


def test_verify_package_accepts_packed_runtime(packed_runtime: tuple[Path, dict]) -> None:
    dest, _result = packed_runtime
    payload = PACK.verify_package(dest)
    assert payload["ok"] is True
    assert Path(payload["dest"]) == dest.resolve()
    assert payload["missing"] == []
    assert payload["forbidden_present"] == []


def test_verify_package_rejects_incomplete_dest(tmp_path: Path) -> None:
    dest = tmp_path / "incomplete"
    dest.mkdir()
    with pytest.raises(PACK.PackError, match="ship-manifest"):
        PACK.verify_package(dest)


def test_packed_runtime_is_discoverable_as_repo_root(
    packed_runtime: tuple[Path, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dest, _result = packed_runtime
    monkeypatch.setenv("OPENMONTAGE_REPO_ROOT", str(dest))
    from lib.paths import WorkspacePaths, get_workspace

    assert WorkspacePaths.discover().repo_root == dest.resolve()
    assert get_workspace().repo_root == dest.resolve()
    assert (dest / "distribution" / "manifests" / "release-manifest.json").is_file()
