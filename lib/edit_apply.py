"""Edit intent application — the Agent-side half of the edit loop.

The user marks edits on the board (POST /intents → ``intents/<id>.json``,
status ``pending``). The Agent then:

1. Reads the pending intent and presents a readable plan in chat.
2. On chat confirmation, applies it to ``artifacts/edit_decisions.json``:
   - drift check: intent's ``base.cuts_revision`` vs current cuts digest;
   - merge **cuts only** — every other field stays untouched (the
     "no partial-table overwrite" rule from the 08-10 phase-sealing fix);
   - actions whose cut no longer exists are skipped (friendly scene #4).
3. Marks the intent ``applied`` (or ``superseded`` on drift).

Digest algorithm mirrors the board's JS (djb2 → base36, values rounded to
1 decimal via ``:g``) so cross-language revision signals match.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.edit_intents import IntentError, UnknownProjectError, get_intent, update_status
from lib.paths import PROJECTS_DIR

EDIT_DECISIONS_RELPATH = "artifacts/edit_decisions.json"

# Statuses an intent may be in when apply is allowed.
_APPLIABLE = frozenset({"pending", "planned", "confirmed"})


# ---- digest (must mirror board-edit.js cutsSig) --------------------------

def _js_num(value: Any):
    """Serialize a number the way JS ``JSON.stringify`` does (ints w/o '.0')."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else f


def cuts_digest(cuts: list[dict[str, Any]]) -> str:
    """Digest of the cuts array, byte-identical to the board's ``cutsSig``."""
    rows = [
        [c["id"], c.get("source"), _js_num(c.get("in_seconds")), _js_num(c.get("out_seconds"))]
        for c in cuts
    ]
    return _digest(json.dumps(rows, separators=(",", ":")))


def _digest(text: str) -> str:
    h = 5381
    for ch in text:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return "h" + _to_base36(h)


def _to_base36(n: int) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = ""
    while n:
        out = chars[n % 36] + out
        n //= 36
    return out


# ---- file access ----------------------------------------------------------

def edit_decisions_path(project_id: str) -> Path:
    return PROJECTS_DIR / project_id / EDIT_DECISIONS_RELPATH


def load_edit_decisions(project_id: str) -> dict[str, Any]:
    path = edit_decisions_path(project_id)
    if not path.is_file():
        raise IntentError(f"edit_decisions not found: {project_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cuts"), list):
        raise IntentError(f"edit_decisions malformed: {project_id}")
    return data


def save_edit_decisions(project_id: str, data: dict[str, Any]) -> None:
    path = edit_decisions_path(project_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def current_cuts_digest(project_id: str) -> str:
    return cuts_digest(load_edit_decisions(project_id)["cuts"])


# ---- plan text (human-readable, for chat confirmation) --------------------

def plan_text(intent: dict[str, Any]) -> str:
    """One readable line per action, plus the user note if any."""
    base = intent.get("base") or {}
    lines = [f"基于 {base.get('source_render') or '(成片)'}（版本 {base.get('cuts_revision') or '?'}）的标记："]
    for a in intent.get("actions") or []:
        kind = a.get("type")
        if kind == "trim":
            lines.append(f"把片段 {a.get('cut_id')} 时长改为 {a.get('in_seconds')}–{a.get('out_seconds')} 秒")
        elif kind == "delete":
            lines.append(f"删除片段 {a.get('cut_id')}")
        elif kind == "reorder":
            order = a.get("order") or []
            lines.append("调整片段顺序：" + " → ".join(str(x) for x in order))
        else:
            lines.append(f"（未知动作：{kind}）")
    note = (
        intent.get("note")
        or next((a.get("note") for a in intent.get("actions") or [] if a.get("note")), "")
    )
    if note:
        lines.append(f"用户备注：{note}")
    return "\n".join(lines)


# ---- apply ----------------------------------------------------------------

def _apply_actions(cuts: list[dict[str, Any]], intent: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply intent actions to the cuts list in order. Missing cuts are skipped."""
    by_id = {c.get("id"): c for c in cuts}
    order = list(cuts)
    skipped: list[str] = []
    for a in intent.get("actions") or []:
        kind = a.get("type")
        if kind == "trim":
            cut = by_id.get(a.get("cut_id"))
            if cut is None:
                skipped.append(f"trim:{a.get('cut_id')}")
                continue
            cut["in_seconds"] = float(a.get("in_seconds"))
            cut["out_seconds"] = float(a.get("out_seconds"))
            cut["reason"] = f"user intent {intent.get('intent_id')}"
        elif kind == "delete":
            if a.get("cut_id") not in by_id:
                skipped.append(f"delete:{a.get('cut_id')}")
                continue
            del by_id[a["cut_id"]]
        elif kind == "reorder":
            wanted = a.get("order") or []
            known = [c for c in order if c.get("id") in by_id]
            by_wanted = {cid: i for i, cid in enumerate(wanted)}
            known.sort(key=lambda c: by_wanted.get(c.get("id"), len(wanted)))
            order = known
    return [c for c in order if c.get("id") in by_id]


def apply_intent(project_id: str, intent_id: str) -> dict[str, Any]:
    """Apply a pending/planned/confirmed intent to edit_decisions.

    Returns a summary dict. Raises ``IntentError`` on invalid state /
    missing intent / malformed edit_decisions.
    """
    intent = get_intent(project_id, intent_id)
    if intent is None:
        raise IntentError(f"intent not found: {intent_id}")
    if intent.get("status") not in _APPLIABLE:
        raise IntentError(f"intent not applicable (status={intent.get('status')}): {intent_id}")

    # Drift: the board's revision must match the cuts on disk right now.
    expected = (intent.get("base") or {}).get("cuts_revision")
    actual = current_cuts_digest(project_id)
    if expected and actual != expected:
        update_status(project_id, intent_id, "superseded")
        return {
            "applied": False,
            "reason": "drift",
            "friendly_zh": "你标记的是旧版本，视频已经更新了。请刷新后重新标记，避免改错位置。",
            "intent_status": "superseded",
        }

    edits = load_edit_decisions(project_id)
    before = edits.get("cuts") or []
    after = _apply_actions(list(before), intent)
    edits["cuts"] = after
    save_edit_decisions(project_id, edits)
    update_status(project_id, intent_id, "applied")

    has_ops = bool(intent.get("actions"))
    removed = [c.get("id") for c in before if c not in after]
    return {
        "applied": True,
        "intent_status": "applied",
        "cut_count": {"before": len(before), "after": len(after)},
        "removed_cuts": removed,
        "plan": plan_text(intent),
        "friendly_zh": (
            "收到，我会按备注处理。"
            if not has_ops
            else "改好了，新版本已生成，去剪辑标签看看效果吧。"
        ),
    }


# ---- discovery (Agent entry point) ----------------------------------------

def list_pending(project_id: str) -> list[dict[str, Any]]:
    """Pending (or planned) intents, oldest first — the Agent's inbox."""
    from lib.edit_intents import list_intents

    return [i for i in list_intents(project_id) if i.get("status") in ("pending", "planned")]
