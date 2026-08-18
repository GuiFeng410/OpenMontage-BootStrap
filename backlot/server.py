"""Backlot server — FastAPI app: board state API, SSE change feed, media.

The watcher observes ``projects/`` with watchfiles; on any change it bumps a
per-project version and wakes SSE subscribers, who tell the browser to
refetch state. Paid generate is never called here. Local writes are limited
to library create, Key refresh snapshots, start-production marker fields,
and intents/.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backlot.state import PROJECTS_DIR, REPO_ROOT, list_projects, load_board_state, summarize_project
from lib.edit_intents import (
    IntentConflictError,
    IntentError,
    UnknownProjectError,
    create_intent,
)
from lib import interaction_intents as interaction_intents

UI_DIR = Path(__file__).resolve().parent / "ui"
THUMB_CACHE_DIR = REPO_ROOT / ".backlot" / "thumbs"
THUMB_WIDTHS = (320, 640, 960)

# Paths inside a project whose changes are pure noise for the board.
_IGNORE_PARTS = {"node_modules", ".git", "__pycache__", ".cache"}

SSE_HEARTBEAT_SECONDS = 15


def _ui_html(name: str, assets: tuple[str, ...]) -> HTMLResponse:
    html = (UI_DIR / name).read_text(encoding="utf-8")
    for asset in assets:
        path = UI_DIR / asset
        if path.is_file():
            version = str(int(path.stat().st_mtime))
            html = html.replace(f"/ui/{asset}", f"/ui/{asset}?v={version}")
    return HTMLResponse(html)


class ChangeHub:
    """Fan-out of project-change notifications to SSE subscribers.

    Subscriptions are filtered: a board subscribed to one project only ever
    receives that project's ids, so unrelated-project bursts can't flood its
    queue and starve out the one notification it actually needs.
    """

    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue, Optional[str]] = {}

    def subscribe(self, project_id: Optional[str] = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers[q] = project_id
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.pop(q, None)

    def publish(self, project_id: str) -> None:
        for q, only in list(self._subscribers.items()):
            if only is not None and only != project_id:
                continue
            try:
                q.put_nowait(project_id)
            except asyncio.QueueFull:
                # Queue holds only THIS subscriber's relevant ids, so a full
                # queue already guarantees a pending wake-up → safe to drop.
                pass


hub = ChangeHub()


def _runner_alive() -> bool:
    try:
        from backlot.runner import runner_alive

        return bool(runner_alive())
    except Exception:
        return False

# Library summaries are expensive to derive (full state parse per project);
# cache per project and invalidate from the watcher.
_summary_cache: dict[str, dict] = {}


def _invalidate_summary(project_id: str) -> None:
    _summary_cache.pop(project_id, None)


def _cached_summaries() -> list[dict]:
    if not PROJECTS_DIR.is_dir():
        return []
    summaries = []
    for entry in sorted(PROJECTS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        cached = _summary_cache.get(entry.name)
        if cached is None:
            try:
                cached = summarize_project(entry)
            except Exception:
                cached = {
                    "project_id": entry.name, "title": entry.name,
                    "pipeline_type": "unknown", "has_pipeline_state": False,
                    "poster": None, "live": False, "last_activity": 0,
                    "active_stage": None, "awaiting_human": False,
                    "stage_states": [], "completed_count": 0,
                    "render_count": 0, "scene_count": 0, "error": "unreadable",
                }
            _summary_cache[entry.name] = cached
        summaries.append(cached)
    summaries.sort(key=lambda s: (not s["live"], -(s["last_activity"] or 0)))
    return summaries


def _read_interaction_intents(project_dir: Path) -> list[dict]:
    return interaction_intents.list_safe_interaction_intents(project_dir)


# Watch-loop hot path: pure string comparison, no per-path filesystem calls
# (change batches can be thousands of paths during a render).
import os as _os

_PROJECTS_ROOT_STR = _os.path.normcase(str(PROJECTS_DIR.resolve()))


def _project_of_change(path_str: str) -> Optional[str]:
    """Map a changed filesystem path to a project id (None = irrelevant)."""
    norm = _os.path.normcase(_os.path.normpath(path_str))
    if not norm.startswith(_PROJECTS_ROOT_STR):
        return None
    rel = norm[len(_PROJECTS_ROOT_STR):].lstrip("\\/")
    if not rel:
        return None
    parts = rel.replace("\\", "/").split("/")
    if _IGNORE_PARTS.intersection(parts):
        return None
    return parts[0]


async def _watch_projects() -> None:
    """Background task: watch projects/ and publish debounced changes."""
    try:
        from watchfiles import awatch
    except ImportError:
        return  # watcher unavailable → board still works via manual refresh
    if not PROJECTS_DIR.is_dir():
        return
    async for changes in awatch(PROJECTS_DIR, recursive=True, step=400):
        touched: set[str] = set()
        for _change, path_str in changes:
            pid = _project_of_change(path_str)
            if pid:
                touched.add(pid)
        for pid in touched:
            _invalidate_summary(pid)
            hub.publish(pid)


def create_app() -> FastAPI:
    app = FastAPI(title="Backlot", docs_url=None, redoc_url=None)

    @app.on_event("startup")
    async def _startup() -> None:
        app.state.watch_task = asyncio.create_task(_watch_projects())

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        task = getattr(app.state, "watch_task", None)
        if task:
            task.cancel()

    # ---- API ----------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict:
        from lib.library_create import public_install_flags

        flags = public_install_flags()
        return {
            "ok": True,
            "app": "backlot",
            "projects_dir": str(PROJECTS_DIR),
            "runner_alive": _runner_alive(),
            **flags,
        }

    @app.post("/api/keys/refresh")
    async def keys_refresh() -> dict:
        from lib.library_create import refresh_key_availability

        return await asyncio.to_thread(refresh_key_availability)

    @app.post("/api/project/{project_id}/start-production")
    async def start_production_endpoint(project_id: str, request: Request) -> JSONResponse:
        from lib.library_create import LibraryCreateError, start_production

        _safe_project_dir(project_id)
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        try:
            result = await asyncio.to_thread(
                start_production,
                project_id=project_id,
                production_tier=str(payload.get("production_tier") or ""),
            )
        except LibraryCreateError as exc:
            raise HTTPException(
                status_code=exc.http_status,
                detail={"code": exc.code, "friendly_zh": exc.friendly_zh},
            ) from exc
        _invalidate_summary(project_id)
        hub.publish(project_id)
        return JSONResponse(content=result)

    # Library create is a local write: it calls produce_init_project after
    # install-state.verify_ready, and never calls paid generate APIs.
    @app.post("/api/library/create-project")
    async def create_library_project(request: Request) -> JSONResponse:
        from lib.library_create import LibraryCreateError, create_library_project as create_project

        content_type = (request.headers.get("content-type") or "").lower()
        asset_files: list[tuple[str, bytes]] = []
        if "multipart/form-data" in content_type:
            form = await request.form()
            payload = {
                "title": form.get("title") or "",
                "review_mode": form.get("review_mode") or "",
                "duration_seconds": form.get("duration_seconds"),
                "asset_location": form.get("asset_location") or form.get("product_url") or "",
            }
            uploads = form.getlist("files")
            for item in uploads:
                filename = getattr(item, "filename", "") or "asset"
                read = getattr(item, "read", None)
                data = await read() if read else b""
                if data:
                    asset_files.append((str(filename), data))
        else:
            try:
                payload = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="invalid JSON body")
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="body must be a JSON object")
        try:
            result = await asyncio.to_thread(
                create_project,
                title=str(payload.get("title") or ""),
                review_mode=str(payload.get("review_mode") or ""),
                duration_seconds=payload.get("duration_seconds"),
                asset_location=str(
                    payload.get("asset_location") or payload.get("product_url") or ""
                ),
                asset_files=asset_files,
            )
        except LibraryCreateError as exc:
            raise HTTPException(
                status_code=exc.http_status,
                detail={"code": exc.code, "friendly_zh": exc.friendly_zh},
            ) from exc
        _invalidate_summary(result["project_id"])
        hub.publish(result["project_id"])
        return JSONResponse(status_code=201, content=result)

    @app.get("/api/projects")
    async def projects() -> list:
        return await asyncio.to_thread(_cached_summaries)

    # Sole write exception to the board's read-only contract (L1-B):
    # accepts user editing marks and stores them under
    # projects/<id>/intents/ only. Never touches checkpoint / artifacts.
    @app.post("/intents")
    async def create_intent_endpoint(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        project_id = payload.get("project_id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise HTTPException(status_code=400, detail="missing project_id")
        project_dir = _safe_project_dir(project_id)

        if "intent_type" in payload:
            intent_type = payload.get("intent_type")
            if intent_type not in interaction_intents.INTERACTION_INTENT_TYPES:
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown intent_type: {intent_type!r}",
                )
            interaction_payload = {
                key: value
                for key, value in payload.items()
                if key != "risk_level"
            }
            try:
                interaction_intents.validate_interaction_intent(
                    interaction_payload
                )
                current = interaction_intents.expire_if_needed(
                    interaction_payload
                )
                record = await asyncio.to_thread(
                    interaction_intents.create_or_conflict,
                    project_id,
                    current,
                )
            except interaction_intents.UnknownProjectError:
                raise HTTPException(status_code=404, detail="unknown project")
            except interaction_intents.IntentConflictError:
                raise HTTPException(
                    status_code=409,
                    detail="intent_id already exists with different content",
                )
            except interaction_intents.IntentError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            hub.publish(project_id)
            intent = record["intent"]
            return JSONResponse(
                status_code=200 if record.get("duplicate") else 201,
                content={
                    "intent_id": intent["intent_id"],
                    "status": intent["status"],
                    "duplicate": bool(record.get("duplicate", False)),
                },
            )

        board_state = await asyncio.to_thread(load_board_state, project_dir)
        editing_gate = board_state.get("editing_gate")
        if not isinstance(editing_gate, dict) or editing_gate.get("enabled") is not True:
            gate = editing_gate if isinstance(editing_gate, dict) else {
                "reason_codes": ["editing_gate_unavailable"],
                "friendly_zh": "当前项目没有可消费的剪辑门禁状态。",
            }
            raise HTTPException(
                status_code=409,
                detail={
                    "kind": "editing_gate",
                    "reason_codes": gate.get("reason_codes") or ["editing_gate_locked"],
                    "friendly_zh": gate.get("friendly_zh") or "当前不可提交剪辑要求。",
                },
            )
        try:
            latest_render = editing_gate.get("latest_render") or {}
            record = await asyncio.to_thread(
                create_intent,
                project_id,
                payload,
                canonical_source_render=latest_render.get("path"),
            )
        except UnknownProjectError:
            raise HTTPException(status_code=404, detail="unknown project")
        except IntentConflictError:
            raise HTTPException(status_code=409, detail="intent_id already exists with different content")
        except IntentError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        hub.publish(project_id)
        return JSONResponse(
            status_code=200 if record.get("duplicate") else 201,
            content={
                "intent_id": record["intent_id"],
                "status": record["status"],
                "duplicate": bool(record.get("duplicate", False)),
            },
        )

    @app.get("/api/project/{project_id}/interaction-intents")
    async def interaction_intent_list(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        if not (project_dir / "project.json").is_file():
            raise HTTPException(status_code=404, detail="unknown project")
        intents = await asyncio.to_thread(
            _read_interaction_intents,
            project_dir,
        )
        return {"project_id": project_id, "intents": intents}

    @app.get("/api/project/{project_id}/state")
    async def project_state(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        return await asyncio.to_thread(load_board_state, project_dir)

    @app.get("/api/project/{project_id}/events")
    async def project_events(project_id: str, request: Request) -> StreamingResponse:
        _safe_project_dir(project_id)  # 404 early for unknown projects

        async def stream():
            q = hub.subscribe(project_id)
            try:
                yield _sse({"type": "hello", "project_id": project_id})
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        await asyncio.wait_for(q.get(), timeout=SSE_HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        yield _sse({"type": "heartbeat", "ts": time.time()})
                        continue
                    # Coalesce bursts: drain anything else queued.
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    yield _sse({"type": "change", "project_id": project_id})
            finally:
                hub.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.get("/api/library/events")
    async def library_events(request: Request) -> StreamingResponse:
        async def stream():
            q = hub.subscribe()
            try:
                yield _sse({"type": "hello"})
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        changed = await asyncio.wait_for(q.get(), timeout=SSE_HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        yield _sse({"type": "heartbeat", "ts": time.time()})
                        continue
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    yield _sse({"type": "change", "project_id": changed})
            finally:
                hub.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    # ---- Thumbnails (downscaled, cached on disk) ------------------------

    @app.get("/thumb/{project_id}/{file_path:path}")
    async def thumb(project_id: str, file_path: str, w: int = 640) -> FileResponse:
        project_dir = _safe_project_dir(project_id)
        target = (project_dir / file_path).resolve()
        try:
            target.relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="path escapes project")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="media not found")
        width = min(THUMB_WIDTHS, key=lambda x: abs(x - w))
        cached = await asyncio.to_thread(_thumbnail_for, target, width)
        if cached is None:
            # Never fall back to raw video bytes for an <img> consumer (F-03);
            # non-thumbable images are safe to serve as-is.
            if target.suffix.lower() in {".mp4", ".webm", ".mov"}:
                raise HTTPException(status_code=404, detail="no poster frame available")
            return FileResponse(target)
        return FileResponse(cached, media_type="image/jpeg")

    # ---- Media (range requests handled by FileResponse) ---------------

    @app.get("/media/{project_id}/{file_path:path}")
    async def media(project_id: str, file_path: str) -> FileResponse:
        project_dir = _safe_project_dir(project_id)
        target = (project_dir / file_path).resolve()
        try:
            target.relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="path escapes project")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="media not found")
        return FileResponse(target)

    # ---- UI ------------------------------------------------------------

    @app.get("/p/{project_id}")
    async def board_page(project_id: str) -> HTMLResponse:
        return _ui_html("board.html", ("board.css", "board.js"))

    @app.get("/p/{project_path:path}")
    async def board_page_path(project_path: str) -> HTMLResponse:
        return _ui_html("board.html", ("board.css", "board.js"))

    @app.get("/")
    async def library_page() -> HTMLResponse:
        return _ui_html("index.html", ("board.css", "library.css", "library.js"))

    if UI_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    # The board is a long-lived SPA: a tab keeps running whatever board.js it
    # loaded, and browsers heuristically cache /ui assets. no-cache forces a
    # conditional revalidation (cheap 304 via ETag) on every load so UI fixes
    # show up on a plain refresh. Media/thumb responses keep normal caching.
    @app.middleware("http")
    async def ui_no_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/ui") or path.startswith("/p/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


def _safe_project_dir(project_id: str) -> Path:
    # ':' rejects Windows drive-relative ids like "C:" (PROJECTS_DIR / "C:"
    # collapses back to PROJECTS_DIR itself).
    if any(c in project_id for c in "/\\:") or project_id in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid project id")
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
    return project_dir


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _thumbnail_for(source: Path, width: int) -> Optional[Path]:
    """Downscale an image (or extract a video poster frame) to a cached JPEG."""
    suffix = source.suffix.lower()
    is_image = suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    is_video = suffix in {".mp4", ".webm", ".mov"}
    if not (is_image or is_video):
        return None
    try:
        import hashlib
        stat = source.stat()
        key = hashlib.sha1(
            f"{source}|{stat.st_mtime_ns}|{stat.st_size}|{width}".encode()
        ).hexdigest()[:20]
        cached = THUMB_CACHE_DIR / f"{key}.jpg"
        if cached.is_file():
            return cached
        THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Unique temp per request — concurrent misses for the same source
        # must not write (and replace from) the same temp file.
        import uuid
        tmp = THUMB_CACHE_DIR / f"{key}.{uuid.uuid4().hex[:8]}.tmp.jpg"
        if is_video:
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.5",
                 "-i", str(source), "-frames:v", "1",
                 "-vf", f"scale={width}:-2", str(tmp)],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not tmp.is_file():
                return None
        else:
            from PIL import Image
            with Image.open(source) as img:
                img = img.convert("RGB")
                img.thumbnail((width, width * 3))
                img.save(tmp, "JPEG", quality=82)
        tmp.replace(cached)
        return cached
    except Exception:
        return None


app = create_app()
