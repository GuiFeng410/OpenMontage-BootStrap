"""Fail CI when tracked source files contain likely live provider API keys."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_ASSIGNMENT = re.compile(
    r"(?im)\bAGNES(?:_AI)?_API_KEY\s*=\s*"
    r"(?!\s*(?:$|#|\[|<|YOUR[_-]|REPLACE[_-]|EXAMPLE[_-]|TEST[_-]|FAKE[_-]))"
    r"([^\s`]+)"
)


def _tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item for item in result.stdout.decode().split("\0") if item]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings: list[str] = []
    for path in _tracked_files(root):
        if path.name == ".env" or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _ASSIGNMENT.search(text):
            findings.append(str(path.relative_to(root)))
    if findings:
        print("Potential live API key found in tracked files:", file=sys.stderr)
        print("\n".join(f" - {path}" for path in findings), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
