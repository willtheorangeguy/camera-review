from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from camreview.models import RecordingFile


@pytest.fixture
def recording(tmp_path: Path) -> RecordingFile:
    return RecordingFile(
        tmp_path / "living_room_2026-08-12_03-33-00.mkv",
        tmp_path,
        "living_room",
        datetime(2026, 8, 12, 3, 33),
        "mkv",
        60.0,
    )
