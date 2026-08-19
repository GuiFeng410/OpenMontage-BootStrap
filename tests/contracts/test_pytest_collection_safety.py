"""Keep generated project scripts outside the unit-test discovery boundary."""

from configparser import ConfigParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generated_projects_are_excluded_from_pytest_discovery() -> None:
    config = ConfigParser()
    loaded = config.read(REPO_ROOT / "pytest.ini", encoding="utf-8")

    assert loaded
    excluded = set(config.get("pytest", "norecursedirs").split())
    assert "projects" in excluded
