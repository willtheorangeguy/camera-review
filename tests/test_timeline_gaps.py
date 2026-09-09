from datetime import datetime
from pathlib import Path

from camreview.models import RecordingFile
from camreview.timeline import detect_gaps


def test_gap_uses_actual_duration(tmp_path: Path) -> None:
    recordings = [
        RecordingFile(
            tmp_path / "cam_2026-08-12_10-41-00.mkv",
            tmp_path,
            "cam",
            datetime(2026, 8, 12, 10, 41),
            "mkv",
            60,
        ),
        RecordingFile(
            tmp_path / "cam_2026-08-12_10-42-00.mkv",
            tmp_path,
            "cam",
            datetime(2026, 8, 12, 10, 42),
            "mkv",
            60,
        ),
        RecordingFile(
            tmp_path / "cam_2026-08-12_10-45-00.mkv",
            tmp_path,
            "cam",
            datetime(2026, 8, 12, 10, 45),
            "mkv",
            60,
        ),
    ]
    gaps = detect_gaps(recordings)
    assert len(gaps) == 1
    assert gaps[0].start == datetime(2026, 8, 12, 10, 43)
    assert gaps[0].end == datetime(2026, 8, 12, 10, 45)


def test_single_short_interval_does_not_redefine_filename_cadence(tmp_path: Path) -> None:
    starts = [
        datetime(2026, 8, 12, 10, 0, 0),
        datetime(2026, 8, 12, 10, 0, 4),
        datetime(2026, 8, 12, 10, 1, 0),
        datetime(2026, 8, 12, 10, 2, 0),
        datetime(2026, 8, 12, 10, 3, 0),
    ]
    recordings = [
        RecordingFile(
            tmp_path / f"cam_{start:%Y-%m-%d_%H-%M-%S}.mkv",
            tmp_path,
            "cam",
            start,
            "mkv",
        )
        for start in starts
    ]
    gaps = detect_gaps(recordings)
    assert gaps == []
