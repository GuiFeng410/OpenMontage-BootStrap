"""Atomic JSON file persistence."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


class JsonStore:
    @staticmethod
    def read_object(path: Path, *, missing: str = "empty") -> dict[str, Any] | None:
        if not path.is_file():
            if missing == "empty":
                return {}
            if missing == "none":
                return None
            raise ValueError(f"unknown missing mode: {missing!r}")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"JSON root must be an object: {path}")
        return loaded

    @staticmethod
    def write_atomic(
        path: Path,
        data: Any,
        *,
        newline: bool = True,
        replace_retries: int = 0,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        if newline:
            payload += "\n"
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            attempts = replace_retries + 1
            for attempt in range(attempts):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt >= replace_retries:
                        raise
                    time.sleep(0.01 * (2**attempt))
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
