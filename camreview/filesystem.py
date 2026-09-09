from __future__ import annotations

import errno
import os
import shutil
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import IO

_TRANSIENT_ERRNOS = {errno.EACCES, errno.EBUSY, errno.EPERM}
_UNSUPPORTED_SYNC_ERRNOS = {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}
_TRANSIENT_WINERRORS = {5, 32, 33, 64, 121}


def _is_transient(exc: OSError) -> bool:
    return exc.errno in _TRANSIENT_ERRNOS or getattr(exc, "winerror", None) in _TRANSIENT_WINERRORS


def stat_path(path: Path, *, attempts: int = 3) -> os.stat_result:
    """Stat a path with short retries for transient SMB errors."""
    for attempt in range(attempts):
        try:
            return path.stat()
        except OSError as exc:
            if not _is_transient(exc) or attempt + 1 >= attempts:
                raise
            time.sleep(0.1 * (2**attempt))
    raise RuntimeError("unreachable")


def flush_file(handle: IO[str] | IO[bytes]) -> None:
    """Flush data, tolerating SMB implementations that do not expose fsync."""
    handle.flush()
    try:
        os.fsync(handle.fileno())
    except OSError as exc:
        if exc.errno not in _UNSUPPORTED_SYNC_ERRNOS:
            raise


def atomic_replace(source: Path, destination: Path, *, attempts: int = 5) -> None:
    """Replace a sibling destination, retrying transient SMB sharing failures."""
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            if not _is_transient(exc) or attempt + 1 >= attempts:
                raise
            time.sleep(0.1 * (2**attempt))


def atomic_copy(source: Path, destination: Path) -> None:
    """Copy to a destination-side temporary file, then rename it into place."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        with temporary.open("r+b") as handle:
            flush_file(handle)
        # Some shares permit file creation but not timestamp/attribute changes.
        with suppress(OSError):
            shutil.copystat(source, temporary)
        atomic_replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
