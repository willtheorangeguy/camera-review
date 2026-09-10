from __future__ import annotations

import stat
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from pathlib import Path

from .errors import ConfigurationError, NoRecordingsError
from .filenames import VIDEO_EXTENSIONS, parse_recording_filename
from .filesystem import stat_path
from .models import RecordingFile, SourceSegment, TimelineGap, TimeRange


@dataclass(slots=True)
class DiscoveryResult:
    recordings: list[RecordingFile]
    unrecognized: list[Path]
    unsettled: list[Path]
    inaccessible: list[tuple[Path, str]]


def discover_recordings(
    root: Path,
    *,
    recursive: bool = False,
    settle_seconds: float = 0,
    now_timestamp: float | None = None,
) -> DiscoveryResult:
    # Resolve once before enumerating.  In particular, this turns a relative
    # filename under a Windows mapped drive into an absolute (usually UNC)
    # filename.  Native libraries such as FFmpeg do not reliably inherit
    # PowerShell's per-drive/UNC working-directory semantics.
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ConfigurationError(f"Recording directory does not exist: {root}")
    candidates = root.rglob("*") if recursive else root.glob("*")
    recordings: list[RecordingFile] = []
    unrecognized: list[Path] = []
    unsettled: list[Path] = []
    inaccessible: list[tuple[Path, str]] = []
    if now_timestamp is None:
        import time as time_module

        now_timestamp = time_module.time()
    for path in candidates:
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        try:
            file_stat = stat_path(path)
        except OSError as exc:
            inaccessible.append((path, str(exc)))
            continue
        if not stat.S_ISREG(file_stat.st_mode):
            continue
        parsed = parse_recording_filename(path, root)
        if parsed is None:
            unrecognized.append(path)
            continue
        if settle_seconds > 0 and now_timestamp - file_stat.st_mtime < settle_seconds:
            unsettled.append(path)
            continue
        recordings.append(parsed)
    recordings.sort(key=lambda item: (item.start, item.path.name))
    return DiscoveryResult(
        recordings,
        sorted(unrecognized),
        sorted(unsettled),
        sorted(inaccessible, key=lambda item: str(item[0])),
    )


def select_camera_and_date(
    recordings: list[RecordingFile],
    *,
    camera: str | None = None,
    recording_date: date | None = None,
) -> tuple[list[RecordingFile], str, date]:
    if not recordings:
        raise NoRecordingsError("No recognized recording files were found")
    cameras = sorted({item.camera for item in recordings})
    if camera is None and len(cameras) > 1:
        choices = ", ".join(cameras)
        raise ConfigurationError(f"Multiple cameras found ({choices}); choose one with --camera")
    selected_camera = camera or cameras[0]
    if selected_camera not in cameras:
        raise NoRecordingsError(f"No recordings found for camera {selected_camera!r}")
    camera_files = [item for item in recordings if item.camera == selected_camera]
    dates = sorted({item.start.date() for item in camera_files})
    if recording_date is None and len(dates) > 1:
        choices = ", ".join(item.isoformat() for item in dates)
        raise ConfigurationError(f"Multiple dates found ({choices}); choose one with --date")
    selected_date = recording_date or dates[0]
    selected = [item for item in camera_files if item.start.date() == selected_date]
    if not selected:
        raise NoRecordingsError(
            f"No recordings found for {selected_camera!r} on {selected_date.isoformat()}"
        )
    return selected, selected_camera, selected_date


def parse_clock(value: str) -> time:
    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, pattern).time()
        except ValueError:
            pass
    raise ConfigurationError(f"Invalid time {value!r}; expected HH:MM or HH:MM:SS")


def build_time_range(
    recording_date: date,
    *,
    time_spec: str | None,
    from_time: str | None,
    to_time: str | None,
) -> TimeRange:
    if time_spec is not None and (from_time is not None or to_time is not None):
        raise ConfigurationError("Use either --time or --from/--to, not both")
    if (from_time is None) != (to_time is None):
        raise ConfigurationError("--from and --to must be supplied together")
    if time_spec is None and from_time is None:
        time_spec = "all"
    if time_spec is not None:
        if time_spec.lower() == "all":
            return TimeRange(None, None)
        parts = time_spec.split("-", maxsplit=1)
        if len(parts) != 2:
            raise ConfigurationError("--time must be 'all' or START-END")
        from_time, to_time = parts
    assert from_time is not None and to_time is not None
    start = datetime.combine(recording_date, parse_clock(from_time))
    end = datetime.combine(recording_date, parse_clock(to_time))
    if end <= start:
        raise ConfigurationError("The end time must be later than the start time")
    return TimeRange(start, end)


def recording_overlaps(
    recording: RecordingFile, requested: TimeRange, *, warmup_seconds: float = 0
) -> bool:
    if requested.all:
        return True
    start = requested.start - timedelta(seconds=warmup_seconds) if requested.start else None
    end = requested.end
    recording_end = recording.end or recording.start + timedelta(seconds=60)
    return (start is None or recording_end >= start) and (end is None or recording.start <= end)


def detect_gaps(
    recordings: list[RecordingFile], threshold_seconds: float = 1.0
) -> list[TimelineGap]:
    gaps: list[TimelineGap] = []
    intervals = [
        (second.start - first.start).total_seconds()
        for first, second in pairwise(recordings)
        if 0 < (second.start - first.start).total_seconds() < 300
    ]
    inferred_duration = 60.0
    if intervals:
        rounded = Counter(round(value) for value in intervals)
        bucket, occurrences = rounded.most_common(1)[0]
        if occurrences > 1:
            matching = [value for value in intervals if round(value) == bucket]
            inferred_duration = sum(matching) / len(matching)
        else:
            ordered = sorted(intervals)
            midpoint = len(ordered) // 2
            median = (
                ordered[midpoint]
                if len(ordered) % 2
                else (ordered[midpoint - 1] + ordered[midpoint]) / 2
            )
            inferred_duration = min(60.0, median)
    for previous, current in pairwise(recordings):
        previous_end = previous.end
        if previous_end is None:
            previous_end = previous.start + timedelta(seconds=inferred_duration)
        gap = (current.start - previous_end).total_seconds()
        if gap > threshold_seconds:
            gaps.append(TimelineGap(previous_end, current.start))
    return gaps


def source_segments_for_window(
    recordings: list[RecordingFile], start: datetime, end: datetime
) -> list[SourceSegment]:
    """Map an absolute event window to its overlapping recording-relative spans."""
    segments: list[SourceSegment] = []
    for recording in recordings:
        recording_end = recording.end or recording.start + timedelta(seconds=60)
        overlap_start = max(start, recording.start)
        overlap_end = min(end, recording_end)
        if overlap_end <= overlap_start:
            continue
        segments.append(
            SourceSegment(
                file=recording.relative_path,
                relative_start=max(0.0, (overlap_start - recording.start).total_seconds()),
                relative_end=max(0.0, (overlap_end - recording.start).total_seconds()),
            )
        )
    return segments
