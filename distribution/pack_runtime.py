"""Copy a user runtime package from the factory checkout using ship-manifest.json."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


class PackError(ValueError):
    """Raised when the destination cannot receive a runtime package."""


def load_ship_manifest(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root) / "distribution" / "manifests" / "ship-manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _release_version(repo_root: Path) -> str:
    payload = json.loads(
        (Path(repo_root) / "distribution" / "manifests" / "release-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return str(payload["version"])


def _ensure_empty_dest(dest: Path) -> None:
    if dest.exists() and dest.is_file():
        raise PackError(f"dest must be a directory, not a file: {dest}")
    if dest.exists() and any(dest.iterdir()):
        raise PackError(f"dest must be empty: {dest}")
    dest.mkdir(parents=True, exist_ok=True)


def _within_repo(repo_root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    resolved.relative_to(repo_root.resolve())
    return resolved


def _make_ignore(repo_root: Path, manifest: dict[str, Any]):
    skip_dirs = set(manifest["copy_skip_dir_names"])
    forbidden = set(manifest["forbidden"])
    forbidden_globs = list(manifest["forbidden_globs"])
    remotion = manifest["remotion"]
    remotion_root = (repo_root / remotion["root"]).resolve()
    remotion_exclude_dirs = set(remotion["exclude_dirs"])
    remotion_globs = list(remotion["exclude_globs"])
    extra_files = {"openmontage-bootstrap-01-installer.zip"}

    def ignore(directory: str, names: list[str]) -> set[str]:
        directory_path = Path(directory).resolve()
        ignored: set[str] = set()
        rel_to_remotion: Path | None
        try:
            rel_to_remotion = directory_path.relative_to(remotion_root)
        except ValueError:
            rel_to_remotion = None
        for name in names:
            if name in skip_dirs or name in forbidden or name in extra_files or name == ".env":
                ignored.add(name)
                continue
            if any(fnmatch(name, pattern) for pattern in forbidden_globs):
                ignored.add(name)
                continue
            if rel_to_remotion is not None:
                if name in remotion_exclude_dirs:
                    ignored.add(name)
                    continue
                candidate = (rel_to_remotion / name).as_posix()
                if any(fnmatch(candidate, pattern) for pattern in remotion_globs):
                    ignored.add(name)
        return ignored

    return ignore


def _count_files(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file())


def pack_runtime(
    repo_root: Path,
    dest: Path,
    *,
    include_optional: bool = False,
) -> dict[str, Any]:
    """Copy core (and optional if asked) into empty dest. Never copy secrets or projects."""
    repo_root = Path(repo_root).resolve()
    dest = Path(dest)
    manifest = load_ship_manifest(repo_root)
    _ensure_empty_dest(dest)
    ignore = _make_ignore(repo_root, manifest)

    files = list(manifest["core"]["files"])
    dirs = list(manifest["core"]["dirs"])
    if include_optional:
        files.extend(manifest["optional"]["files"])
        dirs.extend(manifest["optional"]["dirs"])

    forbidden = set(manifest["forbidden"])
    for rel in files + dirs:
        if rel in forbidden or Path(rel).name in forbidden:
            raise PackError(f"refusing to pack forbidden path: {rel}")

    for rel in files:
        src = _within_repo(repo_root, repo_root / rel)
        if src.name == ".env":
            raise PackError("refusing to copy .env")
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)

    for rel in dirs:
        src = _within_repo(repo_root, repo_root / rel)
        target = dest / rel
        if target.exists():
            raise PackError(f"destination already has {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, target, ignore=ignore, dirs_exist_ok=False)

    version = _release_version(repo_root)
    result = {
        "dest": str(dest.resolve()),
        "files_copied": _count_files(dest),
        "version": version,
    }
    verify_package(dest)
    return result


def verify_package(dest: Path) -> dict[str, Any]:
    """Check release-manifest.json exists, required core dirs exist, forbidden names absent.

    Does not create a venv or call paid APIs.
    """
    dest = Path(dest).resolve()
    if not dest.is_dir():
        raise PackError(f"package dest is not a directory: {dest}")
    ship_path = dest / "distribution" / "manifests" / "ship-manifest.json"
    if not ship_path.is_file():
        raise PackError(f"missing ship-manifest.json: {ship_path}")
    manifest = load_ship_manifest(dest)
    missing: list[str] = []
    forbidden_present: list[str] = []
    release_rel = "distribution/manifests/release-manifest.json"
    if not (dest / release_rel).is_file():
        missing.append(release_rel)
    for rel in manifest["core"]["files"]:
        if not (dest / rel).is_file():
            missing.append(rel)
    for rel in manifest["core"]["dirs"]:
        if not (dest / rel).is_dir():
            missing.append(rel)
    for name in manifest["forbidden"]:
        if (dest / name).exists():
            forbidden_present.append(name)
    if missing or forbidden_present:
        raise PackError(
            "package structure invalid: "
            f"missing={missing!r} forbidden_present={forbidden_present!r}"
        )
    return {
        "ok": True,
        "dest": str(dest),
        "version": _release_version(dest),
        "missing": [],
        "forbidden_present": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pack an OpenMontage user runtime directory.")
    parser.add_argument("--dest", required=True, help="Empty or missing destination directory")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Factory checkout root",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also copy optional dirs/files from ship-manifest",
    )
    args = parser.parse_args(argv)
    result = pack_runtime(
        Path(args.repo_root),
        Path(args.dest),
        include_optional=args.include_optional,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
