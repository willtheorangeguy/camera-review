from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pytest

from camreview.commands.scan import ScanRequest, run_scan
from camreview.errors import DetectorUnavailableError


def _make_video(path: Path, expression: str, duration: float = 8.0) -> None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=320x240:r=20:d={duration}",
            "-vf",
            expression,
            "-c:v",
            "ffv1",
            "-y",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _make_moving_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 20.0, (320, 240))
    assert writer.isOpened()
    try:
        for index in range(160):
            image = np.zeros((240, 320, 3), dtype=np.uint8)
            if 40 <= index <= 100:
                x = 20 + (index - 40) * 2
                cv2.rectangle(image, (x, 80), (x + 50, 130), (255, 255, 255), -1)
            writer.write(image)
    finally:
        writer.release()


def _make_cross_file_video(path: Path, part: int) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 20.0, (320, 240))
    assert writer.isOpened()
    try:
        for index in range(80):
            image = np.zeros((240, 320, 3), dtype=np.uint8)
            absolute_index = index + part * 80
            if 50 <= absolute_index <= 110:
                x = 20 + (absolute_index - 50) * 2
                cv2.rectangle(image, (x, 80), (x + 50, 130), (255, 255, 255), -1)
            writer.write(image)
    finally:
        writer.release()


@pytest.mark.integration
def test_static_video_has_no_events_and_reports_preparation_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    video = tmp_path / "cam_2026-08-12_03-33-00.mkv"
    _make_video(video, "null")
    report, _, _ = run_scan(
        ScanRequest(
            tmp_path,
            time_spec="all",
            report_dir=tmp_path / "reports",
            report_formats={"json"},
            cli_settings={"warmup": 1.0},
            quiet=False,
        )
    )
    assert report.events == []
    output = capsys.readouterr().out
    assert "Discovering video files" in output
    assert "[metadata 1/1]" in output
    assert "Metadata check complete" in output
    assert output.index("Discovering video files") < output.index("Camera: cam")


@pytest.mark.integration
def test_moving_rectangle_creates_timestamped_event(tmp_path: Path) -> None:
    video = tmp_path / "cam_2026-08-12_03-33-00.avi"
    _make_moving_video(video)
    report, _, _ = run_scan(
        ScanRequest(
            tmp_path,
            time_spec="all",
            report_dir=tmp_path / "reports",
            report_formats={"json"},
            cli_settings={"warmup": 1.0, "sensitivity": "high", "motion_fps": 4},
            quiet=True,
        )
    )
    assert len(report.events) == 1
    assert (
        1.5
        <= (report.events[0].start - report.events[0].start.replace(second=0)).total_seconds()
        <= 3
    )
    assert 4 <= (report.events[0].end - report.events[0].end.replace(second=0)).total_seconds() <= 6


@pytest.mark.integration
def test_motion_event_crosses_file_boundary(tmp_path: Path) -> None:
    _make_cross_file_video(tmp_path / "cam_2026-08-12_03-33-00.avi", 0)
    _make_cross_file_video(tmp_path / "cam_2026-08-12_03-33-04.avi", 1)
    report, _, _ = run_scan(
        ScanRequest(
            tmp_path,
            time_spec="all",
            report_dir=tmp_path / "reports",
            report_formats={"json"},
            cli_settings={"warmup": 1.0, "sensitivity": "high", "motion_fps": 4},
            quiet=True,
        )
    )
    assert len(report.events) == 1
    assert len(report.events[0].sources) == 2
    boundary = datetime(2026, 8, 12, 3, 33, 4)
    assert report.events[0].start < boundary < report.events[0].end


@pytest.mark.integration
def test_classification_failure_leaves_motion_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "cam_2026-08-12_03-33-00.avi"
    _make_moving_video(video)

    def fail_classification(*args, **kwargs) -> None:
        raise DetectorUnavailableError("simulated detector failure")

    monkeypatch.setattr("camreview.commands.scan.classify_events", fail_classification)
    report_dir = tmp_path / "reports"
    with pytest.raises(DetectorUnavailableError, match="simulated"):
        run_scan(
            ScanRequest(
                tmp_path,
                time_spec="all",
                report_dir=report_dir,
                report_formats={"json"},
                cli_settings={
                    "warmup": 1.0,
                    "sensitivity": "high",
                    "motion_fps": 4,
                    "classify": True,
                },
                quiet=True,
            )
        )
    checkpoint = json.loads((report_dir / "cam_2026-08-12_motion.json").read_text(encoding="utf-8"))
    assert checkpoint["run"]["status"] == "motion_complete_classification_pending"
    assert checkpoint["summary"]["motion_events"] == 1
