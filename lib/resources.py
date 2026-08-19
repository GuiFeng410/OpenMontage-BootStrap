"""Product resource locator — logical names to current checkout paths.

G5 may remap the table; callers should use ResourceLocator methods, not
hard-coded concatenations off repo root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lib.paths import WorkspacePaths, get_workspace

# Logical name → current physical path relative to repo root.
# Do not invent G5 destinations here.
_LOGICAL: dict[str, str] = {
    "pipelines": "pipeline_defs",
    "styles": "styles",
    "schemas": "schemas",
    "skills.bootstrap": "openmontage/skills",
    "runtimes.remotion": "remotion-composer",
    "distribution.manifests": "distribution/manifests",
    "config.yaml": "config.yaml",
}


@dataclass(frozen=True, slots=True)
class ResourceLocator:
    repo_root: Path

    def resolve(self, logical: str) -> Path:
        rel = _LOGICAL.get(logical)
        if rel is None:
            known = ", ".join(sorted(_LOGICAL))
            raise KeyError(f"unknown resource logical name: {logical!r} (known: {known})")
        return (self.repo_root / rel).resolve()

    def pipeline_defs(self) -> Path:
        return self.resolve("pipelines")

    def styles(self) -> Path:
        return self.resolve("styles")

    def checkpoint_schema(self) -> Path:
        return self.resolve("schemas") / "checkpoints" / "checkpoint.schema.json"

    def artifact_schemas(self) -> Path:
        return self.resolve("schemas") / "artifacts"

    def remotion_composer(self) -> Path:
        return self.resolve("runtimes.remotion")

    def bootstrap_skills(self) -> Path:
        return self.resolve("skills.bootstrap")

    def release_manifest(self) -> Path:
        return self.resolve("distribution.manifests") / "release-manifest.json"

    def config_yaml(self) -> Path:
        return self.resolve("config.yaml")


def get_resources(ws: WorkspacePaths | None = None) -> ResourceLocator:
    if ws is None:
        ws = get_workspace()
    return ResourceLocator(repo_root=ws.repo_root)
