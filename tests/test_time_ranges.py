from datetime import date, datetime
from pathlib import Path

import pytest

from camreview.errors import ConfigurationError
from camreview.models import RecordingFile
from camreview.timeline import build_time_range, recording_overlaps


def test_all_time() -> None:
    requested = build_time_range(date(2026, 8, 12), time_spec="all", from_time=None, to_time=None)
    assert requested.all


def test_range_with_seconds() -> None:
    requested = build_time_range(
        date(2026, 8, 12),
        time_spec="03:33:15-03:35:45",
        from_time=None,
        to_time=None,
    )
    assert requested.start == datetime(2026, 8, 12, 3, 33, 15)
    assert requested.end == datetime(2026, 8, 12, 3, 35, 45)


def test_overlapping_file_is_included(tmp_path: Path) -> None:
    recording = RecordingFile(
        tmp_path / "cam_2026-08-12_03-33-00.mkv",
        tmp_path,
        "cam",
        datetime(2026, 8, 12, 3, 33),
        "mkv",
        60,
    )
    requested = build_time_range(
        date(2026, 8, 12),
        time_spec="03:33:30-03:34:30",
        from_time=None,
        to_time=None,
    )
    assert recording_overlaps(recording, requested)


def test_contradictory_syntax() -> None:
    with pytest.raises(ConfigurationError, match="either"):
        build_time_range(
            date(2026, 8, 12),
            time_spec="all",
            from_time="03:00",
            to_time="04:00",
        )
