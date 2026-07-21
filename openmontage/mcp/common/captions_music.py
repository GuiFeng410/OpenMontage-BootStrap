"""Captions / copy helpers for BootStrap captions-music Skill (phase B)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import DoctorError
from openmontage.mcp.common.sandbox import project_dir, require_projects_root, resolve_under_projects

COPY_DIR = "assets/copy"
MUSIC_DIR = "assets/music"
SUBS_DIR = "assets/subs"
AUDIO_DIR = "assets/audio"

COPY_EXTS = {".txt", ".md"}
MUSIC_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
SUBS_EXTS = {".srt", ".vtt"}


def _project_root(project_id: str) -> Path:
    require_projects_root()
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise DoctorError(f"Project not found: {project_id}", code="not_found")
    return pdir


def ensure_captions_music_dirs(project_id: str) -> dict[str, Any]:
    pdir = _project_root(project_id)
    created: list[str] = []
    paths: dict[str, str] = {}
    for rel in (COPY_DIR, MUSIC_DIR, SUBS_DIR, AUDIO_DIR, "artifacts"):
        target = pdir / rel
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(rel)
        paths[rel] = str(target)
    return {"project_id": project_id, "dirs": paths, "created": created}


def _list_files(folder: Path, exts: set[str]) -> list[dict[str, str]]:
    if not folder.exists():
        return []
    rows: list[dict[str, str]] = []
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in exts:
            rows.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "rel": path.name,
                    "suffix": path.suffix.lower(),
                }
            )
    return rows


def scan_copy_music(project_id: str) -> dict[str, Any]:
    ensure = ensure_captions_music_dirs(project_id)
    pdir = _project_root(project_id)
    copy_files = _list_files(pdir / COPY_DIR, COPY_EXTS)
    music_files = _list_files(pdir / MUSIC_DIR, MUSIC_EXTS)
    subs_files = _list_files(pdir / SUBS_DIR, SUBS_EXTS)
    return {
        "project_id": project_id,
        "dirs": ensure["dirs"],
        "copy_files": copy_files,
        "music_files": music_files,
        "subs_files": subs_files,
        "has_copy": bool(copy_files),
        "has_music": bool(music_files),
        "has_subs": bool(subs_files),
        "next_step": (
            "Use existing assets/copy file, or draft a short script and "
            "produce_write_copy after user approval."
            if not copy_files
            else "Call produce_segment_copy_to_subtitles after user confirms the copy."
        ),
    }


def write_copy(
    project_id: str,
    content: str,
    filename: str = "script.txt",
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        from openmontage.mcp.common.errors import ConfigError

        raise ConfigError(
            "produce_write_copy requires confirm=true after the user approved the script text."
        )
    text = (content or "").strip()
    if not text:
        raise DoctorError("content is empty", code="bad_request")
    name = Path(filename).name
    if not name or Path(name).suffix.lower() not in COPY_EXTS:
        name = "script.txt"
    ensure_captions_music_dirs(project_id)
    pdir = _project_root(project_id)
    path = pdir / COPY_DIR / name
    path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    return {
        "project_id": project_id,
        "path": str(path),
        "rel_path": f"{COPY_DIR}/{name}",
        "bytes": path.stat().st_size,
        "char_count": len(text),
    }


def import_copy(
    project_id: str,
    source_path: str,
    filename: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        from openmontage.mcp.common.errors import ConfigError

        raise ConfigError(
            "produce_import_copy requires confirm=true after the user approved importing their file."
        )
    src = resolve_under_projects(source_path)
    if not src.exists() or not src.is_file():
        # Also allow absolute path if it is under projects root already resolved
        raise DoctorError(f"source_path not found under projects sandbox: {source_path}", code="not_found")
    if src.suffix.lower() not in COPY_EXTS:
        raise DoctorError(f"copy file must be one of {sorted(COPY_EXTS)}", code="bad_request")
    ensure_captions_music_dirs(project_id)
    pdir = _project_root(project_id)
    name = Path(filename).name if filename else src.name
    if Path(name).suffix.lower() not in COPY_EXTS:
        name = src.name
    dest = pdir / COPY_DIR / name
    shutil.copy2(src, dest)
    text = dest.read_text(encoding="utf-8")
    return {
        "project_id": project_id,
        "path": str(dest),
        "rel_path": f"{COPY_DIR}/{name}",
        "bytes": dest.stat().st_size,
        "char_count": len(text),
        "imported_from": str(src),
    }


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?．.])\s*")


def split_copy_into_cues(
    text: str,
    *,
    chars_per_second: float = 4.0,
    min_cue_seconds: float = 1.2,
    max_cue_chars: int = 42,
) -> list[dict[str, Any]]:
    """Heuristic split for BootStrap when no ASR timestamps exist."""
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    cps = max(1.0, float(chars_per_second))
    min_dur = max(0.4, float(min_cue_seconds))
    max_chars = max(12, int(max_cue_chars))

    blocks: list[str] = []
    for para in raw.split("\n"):
        para = para.strip()
        if not para:
            continue
        parts = [p.strip() for p in _SENTENCE_SPLIT.split(para) if p and p.strip()]
        blocks.extend(parts or [para])

    cues_text: list[str] = []
    for block in blocks:
        if len(block) <= max_chars:
            cues_text.append(block)
            continue
        buf = ""
        for ch in block:
            if len(buf) >= max_chars and ch in "，,、；; ":
                cues_text.append(buf.strip())
                buf = ""
                continue
            buf += ch
            if len(buf) >= max_chars * 2:
                cues_text.append(buf.strip())
                buf = ""
        if buf.strip():
            cues_text.append(buf.strip())

    segments: list[dict[str, Any]] = []
    t = 0.0
    for i, cue in enumerate(cues_text):
        dur = max(min_dur, len(cue) / cps)
        start = round(t, 3)
        end = round(t + dur, 3)
        segments.append({"text": cue, "start": start, "end": end, "index": i})
        t = end
    return segments


def read_primary_copy(project_id: str, filename: str = "") -> tuple[Path, str]:
    pdir = _project_root(project_id)
    copy_dir = pdir / COPY_DIR
    if filename:
        path = copy_dir / Path(filename).name
        if not path.exists():
            raise DoctorError(f"copy file not found: {filename}", code="not_found")
    else:
        files = _list_files(copy_dir, COPY_EXTS)
        if not files:
            raise DoctorError(
                "No copy in assets/copy/. Draft a script and produce_write_copy(confirm=true) first.",
                code="not_found",
            )
        path = Path(files[0]["path"])
    return path, path.read_text(encoding="utf-8")


def _pick_music_file(project_id: str, filename: str = "") -> Path:
    pdir = _project_root(project_id)
    music_dir = pdir / MUSIC_DIR
    if filename:
        path = music_dir / Path(filename).name
        if not path.exists():
            raise DoctorError(f"music file not found: {filename}", code="not_found")
        return path
    files = _list_files(music_dir, MUSIC_EXTS)
    if not files:
        raise DoctorError(
            "No BGM in assets/music/. Import with produce_import_music(confirm=true) "
            "or continue without music.",
            code="not_found",
        )
    return Path(files[0]["path"])


def import_music(
    project_id: str,
    source_path: str,
    filename: str = "",
    confirm: bool = False,
    asset_id: str = "music_bgm",
    scene_id: str = "scene_01",
    volume: float = 0.25,
) -> dict[str, Any]:
    if not confirm:
        from openmontage.mcp.common.errors import ConfigError

        raise ConfigError(
            "produce_import_music requires confirm=true after the user approved the BGM file."
        )
    src = resolve_under_projects(source_path)
    if not src.exists() or not src.is_file():
        raise DoctorError(f"source_path not found under projects sandbox: {source_path}", code="not_found")
    if src.suffix.lower() not in MUSIC_EXTS:
        raise DoctorError(f"music file must be one of {sorted(MUSIC_EXTS)}", code="bad_request")
    ensure_captions_music_dirs(project_id)
    pdir = _project_root(project_id)
    name = Path(filename).name if filename else src.name
    if Path(name).suffix.lower() not in MUSIC_EXTS:
        name = src.name
    dest = pdir / MUSIC_DIR / name
    shutil.copy2(src, dest)
    return register_music(
        project_id,
        filename=name,
        asset_id=asset_id,
        scene_id=scene_id,
        volume=volume,
        confirm=True,
    )


def register_music(
    project_id: str,
    filename: str = "",
    asset_id: str = "music_bgm",
    scene_id: str = "scene_01",
    volume: float = 0.25,
    confirm: bool = False,
) -> dict[str, Any]:
    """Register an existing assets/music file into asset_manifest."""
    if not confirm:
        from openmontage.mcp.common.errors import ConfigError

        raise ConfigError(
            "produce_register_music requires confirm=true after the user approved using this BGM."
        )
    from openmontage.mcp.common.asset_manifest import path_relative_to_project, upsert_asset_entry

    path = _pick_music_file(project_id, filename=filename)
    vol = max(0.0, min(1.0, float(volume)))
    aid = (asset_id or "music_bgm").strip() or "music_bgm"
    entry = {
        "id": aid,
        "type": "music",
        "path": path_relative_to_project(project_id, str(path)),
        "source_tool": "user_or_local_bgm",
        "scene_id": (scene_id or "scene_01").strip() or "scene_01",
        "subtype": "bgm",
        "generation_summary": f"BGM registered from {path.name}",
        "cost_usd": 0.0,
        "format": path.suffix.lstrip(".").lower(),
    }
    registered = upsert_asset_entry(project_id, entry)
    return {
        "project_id": project_id,
        "path": str(path),
        "rel_path": entry["path"],
        "asset_id": aid,
        "volume_default": vol,
        "manifest_entry": entry,
        "asset_manifest_path": registered["asset_manifest_path"],
        "asset_count": registered["asset_count"],
        "asset_manifest": registered["asset_manifest"],
    }


def build_compose_inputs(
    project_id: str,
    *,
    music_asset_id: str = "music_bgm",
    subtitle_asset_id: str = "subs_main",
    music_volume: float = 0.25,
    include_music: bool = True,
    include_subs: bool = True,
) -> dict[str, Any]:
    """Build edit_decisions + asset_manifest JSON for produce_compose_*."""
    from openmontage.mcp.common.asset_manifest import load_asset_manifest, manifest_path

    ensure_captions_music_dirs(project_id)
    manifest = load_asset_manifest(project_id)
    assets = [a for a in (manifest.get("assets") or []) if isinstance(a, dict)]
    by_id = {a.get("id"): a for a in assets if a.get("id")}

    warnings: list[str] = []
    audio: dict[str, Any] = {}
    subtitles: dict[str, Any] = {"enabled": False}

    if include_music:
        music = by_id.get(music_asset_id)
        if not music:
            # auto-register first music file if present but not in manifest
            music_files = _list_files(_project_root(project_id) / MUSIC_DIR, MUSIC_EXTS)
            if music_files:
                warnings.append(
                    f"music_asset_id={music_asset_id!r} missing in manifest; "
                    "call produce_register_music(confirm=true) first."
                )
            else:
                warnings.append("No BGM registered; compose will run without audio.music.")
        else:
            audio["music"] = {
                "asset_id": music_asset_id,
                "volume": max(0.0, min(1.0, float(music_volume))),
                "fade_in_seconds": 0.5,
                "fade_out_seconds": 0.5,
                "ducking": True,
            }

    if include_subs:
        sub = by_id.get(subtitle_asset_id)
        if not sub:
            warnings.append(
                f"subtitle_asset_id={subtitle_asset_id!r} missing; "
                "run produce_segment_copy_to_subtitles first or set include_subs=false."
            )
        else:
            subtitles = {
                "enabled": True,
                "source": subtitle_asset_id,
                "style": "sentence",
                "position": "bottom-center",
            }

    edit = {
        "version": "1.0",
        "project_id": project_id,
        "audio": audio,
        "subtitles": subtitles,
        "notes": (
            "BootStrap captions-music phase C bundle. "
            "Timeline cuts still come from produce/scene plan. "
            "FFmpeg duck mix is optional via produce_mix_narration_and_music."
        ),
    }

    import json

    mpath = manifest_path(project_id)
    return {
        "project_id": project_id,
        "asset_manifest_path": str(mpath),
        "asset_manifest": manifest,
        "asset_manifest_json": json.dumps(manifest, ensure_ascii=False),
        "edit_decisions": edit,
        "edit_decisions_json": json.dumps(edit, ensure_ascii=False),
        "has_music": bool(audio.get("music")),
        "has_subtitles": bool(subtitles.get("enabled")),
        "warnings": warnings,
        "compose_hint": (
            "Pass edit_decisions_json + asset_manifest_json to "
            "produce_compose_preflight / produce_compose_start. "
            "If using FFmpeg path that needs a single audio_path, first call "
            "produce_mix_narration_and_music (requires ffmpeg) and mux the mixed file."
        ),
        "mix_dependency": (
            "Full narration+BGM duck mix uses tools.audio_mixer via "
            "produce_mix_narration_and_music; requires ffmpeg on PATH. "
            "Without mix, Remotion/compose may still read asset_manifest music "
            "entries when the runtime supports edit_decisions.audio.music."
        ),
    }
