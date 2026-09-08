"""Cross-platform exclusive, non-blocking advisory file lock.

`Graph`'s single-writer discipline (design doc §7 principle 7) needs one thing
from the OS: take an exclusive lock on a `.lock` sidecar and fail *immediately*
if another process already holds it, so a second writer is refused rather than
made to wait. POSIX gives that as `fcntl.flock(LOCK_EX | LOCK_NB)`; Windows gives
the equivalent as `msvcrt.locking(LK_NBLCK)`. Both raise on contention, which the
caller maps to `SingleWriterViolation`.

On POSIX the behaviour is byte-for-byte the previous `fcntl.flock` call — this
module only adds the Windows branch. No third-party dependency: the project is
stdlib-only (pyproject lists pydantic and nothing else).
"""
from __future__ import annotations

import contextlib
import sys
from typing import IO

if sys.platform == "win32":
    import msvcrt

    def lock_exclusive_nonblocking(f: IO) -> None:
        """Raise `BlockingIOError` if the lock is already held elsewhere."""
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:  # already locked, or region unavailable
            raise BlockingIOError(str(exc)) from exc

    def unlock(f: IO) -> None:
        f.seek(0)
        # Release can fail only if the region was never locked, which for our
        # single owner means nothing to undo — suppress rather than mask a real
        # error the caller could act on.
        with contextlib.suppress(OSError):
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def lock_exclusive_nonblocking(f: IO) -> None:
        """Raise `BlockingIOError` if the lock is already held elsewhere."""
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def unlock(f: IO) -> None:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
