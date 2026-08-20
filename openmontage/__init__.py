"""Shim: the installable package lives in src/openmontage.

A leftover directory named ``openmontage/`` at repo root would otherwise
become a PEP 420 namespace package and hide ``src/openmontage`` even when
``PYTHONPATH`` includes ``src/`` (cwd is searched first).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
_SRC_PKG = _SRC / "openmontage"
_src_s = str(_SRC)
if _src_s not in sys.path:
    sys.path.insert(0, _src_s)

__path__ = [str(_SRC_PKG)] if _SRC_PKG.is_dir() else []
__path__.append(str(Path(__file__).resolve().parent))

from openmontage.product_version import PRODUCT_VERSION  # noqa: E402

__version__ = PRODUCT_VERSION
