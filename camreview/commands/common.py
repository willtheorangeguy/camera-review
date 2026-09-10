from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from ..decoding.base import VideoDecoder
from ..errors import NoRecordingsError, StrictRecordingError
from ..models import MotionEvent, ProcessingIssue, RecordingFile
from ..timeline import DiscoveryResult, discover_recordings, select_camera_and_date


def parse_date_selector(value: str | None) -> date | None:
    if value is None:
        return None
    if value.casefold() == "yesterday":
        return date.today() - timedelta(days=1)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        from ..errors import ConfigurationError

        raise ConfigurationError("--date must be YYYY-MM-DD or yesterday") from exc


def prepare_recordings(
    root: Path,
    decoder: VideoDecoder,
    *,
    recursive: bool,
    settle_seconds: float,
    camera: str | None,
    date_selector: str | None,
    strict: bool,
    probe: bool = True,
    notify: Callable[[str], None] | None = None,
) -> tuple[list[RecordingFile], str, date, DiscoveryResult, list[ProcessingIssue]]:
    resolved_root = root.expanduser().resolve()
    if notify:
        notify(
            f"Discovering video files in {resolved_root} "
            f"({'recursive' if recursive else 'top-level only'})..."
        )
    discovered = discover_recordings(
        resolved_root, recursive=recursive, settle_seconds=settle_seconds
    )
    if notify:
        notify(
            f"Discovery complete: {len(discovered.recordings):,} recognized, "
            f"{len(discovered.unrecognized):,} unrecognized, "
            f"{len(discovered.unsettled):,} still settling, "
            f"{len(discovered.inaccessible):,} inaccessible."
        )
    if strict and discovered.unrecognized:
        raise StrictRecordingError(
            f"Unrecognized video filename: {discovered.unrecognized[0].name}"
        )
    if strict and discovered.inaccessible:
        path, error = discovered.inaccessible[0]
        raise StrictRecordingError(f"Could not access {path}: {error}")
    recordings, selected_camera, selected_date = select_camera_and_date(
        discovered.recordings,
        camera=camera,
        recording_date=parse_date_selector(date_selector),
    )
    if notify:
        notify(
            f"Selected camera {selected_camera!r}, date {selected_date.isoformat()}: "
            f"{len(recordings):,} candidate file(s)."
        )
    issues = [
        ProcessingIssue(
            file=path.relative_to(resolved_root).as_posix(),
            error="filename does not match the supported camera timestamp format",
            kind="unrecognized_filename",
        )
        for path in discovered.unrecognized
    ]
    issues.extend(
        ProcessingIssue(
            file=path.relative_to(resolved_root).as_posix(),
            error=f"file modified less than {settle_seconds:g} seconds ago",
            kind="unsettled_file",
        )
        for path in discovered.unsettled
    )
    issues.extend(
        ProcessingIssue(
            file=(
                path.relative_to(resolved_root).as_posix()
                if path.is_relative_to(resolved_root)
                else str(path)
            ),
            error=error,
            kind="network_or_filesystem_error",
        )
        for path, error in discovered.inaccessible
    )
    if not probe:
        return recordings, selected_camera, selected_date, discovered, issues
    usable: list[RecordingFile] = []
    if notify:
        notify("Checking video metadata and durations...")
    interval = max(1, len(recordings) // 20)
    for index, recording in enumerate(recordings, 1):
        if notify and (index == 1 or index == len(recordings) or index % interval == 0):
            notify(f"[metadata {index:,}/{len(recordings):,}] {recording.relative_path}")
        try:
            info = decoder.probe(recording)
            recording.duration_seconds = info.duration_seconds
            usable.append(recording)
        except Exception as exc:
            if strict:
                raise StrictRecordingError(
                    f"Could not read {recording.relative_path}: {exc}"
                ) from exc
            issues.append(
                ProcessingIssue(
                    recording.relative_path,
                    str(exc),
                    recording.start,
                )
            )
    if not usable:
        raise NoRecordingsError("No readable matching recordings were found")
    if notify:
        notify(
            f"Metadata check complete: {len(usable):,} readable, "
            f"{len(recordings) - len(usable):,} skipped."
        )
    return usable, selected_camera, selected_date, discovered, issues


def filter_events(
    events: list[MotionEvent], only: set[str], exclude: set[str]
) -> list[MotionEvent]:
    selected: list[MotionEvent] = []
    for event in events:
        categories = set(event.classification.categories) if event.classification else set()
        if only and not categories.intersection(only):
            continue
        if exclude and categories.intersection(exclude):
            continue
        selected.append(event)
    return selected


def parse_categories(value: str | None) -> set[str]:
    return {item.strip().casefold() for item in (value or "").split(",") if item.strip()}
