"""Plan-page beat coverage and four-way gap choices. Does not call generate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.asset_precheck import duration_profile, scan_user_images
from lib.paths import REPO_ROOT, get_workspace
from openmontage.mcp.bootstrap import install_state as install_state_mod

GAP_ACTIONS = ("upload", "i2i", "reuse", "skip")
IMAGE_MODEL_DECISION_KEY = "image_model::project"
ACTION_LABEL_ZH = {
    "upload": "补传",
    "i2i": "图生图",
    "reuse": "复用",
    "skip": "不补",
}
CLASS_NEED_ZH = {
    "product_hero": "商品整体正面",
    "product_angle": "侧面结构",
    "product_detail": "扣合细节",
    "on_body": "佩戴或使用",
    "lifestyle": "场景氛围",
    "packaging": "包装",
}
COMMERCIAL_IMAGE_MODELS: tuple[dict[str, Any], ...] = (
    {
        "id": "dashscope",
        "label_zh": "通义万相",
        "key_names": ("DASHSCOPE_API_KEY",),
    },
    {
        "id": "agnes",
        "label_zh": "Agnes 生图",
        "key_names": ("AGNES_API_KEY", "AGNES_AI_API_KEY"),
    },
    {
        "id": "flux",
        "label_zh": "FLUX",
        "key_names": ("FAL_KEY", "FAL_AI_API_KEY"),
    },
    {
        "id": "openai",
        "label_zh": "OpenAI 生图",
        "key_names": ("OPENAI_API_KEY",),
    },
    {
        "id": "kling",
        "label_zh": "可灵生图",
        "key_names": ("KLING_API_KEY",),
    },
    {
        "id": "google",
        "label_zh": "Imagen",
        "key_names": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    },
    {
        "id": "grok",
        "label_zh": "Grok 生图",
        "key_names": ("XAI_API_KEY",),
    },
)
_DEFAULT_DURATION = 20


class GapPlanError(Exception):
    def __init__(self, message: str, *, code: str = "gap_plan") -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


def projects_root(projects_dir: Path | None = None) -> Path:
    if projects_dir is not None:
        return Path(projects_dir)
    return get_workspace().projects_dir


def list_commercial_image_models(
    key_names_present: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    present = {str(name) for name in (key_names_present or [])}
    rows: list[dict[str, Any]] = []
    for spec in COMMERCIAL_IMAGE_MODELS:
        rows.append(
            {
                "id": spec["id"],
                "label_zh": spec["label_zh"],
                "available": any(name in present for name in spec["key_names"]),
            }
        )
    return rows


def default_commercial_image_model(
    models: list[dict[str, Any]] | None = None,
    *,
    key_names_present: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    """First usable image model. Prefer Agnes (native I2I). Never labeled 推荐."""
    rows = models if models is not None else list_commercial_image_models(key_names_present)
    available = [item for item in rows if item.get("available")]
    if not available:
        return None
    for item in available:
        if item.get("id") == "agnes":
            return item
    return available[0]


def scan_image_key_names(
    *,
    repo_root: Path | None = None,
    environ: dict[str, str] | None = None,
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for spec in COMMERCIAL_IMAGE_MODELS:
        for name in spec["key_names"]:
            if name not in seen:
                seen.add(name)
                names.append(name)
    _from_file, _from_proc, present, _meta = install_state_mod._scan_named_keys(
        repo_root=Path(repo_root or REPO_ROOT),
        names=names,
        environ=environ,
    )
    return list(present)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _duration_seconds(marker: dict[str, Any], project_dir: Path) -> int:
    profile = marker.get("production_profile")
    profile = profile if isinstance(profile, dict) else {}
    brief = _read_json(project_dir / "artifacts" / "brief.json")
    for raw in (
        profile.get("duration_seconds"),
        marker.get("duration_seconds"),
        brief.get("duration_seconds"),
        brief.get("target_duration_seconds"),
    ):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return _DEFAULT_DURATION


def _beats_from_plan(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows = plan.get("segments") if isinstance(plan.get("segments"), list) else None
    if rows is None:
        rows = plan.get("beats") if isinstance(plan.get("beats"), list) else []
    beats: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        beat_id = str(row.get("id") or row.get("beat") or "").strip()
        if not beat_id:
            beat_id = f"B{index + 1:02d}"
        need = str(
            row.get("purpose")
            or row.get("need_zh")
            or row.get("asset_plan_zh")
            or ""
        ).strip()
        beats.append(
            {
                "beat_id": beat_id,
                "need_zh": need or f"第{index + 1}段画面",
                "ref_image": str(row.get("ref_image") or row.get("ref") or "").strip(),
            }
        )
    return beats


def _default_beats(duration_seconds: int) -> list[dict[str, str]]:
    classes = list(duration_profile(duration_seconds)["preferred_asset_classes"])
    beats: list[dict[str, str]] = []
    for index, class_id in enumerate(classes):
        beats.append(
            {
                "beat_id": f"B{index + 1:02d}",
                "need_zh": CLASS_NEED_ZH.get(class_id, class_id),
                "ref_image": "",
                "asset_class": class_id,
            }
        )
    return beats


def _usable_images(scan: dict[str, Any]) -> list[dict[str, Any]]:
    usable: list[dict[str, Any]] = []
    for entry in scan.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        if not path or entry.get("duplicate_of"):
            continue
        usable.append(entry)
    return usable


def build_gap_snapshot(
    project_id: str,
    *,
    projects_dir: Path | None = None,
    repo_root: Path | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = projects_root(projects_dir)
    project_dir = root / project_id
    marker = _read_json(project_dir / "project.json")
    duration = _duration_seconds(marker, project_dir)
    scan = scan_user_images(project_dir)
    plan = _read_json(project_dir / "artifacts" / "video_plan.json")
    beats = _beats_from_plan(plan) if plan else _default_beats(duration)
    if not beats:
        beats = _default_beats(duration)
    images = _usable_images(scan)
    remaining = list(images)
    covered: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    for beat in beats:
        beat_id = beat["beat_id"]
        need_zh = beat["need_zh"]
        existing = str(beat.get("ref_image") or "").strip()
        if existing and existing not in used_paths:
            used_paths.add(existing)
            remaining = [item for item in remaining if item.get("path") != existing]
            covered.append(
                {
                    "beat_id": beat_id,
                    "need_zh": need_zh,
                    "path": existing,
                    "status": "used",
                }
            )
            continue
        if remaining:
            picked = remaining.pop(0)
            path = str(picked.get("path") or "")
            used_paths.add(path)
            covered.append(
                {
                    "beat_id": beat_id,
                    "need_zh": need_zh,
                    "path": path,
                    "status": "used",
                }
            )
            continue
        gaps.append(
            {
                "beat_id": beat_id,
                "need_zh": need_zh,
                "choice": None,
                "i2i_model": None,
                "reuse_path": None,
            }
        )
    key_names = scan_image_key_names(repo_root=repo_root, environ=environ)
    models = list_commercial_image_models(key_names)
    image_key_present = any(item.get("available") for item in models)
    default_model = default_commercial_image_model(models)
    reuse_paths = [str(item["path"]) for item in covered if item.get("path")]
    return {
        "version": "1.0",
        "project_id": project_id,
        "enough": not gaps,
        "duration_seconds": duration,
        "image_key_present": image_key_present,
        "image_key_names_present": key_names,
        "image_models": models,
        "default_image_model": None if default_model is None else default_model["id"],
        "image_model": None,
        "reuse_paths": reuse_paths,
        "covered": covered,
        "gaps": gaps,
        "locked": False,
    }


def _selection_map(payload: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    selections = payload.get("selections")
    if not isinstance(selections, list):
        return values
    for item in selections:
        if not isinstance(item, dict):
            continue
        key = str(item.get("decision_key") or "").strip()
        option_id = str(item.get("option_id") or item.get("id") or "").strip()
        if key and option_id:
            values[key] = option_id
    return values


def stop_action_from_intent(intent: dict[str, Any]) -> str:
    payload = intent.get("payload") if isinstance(intent.get("payload"), dict) else {}
    values = _selection_map(payload)
    for key, option_id in values.items():
        if key.endswith("::current"):
            return option_id
    return "continue"


def _shared_image_model_id(
    values: dict[str, str],
    models: dict[str, dict[str, Any]],
) -> str:
    model_id = values.get(IMAGE_MODEL_DECISION_KEY, "")
    if not model_id:
        for key, option_id in values.items():
            if key.startswith("gap_model::") and option_id:
                model_id = option_id
                break
    spec = models.get(model_id)
    if not spec or not spec.get("available"):
        raise GapPlanError(
            "选了图生图，请再选一个已填入 Key 的生图模型。全片共用一个，有多个 Key 时请点选。",
            code="i2i_model_required",
        )
    return model_id


def _choices_from_intent(
    snapshot: dict[str, Any],
    intent: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = intent.get("payload") if isinstance(intent.get("payload"), dict) else {}
    values = _selection_map(payload)
    models = {
        str(item.get("id")): item
        for item in snapshot.get("image_models") or []
        if isinstance(item, dict)
    }
    reuse_ok = {str(path) for path in snapshot.get("reuse_paths") or []}
    needs_i2i = False
    filled: list[dict[str, Any]] = []
    for gap in snapshot.get("gaps") or []:
        beat_id = str(gap.get("beat_id") or "")
        choice = values.get(f"gap::{beat_id}", "")
        if choice not in GAP_ACTIONS:
            raise GapPlanError(
                f"「{gap.get('need_zh') or beat_id}」还没选缺口做法（补传 / 图生图 / 复用 / 不补）。",
                code="gap_choice_required",
            )
        row = {
            "beat_id": beat_id,
            "need_zh": gap.get("need_zh"),
            "choice": choice,
            "i2i_model": None,
            "reuse_path": None,
        }
        if choice == "i2i":
            if not snapshot.get("image_key_present"):
                raise GapPlanError(
                    "图生图需要生图 Key。请写入仓根 .env 后点「已填入 Key，刷新可用性」，或改选其它做法。",
                    code="i2i_unavailable",
                )
            needs_i2i = True
        if choice == "reuse":
            reuse_path = values.get(f"gap_reuse::{beat_id}", "")
            if reuse_path not in reuse_ok:
                raise GapPlanError(
                    f"「{gap.get('need_zh') or beat_id}」选了复用，请指定一张已有图片。",
                    code="reuse_path_required",
                )
            row["reuse_path"] = reuse_path
        filled.append(row)
    shared_model = _shared_image_model_id(values, models) if needs_i2i else None
    if shared_model:
        for row in filled:
            if row["choice"] == "i2i":
                row["i2i_model"] = shared_model
    return filled


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _beat_time_span(index: int, total: int, duration: int) -> str:
    if total <= 0:
        return f"0-{duration}s"
    start = int(round(duration * index / total))
    end = int(round(duration * (index + 1) / total))
    if end <= start:
        end = start + 1
    return f"{start}-{end}s"


def _plan_artifacts(
    project_id: str,
    project_dir: Path,
    snapshot: dict[str, Any],
    filled_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    duration = int(snapshot.get("duration_seconds") or _DEFAULT_DURATION)
    marker = _read_json(project_dir / "project.json")
    theme = str(marker.get("title") or project_id)
    scan = scan_user_images(project_dir)
    choice_by_beat = {item["beat_id"]: item for item in filled_gaps}
    rows: list[dict[str, Any]] = []
    for item in snapshot.get("covered") or []:
        rows.append(
            {
                "kind": "covered",
                "beat_id": item["beat_id"],
                "need_zh": item["need_zh"],
                "path": item.get("path"),
                "choice": "used",
            }
        )
    for item in filled_gaps:
        rows.append(
            {
                "kind": "gap",
                **item,
            }
        )
    ordered = list(snapshot.get("covered") or []) + list(snapshot.get("gaps") or [])
    total = max(len(ordered), 1)
    video_segments: list[dict[str, Any]] = []
    card_segments: list[dict[str, Any]] = []
    for index, beat in enumerate(ordered):
        beat_id = str(beat["beat_id"])
        need_zh = str(beat.get("need_zh") or beat_id)
        span = _beat_time_span(index, total, duration)
        covered = next(
            (
                item
                for item in snapshot.get("covered") or []
                if item.get("beat_id") == beat_id
            ),
            None,
        )
        gap = choice_by_beat.get(beat_id)
        segment: dict[str, Any] = {
            "id": beat_id,
            "beat": beat_id,
            "purpose": need_zh,
            "duration": max(1, int(round(duration / total))),
        }
        asset_plan = need_zh
        if covered:
            path = str(covered.get("path") or "")
            segment["gap_fill"] = "user_upload"
            segment["assignment_status"] = "assigned"
            segment["asset_source"] = "user_upload"
            if path:
                segment["ref_image"] = path
            asset_plan = f"使用用户图 {path}" if path else "使用用户已有图"
        elif gap:
            choice = gap["choice"]
            if choice == "upload":
                segment["gap_fill"] = "user_upload"
                segment["assignment_status"] = "missing"
                asset_plan = "用户将补传该段画面"
            elif choice == "i2i":
                segment["gap_fill"] = "i2i"
                segment["assignment_status"] = "i2i_planned"
                segment["asset_source"] = "i2i"
                segment["provider"] = gap.get("i2i_model")
                segment["model"] = gap.get("i2i_model")
                segment["planned_output_path"] = f"assets/images/i2i_{beat_id}.png"
                asset_plan = f"图生图（{gap.get('i2i_model')}），本步只锁定计划、不生成"
            elif choice == "reuse":
                segment["gap_fill"] = "none"
                segment["assignment_status"] = "reuse_pending"
                segment["asset_source"] = "user_upload"
                path = str(gap.get("reuse_path") or "")
                if path:
                    segment["ref_image"] = path
                asset_plan = f"拟复用 {path}，待素材检查确认"
            else:
                segment["gap_fill"] = "concept_only"
                segment["assignment_status"] = "assigned"
                asset_plan = "本段明确不补图，改为概念表达"
        video_segments.append(segment)
        card_segments.append(
            {
                "beat": beat_id,
                "time": span,
                "copy_plan_zh": f"{need_zh}。",
                "shot_plan_zh": f"展示{need_zh}。",
                "asset_plan_zh": asset_plan,
            }
        )
    images: dict[str, Any] = {}
    for entry in scan.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        if not path:
            continue
        role = str(entry.get("suggested_class") or "product_hero")
        images[Path(path).stem or f"img{len(images)+1}"] = {
            "path": path,
            "role": role or "product_hero",
            "bytes": int(entry.get("bytes") or 0),
        }
    brief = {
        "theme": theme,
        "duration_seconds": duration,
        "images": images,
    }
    video_plan = {"version": "1.0", "segments": video_segments}
    segment_cards = {
        "version": "1.0",
        "duration_seconds": duration,
        "overall_prompt_zh": (
            f"{theme}，时长 {duration} 秒。"
            "按方案页已锁定的画面覆盖与缺口做法制作，本步不生成图片或视频。"
        ),
        "segments": card_segments,
    }
    shared_model = next(
        (item.get("i2i_model") for item in filled_gaps if item.get("choice") == "i2i"),
        None,
    )
    locked = {
        **snapshot,
        "locked": True,
        "locked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "image_model": shared_model,
        "gaps": filled_gaps,
        "rows": rows,
    }
    return {
        "gap_plan": locked,
        "brief": brief,
        "asset_precheck": scan,
        "video_plan": video_plan,
        "segment_cards": segment_cards,
    }


def lock_gap_plan_from_intent(
    project_id: str,
    intent: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    repo_root: Path | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Persist four-way choices. Never calls image/video generate."""
    snapshot = build_gap_snapshot(
        project_id,
        projects_dir=projects_dir,
        repo_root=repo_root,
        environ=environ,
    )
    action = stop_action_from_intent(intent)
    if action == "revise":
        return {"action": "revise", "snapshot": snapshot, "artifacts": {}}
    filled = [] if snapshot.get("enough") else _choices_from_intent(snapshot, intent)
    project_dir = projects_root(projects_dir) / project_id
    artifacts = _plan_artifacts(project_id, project_dir, snapshot, filled)
    art_dir = project_dir / "artifacts"
    _write_json(art_dir / "gap_plan.json", artifacts["gap_plan"])
    _write_json(art_dir / "brief.json", artifacts["brief"])
    _write_json(art_dir / "asset_precheck.json", artifacts["asset_precheck"])
    _write_json(art_dir / "video_plan.json", artifacts["video_plan"])
    _write_json(art_dir / "segment_cards.json", artifacts["segment_cards"])
    _write_image_model_profile(
        project_dir,
        artifacts["gap_plan"].get("image_model"),
    )
    return {"action": "continue", "snapshot": artifacts["gap_plan"], "artifacts": artifacts}


def _write_image_model_profile(project_dir: Path, model_id: str | None) -> None:
    if not model_id:
        return
    marker_path = project_dir / "project.json"
    marker = _read_json(marker_path)
    profile = marker.get("production_profile")
    if not isinstance(profile, dict):
        profile = {}
    profile["image_model"] = str(model_id)
    marker["production_profile"] = profile
    _write_json(marker_path, marker)
