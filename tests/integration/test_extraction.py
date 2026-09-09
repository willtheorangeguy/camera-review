from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

from camreview.extraction import extract_events, extract_source_files
from camreview.models import MotionEvent, RecordingFile, SourceSegment


def _video(path: Path, seconds: int = 3) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 10.0, (160, 120))
    assert writer.isOpened()
    try:
        for index in range(seconds * 10):
            image = np.zeros((120, 160, 3), dtype=np.uint8)
            cv2.rectangle(image, (index, 30), (index + 20, 60), (255, 255, 255), -1)
            writer.write(image)
    finally:
        writer.release()


@pytest.mark.integration
def test_source_copy_is_deduplicated_and_handles_spaces(tmp_path: Path) -> None:
    root = tmp_path / "source footage"
    root.mkdir()
    path = root / "front_door_2026-08-12_03-33-00.avi"
    _video(path)
    recording = RecordingFile(path, root, "front_door", datetime(2026, 8, 12, 3, 33), "avi", 3)
    events = [
        MotionEvent(
            f"event-{index:03d}",
            recording.start + timedelta(seconds=index),
            recording.start + timedelta(seconds=index + 0.5),
            0.1,
            0.1,
            0.1,
            [SourceSegment(path.name, index, index + 0.5)],
        )
        for index in (1, 2)
    ]
    copied = extract_source_files(events, [recording], tmp_path / "review output")
    assert len(copied) == 1
    assert copied[0].read_bytes() == path.read_bytes()


@pytest.mark.integration
@pytest.mark.parametrize("accuracy", ["accurate", "fast"])
def test_event_extraction_modes(tmp_path: Path, accuracy: str) -> None:
    root = tmp_path / "source footage"
    root.mkdir()
    path = root / "cam_2026-08-12_03-33-00.avi"
    _video(path)
    recording = RecordingFile(path, root, "cam", datetime(2026, 8, 12, 3, 33), "avi", 3)
    event = MotionEvent(
        "cam-20260812-033301-001",
        recording.start + timedelta(seconds=1),
        recording.start + timedelta(seconds=2),
        0.1,
        0.1,
        0.1,
        [SourceSegment(path.name, 1, 2)],
    )
    created = extract_events(
        "cam",
        [event],
        [recording],
        tmp_path / "event output",
        pre_roll=0.25,
        post_roll=0.25,
        accuracy=accuracy,
    )
    assert len(created) == 1
    assert created[0].is_file()
    assert created[0].stat().st_size > 0
