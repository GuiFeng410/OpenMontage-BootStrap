"""Start and poll a local produce job after minimal assets_gate.

Browser still does not generate. This module may call local compose.
Locked heavy with a video Key may call video_generate after the board
「开始出片」click (that click is the human confirm). It does not call
image generate, TTS generate, or stock downloads, and never switches
providers.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lib.board_advance import write_board_stop_overlay
from lib.checkpoint import read_checkpoint
from lib.paths import PROJECTS_DIR, REPO_ROOT
from lib.review_interrupt import normalize_review_preset

JOB_NAME = "produce_job.json"
OUTPUT_REL = "renders/final.mp4"
COMPOSE_WAIT_ZH = (
    "素材已确认，本机正在按锁定轻度合成成片，大约 1–3 分钟。请留在本页。"
)

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_FAILED = "failed"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"

_PAID_PROVIDERS = (
    "agnes",
    "kling",
    "seedance",
    "sora",
    "veo",
    "minimax",
    "runway",
)
_HEAVY_KEY_HINTS = {
    "agnes": ("AGNES_API_KEY", "AGNES_AI_API_KEY"),
    "kling": ("KLING_API_KEY",),
    "seedance": ("FAL_KEY", "FAL_AI_API_KEY"),
    "sora": ("OPENAI_API_KEY",),
    "veo": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "FAL_KEY", "FAL_AI_API_KEY"),
    "minimax": ("FAL_KEY", "FAL_AI_API_KEY"),
    "runway": ("RUNWAY_API_KEY", "RUNWAYML_API_SECRET"),
    "pixverse": ("PIXVERSE_API_KEY", "TOKENHUB_API_KEY"),
}


class ProduceJobError(Exception):
    def __init__(self, message: str, *, code: str = "produce_job") -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _project_dir(project_id: str, projects_dir: Path | None = None) -> Path:
    return Path(projects_dir or PROJECTS_DIR) / project_id


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def job_path(project_id: str, *, projects_dir: Path | None = None) -> Path:
    return _project_dir(project_id, projects_dir) / "artifacts" / JOB_NAME


def read_job(project_id: str, *, projects_dir: Path | None = None) -> dict[str, Any] | None:
    data = _read_json(job_path(project_id, projects_dir=projects_dir))
    return data or None


def write_job(
    project_id: str,
    payload: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    body = {
        "version": "1.0",
        "project_id": project_id,
        "updated_at": _now(),
        **payload,
    }
    _write_json(job_path(project_id, projects_dir=projects_dir), body)
    return body


def is_minimal(marker: dict[str, Any]) -> bool:
    profile = marker.get("production_profile") if isinstance(marker, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    return normalize_review_preset(
        profile.get("review_mode_preset") or profile.get("review_mode")
    ) == "minimal"


def assets_gate_completed(project_id: str, *, projects_dir: Path | None = None) -> bool:
    root = Path(projects_dir or PROJECTS_DIR)
    checkpoint = read_checkpoint(root, project_id, "assets_gate")
    return isinstance(checkpoint, dict) and checkpoint.get("status") == "completed"


def _has_final(project_id: str, *, projects_dir: Path | None = None) -> bool:
    path = _project_dir(project_id, projects_dir) / OUTPUT_REL
    return path.is_file() and path.stat().st_size > 0


def _profile(marker: dict[str, Any]) -> dict[str, Any]:
    raw = marker.get("production_profile") if isinstance(marker, dict) else {}
    return raw if isinstance(raw, dict) else {}


def _tier(profile: dict[str, Any]) -> str:
    value = str(profile.get("production_tier") or "light").strip().lower()
    if value in {"light", "medium", "heavy"}:
        return value
    return "light"


def _provider_id(profile: dict[str, Any], brief: dict[str, Any]) -> str:
    raw = " ".join(
        [
            str(profile.get("video_channel") or ""),
            str(profile.get("provider") or ""),
            str(profile.get("video_model") or profile.get("model") or ""),
            str(brief.get("video_channel") or ""),
            str(brief.get("provider") or ""),
        ]
    ).lower()
    for name in _HEAVY_KEY_HINTS:
        if name in raw:
            return name
    return ""


def _present_key_names() -> set[str]:
    names: set[str] = set()
    try:
        from openmontage.mcp.bootstrap.install_state import scan_stock_keys, scan_video_keys

        video = scan_video_keys(repo_root=REPO_ROOT, environ=dict(os.environ))
        stock = scan_stock_keys(repo_root=REPO_ROOT, environ=dict(os.environ))
        names.update(video.get("video_key_names_present") or [])
        names.update(stock.get("stock_key_names_present") or [])
    except Exception:
        pass
    for key, value in os.environ.items():
        if value and str(value).strip():
            names.add(key)
    return names


def key_gate(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Return a paused job payload when locked tier cannot run. None = compose OK."""
    profile = _profile(marker)
    tier = _tier(profile)
    if tier == "light":
        return None
    present = _present_key_names()
    if tier == "medium":
        source = str(profile.get("medium_source") or "user_assets").strip().lower()
        if source != "stock":
            return None
        if "PEXELS_API_KEY" in present or "PIXABAY_API_KEY" in present:
            return {
                "status": STATUS_PAUSED,
                "engine": "stock",
                "tier": tier,
                "code": "stock_not_auto",
                "friendly_zh": (
                    "已锁定中度 Stock，不降为轻度。"
                    "本页不自动下载素材；请刷新可用性后按锁定来源继续。"
                ),
            }
        return {
            "status": STATUS_PAUSED,
            "engine": "stock",
            "tier": tier,
            "code": "stock_key_missing",
            "friendly_zh": (
                "已锁定中度 Stock，但本机没有 Stock Key，不能改走轻度。"
                "请在本页刷新可用性，或回方案改档。"
            ),
        }
    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    hints = _HEAVY_KEY_HINTS.get(provider) or ()
    has_key = any(name in present for name in hints) if hints else bool(
        present.intersection(
            {name for group in _HEAVY_KEY_HINTS.values() for name in group}
        )
    )
    if not has_key:
        return {
            "status": STATUS_PAUSED,
            "engine": "paid_video",
            "tier": tier,
            "code": "video_key_missing",
            "friendly_zh": (
                "已锁定重度，不降为轻度。本机未检测到对应视频 Key。"
                "请在本页刷新可用性后再试。"
            ),
        }
    if provider not in _PAID_PROVIDERS:
        return {
            "status": STATUS_PAUSED,
            "engine": "paid_video",
            "tier": tier,
            "code": "video_channel_missing",
            "friendly_zh": (
                "已锁定重度，但不明确视频渠道，不能猜渠道、也不能改走轻度。"
                "请回方案确认渠道后再点开始出片。"
            ),
        }
    return None


