"""Shim: the ``lib`` package lives in src/openmontage/lib.

A leftover directory named ``lib/`` at repo root would otherwise become a
PEP 420 namespace package and hide ``src/openmontage/lib`` (cwd is searched
before PYTHONPATH). Point ``__path__`` at the real tree so ``from lib.xxx``
keeps working.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
_SRC_LIB = _SRC / "openmontage" / "lib"
_src_s = str(_SRC)
if _src_s not in sys.path:
    sys.path.insert(0, _src_s)

__path__ = [str(_SRC_LIB)] if _SRC_LIB.is_dir() else []
