"""Checkpoint writer/reader for pipeline state persistence.

Each stage writes a checkpoint after completion. The orchestrator uses
checkpoints to resume pipelines and to present state at human checkpoints.

Facade over checkpoint_validate / checkpoint_commercial / checkpoint_store.
Existing `from lib.checkpoint import merge_write_checkpoint` callers keep working.
"""

from __future__ import annotations

from lib.paths import PROJECTS_DIR
from lib import checkpoint_validate as _validate
from lib import checkpoint_commercial as _commercial
from lib import checkpoint_store as _store

for _mod in (_validate, _commercial, _store):
    for _name in dir(_mod):
        if _name.startswith("__"):
            continue
        globals()[_name] = getattr(_mod, _name)

del _mod, _name, _validate, _commercial, _store
