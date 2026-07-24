#!/usr/bin/env python3
"""Smoke-test eRouter Chat (OpenAI-compatible).

Usage:
  python scripts/erouter_chat_smoke.py
  python scripts/erouter_chat_smoke.py --model claude-haiku-4-5
  python scripts/erouter_chat_smoke.py --prompt "用一句话介绍你自己"

Requires EROUTER_API_KEY in .env (see .env.example). Does not write keys.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

load_dotenv(REPO / ".env", override=True)

from tools._erouter.chat import chat_completions, extract_assistant_text  # noqa: E402
from tools._erouter.client import (  # noqa: E402
    ERouterError,
    get_erouter_api_key,
    get_erouter_base_url,
)
from tools._erouter.models import DEFAULT_CHAT_MODEL, list_models  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="eRouter chat smoke test")
    parser.add_argument(
        "--model",
        default=DEFAULT_CHAT_MODEL,
        help=f"chat model id (default: {DEFAULT_CHAT_MODEL})",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly: erouter-ok",
        help="user message content",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="print curated catalog and exit (no API call)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print full JSON response",
    )
    args = parser.parse_args()

    if args.list_models:
        for m in list_models():
            print(f"{m.status:8} {m.capability:6} {m.id}" + (f"  # {m.note}" if m.note else ""))
        return 0

    key = get_erouter_api_key()
    base = get_erouter_base_url()
    print(f"base_url={base}")
    print(f"api_key={'set' if key else 'MISSING'}")
    print(f"model={args.model}")

    if not key:
        print(
            "ERROR: EROUTER_API_KEY not set. Copy from .env.example into .env and fill your Proxy Key.",
            file=sys.stderr,
        )
        return 2

    try:
        response = chat_completions(
            [{"role": "user", "content": args.prompt}],
            model=args.model,
            max_tokens=64,
        )
    except ERouterError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        if getattr(exc, "http_status", None) is not None:
            print(f"http_status={exc.http_status}", file=sys.stderr)
        return 1

    text = extract_assistant_text(response)
    print(f"assistant: {text!r}")
    if args.raw:
        print(json.dumps(response, ensure_ascii=False, indent=2))
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