def _beat_token(beat: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in beat) or "beat"


def _seg_rel(beat: str) -> str:
    return f"assets/video/seg_{_beat_token(beat)}.mp4"


def _sandbox_rel(project_id: str, rel: str) -> str:
    return f"{project_id}/{rel.replace(chr(92), '/')}"


def _aspect_ratio(width: int, height: int) -> str:
    if height > width:
        return "9:16"
    if width == height:
        return "1:1"
    return "16:9"


def _frame_size(profile: dict[str, Any]) -> tuple[int, int]:
    resolution = str(profile.get("resolution") or "1080x1920")
    if "x" in resolution:
        try:
            width, height = (int(part) for part in resolution.lower().split("x", 1))
            return width, height
        except ValueError:
            pass
    return 1080, 1920


def _cards_by_beat(project: Path) -> dict[str, dict[str, Any]]:
    cards = _read_json(project / "artifacts" / "segment_cards.json")
    out: dict[str, dict[str, Any]] = {}
    for item in cards.get("segments") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("beat") or item.get("id") or "").strip()
        if key:
            out[key] = item
    return out


def _segment_prompt(brief: dict[str, Any], card: dict[str, Any], beat: str) -> str:
    parts = [
        str(brief.get("theme") or "").strip(),
        str(card.get("shot_plan_zh") or "").strip(),
        str(card.get("copy_plan_zh") or "").strip(),
    ]
    text = "。".join(part for part in parts if part)
    return text or f"商品展示镜头 {beat}"


