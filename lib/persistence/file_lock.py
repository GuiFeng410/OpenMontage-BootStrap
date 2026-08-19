"""Project-scoped OS file lock for checkpoint transactions.

Does not own runner.lock. Lock filename, Windows byte-0 init, timeout, and
poll semantics stay compatible with lib.checkpoint.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl

CHECKPOINT_LOCK_FILENAME = ".checkpoint.lock"
CHECKPOINT_LOCK_TIMEOUT_SECONDS = 10.0
CHECKPOINT_LOCK_POLL_SECONDS = 0.02
_LOCK_FILE_INIT_GUARD = threading.Lock()


class CheckpointLockTimeout(TimeoutError):
    """Raised when the project checkpoint lock cannot be acquired in time."""


@contextmanager
def project_checkpoint_lock(
    pipeline_dir: Path,
    project_id: str,
    *,
    timeout: float = CHECKPOINT_LOCK_TIMEOUT_SECONDS,
    poll_seconds: float = CHECKPOINT_LOCK_POLL_SECONDS,
    lock_filename: str = CHECKPOINT_LOCK_FILENAME,
) -> Iterator[None]:
    """Serialize one project's checkpoint transaction with an OS-owned lock."""
    project_dir = pipeline_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    lock_path = project_dir / lock_filename
    # Initialize byte 0 without a buffered file object. On Windows, separate
    # processes may both observe a newly-created lock file as empty. O_APPEND
    # makes each stale observer write at the then-current EOF, so a process
    # cannot flush back onto byte 0 after another process has locked it.
    with _LOCK_FILE_INIT_GUARD:
        init_fd = os.open(
            lock_path,
            os.O_CREAT | os.O_APPEND | os.O_RDWR,
        )
        try:
            if os.fstat(init_fd).st_size == 0:
                os.write(init_fd, b"\0")
        finally:
            os.close(init_fd)
    lock_file = open(lock_path, "r+b", buffering=0)
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while not acquired:
            lock_file.seek(0)
            try:
                if os.name == "nt":
                    msvcrt.locking(
                        lock_file.fileno(),
                        msvcrt.LK_NBLCK,
                        1,
                    )
                else:
                    fcntl.flock(
                        lock_file.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise CheckpointLockTimeout(
                        f"checkpoint lock timeout for project {project_id!r}"
                    ) from exc
                time.sleep(poll_seconds)
                continue
            acquired = True
        yield
    finally:
        if acquired:
            try:
                lock_file.seek(0)
                if os.name == "nt":
                    msvcrt.locking(
                        lock_file.fileno(),
                        msvcrt.LK_UNLCK,
                        1,
                    )
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_file.close()
