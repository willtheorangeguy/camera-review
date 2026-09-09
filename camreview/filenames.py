from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .models import RecordingFile

RECORDING_RE = re.compile(
    r"^(?P<camera>.+)_(?P<date>\d{4}-\d{2}-\d{2})_"
    r"(?P<time>\d{2}-\d{2}-\d{2})\.(?P<ext>mkv|mp4|mov|avi)$",
    re.IGNORECASE,
)
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".mov", ".avi"}


def parse_recording_filename(path: Path, source_root: Path | None = None) -> RecordingFile | None:
    match = RECORDING_RE.fullmatch(path.name)
    if match is None:
        return None
    try:
        start = datetime.strptime(
            f"{match.group('date')} {match.group('time')}", "%Y-%m-%d %H-%M-%S"
        )
    except ValueError:
        return None
    return RecordingFile(
        path=path,
        source_root=source_root or path.parent,
        camera=match.group("camera"),
        start=start,
        extension=match.group("ext").lower(),
    )
