from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from camreview.decoding.pyav_decoder import PyAVDecoder
from camreview.models import RecordingFile
from camreview.timeline import source_segments_for_window


def _make_cumulative_timestamp_segments(root: Path) -> list[Path]:
    output = root / "segment-%02d.mkv"
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=10:duration=12",
            "-c:v",
            "ffv1",
            "-g",
            "30",
            "-f",
            "segment",
            "-segment_time",
            "3",
            "-reset_timestamps",
            "0",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return sorted(root.glob("segment-*.mkv"))


@pytest.mark.integration
def test_cumulative_container_timestamps_are_normalized_per_file(tmp_path: Path) -> None:
    paths = _make_cumulative_timestamp_segments(tmp_path)
    assert len(paths) == 4

    timeline_start = datetime(2026, 8, 12, 18, 20)
    recordings = [
        RecordingFile(
            path,
            tmp_path,
            "basement",
            timeline_start + timedelta(seconds=index * 3),
            "mkv",
        )
        for index, path in enumerate(paths)
    ]

    decoder = PyAVDecoder()
    for recording in recordings:
        recording.duration_seconds = decoder.probe(recording).duration_seconds

    assert [item.duration_seconds for item in recordings] == pytest.approx([3.0] * 4)

    event_start = timeline_start + timedelta(seconds=10)
    segments = source_segments_for_window(
        recordings,
        event_start,
        event_start + timedelta(seconds=0.7),
    )

    assert len(segments) == 1
    assert segments[0].file == paths[-1].name
    assert segments[0].relative_start == pytest.approx(1.0)
    assert segments[0].relative_end == pytest.approx(1.7)