def _kling_duration(seconds: float) -> str:
    value = int(round(float(seconds) or 5))
    return str(min(15, max(3, value)))


def _video_extras(
    provider: str,
    still_path: str,
    duration: float,
    aspect: str,
) -> dict[str, Any]:
    if provider == "agnes":
        return {
            "operation": "image_to_video",
            "duration": duration,
            "aspect_ratio": aspect,
            "image_path": still_path,
        }
    if provider == "kling":
        return {
            "operation": "image_to_video",
            "duration": _kling_duration(duration),
            "reference_image_path": still_path,
        }
    return {
        "operation": "image_to_video",
        "duration": duration,
        "aspect_ratio": aspect,
        "image_path": still_path,
        "reference_image_path": still_path,
    }


def _plan_beats(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> list[dict[str, Any]]:
    project = _project_dir(project_id, projects_dir)
    plan = _read_json(project / "artifacts" / "video_plan.json")
    ledger = _read_json(project / "artifacts" / "asset_ledger.json")
    brief = _read_json(project / "artifacts" / "brief.json")
    profile = _profile(_read_json(project / "project.json"))
    cards = _cards_by_beat(project)
    segments = [item for item in (plan.get("segments") or []) if isinstance(item, dict)]
    if not segments:
        raise ProduceJobError("缺少 video_plan 分段，无法生成。", code="no_plan")
    by_beat: dict[str, str] = {}
    for entry in ledger.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        beats = entry.get("beats") or []
        if isinstance(beats, str):
            beats = [part.strip() for part in beats.split(",") if part.strip()]
        for beat in beats:
            by_beat[str(beat)] = path
    duration = float(brief.get("duration_seconds") or profile.get("duration_seconds") or 15)
    fallback = max(2.0, duration / max(1, len(segments)))
    rows: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        beat = str(segment.get("beat") or segment.get("id") or f"beat_{index + 1:02d}")
        still = str(segment.get("ref_image") or by_beat.get(beat) or "").strip()
        if not still:
            raise ProduceJobError(f"分段 {beat} 没有锁定图片。", code="missing_still")
        rows.append(
            {
                "beat": beat,
                "still": still,
                "span": _span_seconds(segment.get("t") or segment.get("time"), fallback),
                "prompt": _segment_prompt(brief, cards.get(beat) or {}, beat),
            }
        )
    return rows


def _clock_seconds(token: str) -> float:
    text = str(token or "").strip().rstrip("sS")
    if not text:
        return 0.0
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError:
        return 0.0


def _span_seconds(raw: Any, fallback: float) -> float:
    text = str(raw or "").strip()
    if not text or "-" not in text:
        return fallback
    left, right = text.split("-", 1)
    span = _clock_seconds(right) - _clock_seconds(left)
    return span if span >= 0.5 else fallback


def build_compose_bundle(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    plan = _read_json(project / "artifacts" / "video_plan.json")
    ledger = _read_json(project / "artifacts" / "asset_ledger.json")
    brief = _read_json(project / "artifacts" / "brief.json")
    marker = _read_json(project / "project.json")
    profile = _profile(marker)
    segments = [item for item in (plan.get("segments") or []) if isinstance(item, dict)]
    if not segments:
        raise ProduceJobError("缺少 video_plan 分段，无法合成。", code="no_plan")
    by_beat: dict[str, str] = {}
    assets: list[dict[str, Any]] = []
    for entry in ledger.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        beats = entry.get("beats") or []
        if isinstance(beats, str):
            beats = [part.strip() for part in beats.split(",") if part.strip()]
        for beat in beats:
            by_beat[str(beat)] = path
        asset_id = f"img_{len(assets) + 1:02d}"
        assets.append({"id": asset_id, "path": path, "type": "image", "kind": "image"})
        by_beat[f"__path__{path}"] = asset_id
    if not by_beat:
        raise ProduceJobError("账本没有可用图片，无法合成。", code="empty_ledger")
    duration = float(brief.get("duration_seconds") or profile.get("duration_seconds") or 15)
    fallback = max(2.0, duration / max(1, len(segments)))
    cuts: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        beat = str(segment.get("beat") or segment.get("id") or f"beat_{index + 1:02d}")
        still = str(segment.get("ref_image") or by_beat.get(beat) or "").strip()
        if not still:
            raise ProduceJobError(f"分段 {beat} 没有锁定图片。", code="missing_still")
        video_rel = _seg_rel(beat)
        video_path = project / video_rel
        source = still
        kind = "image"
        if video_path.is_file() and video_path.stat().st_size > 0:
            source = video_rel
            kind = "video"
            assets.append(
                {
                    "id": f"vid_{index + 1:02d}",
                    "path": video_rel,
                    "type": "video",
                    "kind": "video",
                }
            )
        span = _span_seconds(segment.get("t") or segment.get("time"), fallback)
        cuts.append(
            {
                "id": f"c{index + 1:02d}",
                "source": source,
                "in_seconds": 0,
                "out_seconds": round(span, 3),
                "reason": beat,
                "kind": kind,
            }
        )
    runtime = str(profile.get("render_runtime") or "remotion").strip().lower() or "remotion"
    width, height = _frame_size(profile)
    edit = {
        "version": "1.0",
        "project_id": project_id,
        "render_runtime": runtime,
        "cuts": cuts,
        "audio": {},
        "subtitles": {"enabled": False},
        "metadata": {
            "compose_target": {"width": width, "height": height, "fit": "cover"},
            "board_produce": True,
        },
    }
    manifest = {"version": "1.0", "assets": assets, "total_cost_usd": 0.0}
    return {"edit_decisions": edit, "asset_manifest": manifest}


def _refresh_overlay(
    project_id: str,
    friendly_zh: str,
    *,
    projects_dir: Path | None = None,
    paused: bool = False,
) -> None:
    marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    stage = str(stop.get("stage") or "delivery_signoff")
    write_board_stop_overlay(project_id, stage, projects_dir=projects_dir)
    marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    if not stop:
        return
    stop["producing_wait"] = True
    stop["needs_user_decision"] = False
    stop["decision_title_zh"] = "已暂停" if paused else "制作中"
    stop["decision_prompt_zh"] = friendly_zh
    stop["decision_options"] = []
    marker["board_stop"] = stop
    _write_json(_project_dir(project_id, projects_dir) / "project.json", marker)


def _fail_job(
    project_id: str,
    *,
    projects_dir: Path | None,
    engine: str,
    tier: str,
    code: str,
    friendly_zh: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": STATUS_FAILED,
        "engine": engine,
        "tier": tier,
        "code": code,
        "friendly_zh": friendly_zh,
    }
    if extra:
        payload.update(extra)
    job = write_job(project_id, payload, projects_dir=projects_dir)
    _refresh_overlay(project_id, friendly_zh, projects_dir=projects_dir, paused=True)
    return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}


def _wait_copy(project_id: str, marker: dict[str, Any], *, projects_dir: Path | None) -> str:
    from lib.board_advance import producing_wait_copy_zh

    return producing_wait_copy_zh(marker, project_id=project_id, projects_dir=projects_dir)


def _start_compose(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    engine: str = "compose",
    wait_copy: str = "",
) -> dict[str, Any]:
    tier = _tier(_profile(marker))
    try:
        bundle = build_compose_bundle(project_id, projects_dir=projects_dir)
    except ProduceJobError as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine=engine,
            tier=tier,
            code=exc.code,
            friendly_zh=exc.safe_message,
        )
    art = _project_dir(project_id, projects_dir) / "artifacts"
    _write_json(art / "edit_decisions.json", bundle["edit_decisions"])
    _write_json(art / "asset_manifest.json", bundle["asset_manifest"])
    starter = compose_start
    if starter is None:
        from openmontage.mcp.media.tools import compose_start as starter
    os.environ.setdefault("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    try:
        started = starter(
            json.dumps(bundle["edit_decisions"], ensure_ascii=False),
            json.dumps(bundle["asset_manifest"], ensure_ascii=False),
            _sandbox_rel(project_id, OUTPUT_REL),
        )
    except Exception as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine=engine,
            tier=tier,
            code="compose_start_failed",
            friendly_zh=f"本机无法启动合成：{exc}",
            extra={"error": str(exc)},
        )
    if not isinstance(started, dict):
        started = {}
    friendly = wait_copy or COMPOSE_WAIT_ZH
    job = write_job(
        project_id,
        {
            "status": STATUS_QUEUED,
            "engine": engine,
            "tier": tier,
            "job_id": str(started.get("job_id") or ""),
            "output_path": str(started.get("output_path") or OUTPUT_REL),
            "friendly_zh": friendly,
        },
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, job["friendly_zh"], projects_dir=projects_dir)
    return {"action": "produce_start", "status": STATUS_QUEUED, "job": job, "started": started}


