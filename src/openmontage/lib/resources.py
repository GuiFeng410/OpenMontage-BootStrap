"""Product resource locator — logical names to current checkout paths.

G5 may remap the table; callers should use ResourceLocator methods, not
hard-coded concatenations off repo root. Candidate paths are preferred first;
the last entry is the frozen checkout fallback when the new path is absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lib.paths import WorkspacePaths, get_workspace

# Logical name → candidate paths relative to repo root, preferred first.
# G5 layout is tried before the frozen checkout path.
_LOGICAL: dict[str, tuple[str, ...]] = {
    "pipelines": ("product/pipelines", "pipeline_defs"),
    "styles": ("product/styles", "styles"),
    "schemas": ("product/schemas", "schemas"),
    "skills.bootstrap": ("skills/bootstrap", "openmontage/skills"),
    "runtimes.remotion": ("runtimes/remotion", "remotion-composer"),
    "distribution.manifests": ("distribution/manifests",),
    "config.yaml": ("config.yaml",),
}


@dataclass(frozen=True, slots=True)
class ResourceLocator:
    repo_root: Path

    def resolve(self, logical: str) -> Path:
        candidates = _LOGICAL.get(logical)
        if candidates is None:
            known = ", ".join(sorted(_LOGICAL))
            raise KeyError(f"unknown resource logical name: {logical!r} (known: {known})")
        fallback = (self.repo_root / candidates[-1]).resolve()
        for rel in candidates:
            path = self.repo_root / rel
            if path.exists():
                return path.resolve()
        return fallback

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
