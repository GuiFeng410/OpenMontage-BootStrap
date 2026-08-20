"""Zero-key ambient BGM synthesis for Error-Handling E01 fallback (phase 3).

Generates a soft multi-sine pad as WAV under ``assets/music/`` — no paid APIs.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import DoctorError
from openmontage.mcp.common.sandbox import project_dir, require_projects_root

# Soft ambient chord-ish partials (Hz) — intentionally quiet but audible.
_PARTIALS = (
    (110.0, 0.18),
    (165.0, 0.12),
    (220.0, 0.10),
    (330.0, 0.06),
    (440.0, 0.04),
)


def synthesize_ambient_wav(
    output_path: Path,
    *,
    duration_seconds: float = 64.0,
    sample_rate: int = 44100,
) -> Path:
    """Write a mono 16-bit PCM WAV ambient bed to ``output_path``."""
    dur = max(2.0, float(duration_seconds))
    sr = int(sample_rate)
    n = int(dur * sr)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build samples with simple attack/release envelope
    attack = int(0.5 * sr)
    release = int(1.5 * sr)
    frames = bytearray()
    for i in range(n):
        t = i / sr
        sample = 0.0
        for freq, amp in _PARTIALS:
            sample += amp * math.sin(2.0 * math.pi * freq * t)
            # slow tremolo on higher partial
            if freq >= 330:
                sample += amp * 0.15 * math.sin(2.0 * math.pi * (freq * 1.01) * t)
        # gentle low noise-ish shimmer via slow LFO
        sample *= 0.85 + 0.15 * math.sin(2.0 * math.pi * 0.05 * t)
        env = 1.0
        if i < attack:
            env = i / max(1, attack)
        elif i > n - release:
            env = max(0.0, (n - i) / max(1, release))
        sample *= env
        # clamp
        sample = max(-0.95, min(0.95, sample * 0.55))
        ival = int(sample * 32767.0)
        frames += int(ival).to_bytes(2, byteorder="little", signed=True)

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))

    if not output_path.exists() or output_path.stat().st_size < 1000:
        raise DoctorError(f"synth BGM failed to write: {output_path}", code="synth_failed")
    return output_path


def synthesize_and_register_bgm(
    project_id: str,
    *,
    duration_seconds: float = 64.0,
    filename: str = "synth_ambient.wav",
    asset_id: str = "music_bgm",
    scene_id: str = "scene_01",
    volume: float = 0.25,
    archive_invalid: bool = True,
) -> dict[str, Any]:
    """Synthesize ambient WAV into assets/music and register as music_bgm."""
    from openmontage.mcp.common.captions_music import MUSIC_DIR, ensure_captions_music_dirs, register_music

    require_projects_root()
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise DoctorError(f"Project not found: {project_id}", code="not_found")

    ensure_captions_music_dirs(project_id)
    music_dir = pdir / MUSIC_DIR
    name = Path(filename).name
    if Path(name).suffix.lower() != ".wav":
        name = "synth_ambient.wav"
    dest = music_dir / name

    archived: list[str] = []
    if archive_invalid:
        invalid_dir = music_dir / "_invalid"
        for p in sorted(music_dir.iterdir()):
            if not p.is_file():
                continue
            if p.name == name:
                continue
            if p.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
                continue
            invalid_dir.mkdir(parents=True, exist_ok=True)
            target = invalid_dir / p.name
            # avoid clobber
            if target.exists():
                target = invalid_dir / f"{p.stem}_{p.stat().st_mtime_ns}{p.suffix}"
            p.rename(target)
            archived.append(str(target))

    synthesize_ambient_wav(dest, duration_seconds=duration_seconds)
    registered = register_music(
        project_id,
        filename=name,
        asset_id=asset_id,
        scene_id=scene_id,
        volume=volume,
        confirm=True,
    )
    # Clear skip-music hint if present
    hints = pdir / "artifacts" / "recovery_hints.json"
    if hints.exists():
        try:
            import json

            data = json.loads(hints.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["include_music"] = True
                data["bgm_replaced"] = True
                data["bgm_path"] = registered.get("rel_path")
                hints.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    return {
        "project_id": project_id,
        "synthesized_path": str(dest),
        "rel_path": registered.get("rel_path"),
        "asset_id": registered.get("asset_id"),
        "duration_seconds": duration_seconds,
        "archived_invalid": archived,
        "register": registered,
        "cost_usd": 0.0,
        "note": "Zero-key ambient BGM synthesized and registered. Listen before compose.",
    }
