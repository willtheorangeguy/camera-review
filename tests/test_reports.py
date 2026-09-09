from datetime import date, datetime
from pathlib import Path

from camreview.models import (
    MotionEvent,
    PerformanceStats,
    ScanReport,
    ScanSettings,
    SourceSegment,
    TimeRange,
)
from camreview.reports import load_report, write_reports


def test_report_round_trip_and_formats(tmp_path: Path) -> None:
    event = MotionEvent(
        "cam-20260812-033312-001",
        datetime(2026, 8, 12, 3, 33, 12, 250000),
        datetime(2026, 8, 12, 3, 33, 19, 750000),
        0.123,
        0.052,
        0.2,
        [SourceSegment("cam_2026-08-12_03-33-00.mkv", 12.25, 19.75)],
    )
    report = ScanReport(
        "cam",
        date(2026, 8, 12),
        tmp_path,
        TimeRange(None, None),
        ScanSettings(),
        [event],
        [],
        [],
        PerformanceStats(video_seconds=60, files_processed=1),
    )
    paths = write_reports(report, tmp_path, {"json", "csv", "txt"})
    assert set(paths) == {"json", "csv", "txt"}
    loaded = load_report(paths["json"])
    assert loaded.events[0].start == event.start
    assert loaded.events[0].sources[0].file == event.sources[0].file
    assert "CamReview Motion Report" in paths["txt"].read_text(encoding="utf-8")
    assert "event_id,camera,start" in paths["csv"].read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.tmp"))