def _wait_compose_done(
    project_id: str,
    started: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    if _has_final(project_id, projects_dir=projects_dir):
        return
    compose_id = str(started.get("job_id") or "")
    if not compose_id:
        if _has_final(project_id, projects_dir=projects_dir):
            return
        raise ProduceJobError("合成已启动但没有任务号，也没有成片。", code="compose_no_job")
    reader = job_status
    if reader is None:
        from openmontage.mcp.media.tools import job_status as reader
    for _ in range(3600):
        if _has_final(project_id, projects_dir=projects_dir):
            return
        remote = reader(compose_id)
        if not isinstance(remote, dict):
            remote = {}
        remote_status = str(remote.get("status") or "")
        if remote_status in {"failed", "error"}:
            raise ProduceJobError(
                str(remote.get("error") or "合成失败，请留在本页重试。"),
                code="compose_failed",
            )
        if remote_status in {"completed", "done", "succeeded"}:
            if _has_final(project_id, projects_dir=projects_dir):
                return
            raise ProduceJobError(
                "合成报告完成，但还没有成片文件。请留在本页重试。",
                code="final_missing",
            )
        time.sleep(1)
    raise ProduceJobError("合成等待超时。请留在本页重试。", code="compose_timeout")


def _run_paid_pipeline(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    profile = _profile(marker)
    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    beats = _plan_beats(project_id, projects_dir=projects_dir)
    width, height = _frame_size(profile)
    aspect = _aspect_ratio(width, height)
    wait_copy = _wait_copy(project_id, marker, projects_dir=projects_dir)
    generate = video_generate
    if generate is None:
        from openmontage.mcp.providers_video.tools import video_generate as generate
    project = _project_dir(project_id, projects_dir)
    total = len(beats)
    for index, row in enumerate(beats, start=1):
        dest_rel = _seg_rel(str(row["beat"]))
        dest = project / dest_rel
        if dest.is_file() and dest.stat().st_size > 0:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        still_abs = str((project / str(row["still"])).resolve())
        extras = _video_extras(provider, still_abs, float(row["span"]), aspect)
        friendly = f"第 {index}/{total} 段正在生成。{wait_copy}"
        write_job(
            project_id,
            {
                "status": STATUS_RUNNING,
                "engine": "paid_video",
                "tier": "heavy",
                "provider": provider,
                "beat": row["beat"],
                "friendly_zh": friendly,
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(project_id, friendly, projects_dir=projects_dir)
        result = generate(
            provider,
            str(row["prompt"]),
            _sandbox_rel(project_id, dest_rel),
            json.dumps(extras, ensure_ascii=False),
            True,
            True,
        )
        if isinstance(result, dict) and result.get("success") is False:
            raise ProduceJobError(
                str(result.get("error") or f"分段 {row['beat']} 生成失败，未换渠道。"),
                code="video_generate_failed",
            )
        if not dest.is_file() or dest.stat().st_size <= 0:
            raise ProduceJobError(
                f"分段 {row['beat']} 生成结束但没有视频文件，未换渠道。",
                code="segment_missing",
            )
    launched = _start_compose(
        project_id,
        marker,
        projects_dir=projects_dir,
        compose_start=compose_start,
        engine="paid_video",
        wait_copy=wait_copy,
    )
    if launched.get("status") == STATUS_FAILED:
        raise ProduceJobError(
            str((launched.get("job") or {}).get("friendly_zh") or "合成失败。"),
            code=str((launched.get("job") or {}).get("code") or "compose_start_failed"),
        )
    started = launched.get("started") if isinstance(launched.get("started"), dict) else {}
    _wait_compose_done(
        project_id,
        started,
        projects_dir=projects_dir,
        job_status=job_status,
    )


def maybe_start(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    paid_inline: bool = False,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if _has_final(project_id, projects_dir=projects_dir):
        return {"action": "", "status": STATUS_DONE, "skipped": True}
    if not is_minimal(marker) or not assets_gate_completed(
        project_id, projects_dir=projects_dir
    ):
        return {"action": "", "status": STATUS_SKIPPED, "skipped": True}
    existing = read_job(project_id, projects_dir=projects_dir) or {}
    status = str(existing.get("status") or "")
    if status in {STATUS_QUEUED, STATUS_RUNNING, STATUS_FAILED}:
        return {"action": "", "status": status, "job": existing, "skipped": True}

    gated = key_gate(project_id, marker, projects_dir=projects_dir)
    if status == STATUS_PAUSED and gated is not None:
        return {"action": "", "status": STATUS_PAUSED, "job": existing, "skipped": True}
    if gated is not None:
        job = write_job(project_id, gated, projects_dir=projects_dir)
        _refresh_overlay(
            project_id,
            str(gated.get("friendly_zh") or ""),
            projects_dir=projects_dir,
            paused=True,
        )
        return {"action": "produce_paused", "status": STATUS_PAUSED, "job": job}

    profile = _profile(marker)
    tier = _tier(profile)
    wait_copy = _wait_copy(project_id, marker, projects_dir=projects_dir)
    if tier != "heavy":
        return _start_compose(
            project_id,
            marker,
            projects_dir=projects_dir,
            compose_start=compose_start,
            engine="compose",
            wait_copy=COMPOSE_WAIT_ZH,
        )

    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)

    def worker(_job_id: str = "") -> None:
        try:
            _run_paid_pipeline(
                project_id,
                marker,
                projects_dir=projects_dir,
                compose_start=compose_start,
                video_generate=video_generate,
                job_status=job_status,
            )
            if _has_final(project_id, projects_dir=projects_dir):
                write_job(
                    project_id,
                    {
                        "status": STATUS_DONE,
                        "engine": "paid_video",
                        "tier": "heavy",
                        "provider": provider,
                        "friendly_zh": "成片已就绪，请在本页预览并导出。",
                    },
                    projects_dir=projects_dir,
                )
        except ProduceJobError as exc:
            _fail_job(
                project_id,
                projects_dir=projects_dir,
                engine="paid_video",
                tier="heavy",
                code=exc.code,
                friendly_zh=exc.safe_message,
            )
            raise
        except Exception as exc:
            _fail_job(
                project_id,
                projects_dir=projects_dir,
                engine="paid_video",
                tier="heavy",
                code="paid_pipeline_failed",
                friendly_zh=f"分段生成失败，未换渠道：{exc}",
                extra={"error": str(exc)},
            )
            raise

    if paid_inline:
        try:
            worker()
        except Exception:
            job = read_job(project_id, projects_dir=projects_dir) or {}
            return {
                "action": "produce_failed",
                "status": str(job.get("status") or STATUS_FAILED),
                "job": job,
            }
        job = read_job(project_id, projects_dir=projects_dir) or {}
        return {
            "action": "produce_start",
            "status": str(job.get("status") or STATUS_QUEUED),
            "job": job,
        }

    from openmontage.mcp.common.jobs import create_job, start_background

    media_job = create_job("board_paid_video", meta={"project_id": project_id})
    job = write_job(
        project_id,
        {
            "status": STATUS_QUEUED,
            "engine": "paid_video",
            "tier": "heavy",
            "provider": provider,
            "job_id": str(media_job.get("job_id") or ""),
            "friendly_zh": wait_copy,
        },
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, wait_copy, projects_dir=projects_dir)
    start_background(str(media_job["job_id"]), worker)
    return {"action": "produce_start", "status": STATUS_QUEUED, "job": job}


def poll(
    project_id: str,
    *,
    projects_dir: Path | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    job = read_job(project_id, projects_dir=projects_dir)
    if not job:
        return {"action": "", "status": ""}
    if _has_final(project_id, projects_dir=projects_dir):
        if job.get("status") != STATUS_DONE:
            job = write_job(
                project_id,
                {**job, "status": STATUS_DONE, "friendly_zh": "成片已就绪，请在本页预览并导出。"},
                projects_dir=projects_dir,
            )
        return {"action": "produce_done", "status": STATUS_DONE, "job": job}
    if job.get("status") in {STATUS_PAUSED, STATUS_FAILED, STATUS_DONE}:
        return {"action": "", "status": str(job.get("status") or ""), "job": job}
    compose_id = str(job.get("job_id") or "")
    if not compose_id:
        return {"action": "", "status": str(job.get("status") or ""), "job": job}
    reader = job_status
    if reader is None:
        from openmontage.mcp.media.tools import job_status as reader
    try:
        remote = reader(compose_id)
    except Exception as exc:
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "compose_status_failed",
                "friendly_zh": f"无法读取合成进度：{exc}",
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(
            project_id,
            job["friendly_zh"],
            projects_dir=projects_dir,
            paused=True,
        )
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    if not isinstance(remote, dict):
        remote = {}
    remote_status = str(remote.get("status") or "")
    if remote_status in {"failed", "error"}:
        friendly = str(remote.get("error") or "合成失败，请留在本页重试。")
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "compose_failed",
                "friendly_zh": friendly,
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(project_id, friendly, projects_dir=projects_dir, paused=True)
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    if remote_status in {"completed", "done", "succeeded"}:
        if _has_final(project_id, projects_dir=projects_dir):
            job = write_job(
                project_id,
                {**job, "status": STATUS_DONE, "friendly_zh": "成片已就绪，请在本页预览并导出。"},
                projects_dir=projects_dir,
            )
            return {"action": "produce_done", "status": STATUS_DONE, "job": job}
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "final_missing",
                "friendly_zh": "合成报告完成，但还没有成片文件。请留在本页重试。",
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(
            project_id, job["friendly_zh"], projects_dir=projects_dir, paused=True
        )
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    progress = remote.get("progress")
    engine = str(job.get("engine") or "compose")
    if engine == "paid_video":
        marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
        friendly = str(job.get("friendly_zh") or "") or _wait_copy(
            project_id, marker, projects_dir=projects_dir
        )
    else:
        friendly = "本机正在合成成片，大约 1–3 分钟。请留在本页。"
        if progress not in (None, ""):
            try:
                friendly = (
                    f"本机正在合成成片（{int(float(progress) * 100)}%），"
                    "大约还需要一两分钟。请留在本页。"
                )
            except (TypeError, ValueError):
                pass
    job = write_job(
        project_id,
        {**job, "status": STATUS_RUNNING, "friendly_zh": friendly},
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, friendly, projects_dir=projects_dir)
    return {"action": "produce_poll", "status": STATUS_RUNNING, "job": job}


def sync_produce(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    paid_inline: bool = False,
) -> dict[str, Any]:
    started = maybe_start(
        project_id,
        marker,
        projects_dir=projects_dir,
        compose_start=compose_start,
        video_generate=video_generate,
        paid_inline=paid_inline,
        job_status=job_status,
    )
    if started.get("action"):
        return started
    return poll(project_id, projects_dir=projects_dir, job_status=job_status)
