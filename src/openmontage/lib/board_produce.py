"""Start and poll a local produce job after minimal assets_gate.

Facade over lib.produce. Existing `from lib.board_produce import sync_produce`
callers keep working. Browser still does not generate.
"""

from __future__ import annotations

from lib.paths import PROJECTS_DIR, REPO_ROOT
from lib.produce import compose_adapter as _compose
from lib.produce import job_store as _jobs
from lib.produce import orchestrator as _orch
from lib.produce import video_adapter as _video

for _mod in (_jobs, _compose, _video, _orch):
    for _name in dir(_mod):
        if _name.startswith("__"):
            continue
        globals()[_name] = getattr(_mod, _name)

del _mod, _name, _jobs, _compose, _video, _orch
