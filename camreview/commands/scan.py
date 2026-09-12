from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import load_config, resolve_settings
from ..decoding import PyAVDecoder, RecordingDecodeError
from ..detection import UltralyticsDetector, classify_events
from ..errors import DetectorUnavailableError, NoRecordingsError, StrictRecordingError
from ..extraction import extract_events, extract_source_files
from ..models import (
    PerformanceStats,
    ProcessingIssue,
    ScanReport,
    TimelineGap,
)
from ..motion import EventBuilder, MOG2MotionDetector
from ..reports import write_reports
from ..timeline import (
    build_time_range,
    detect_gaps,
    recording_overlaps,
    source_segments_for_window,
)
from .common import filter_events, parse_categories, prepare_recordings

LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class ScanRequest:
    root: Path
    camera: str | None = None
    date: str | None = None
    time_spec: str | None = None
    from_time: str | None = None
    to_time: str | None = None
    recursive: bool = False
    settle_seconds: float = 0.0
    strict: bool = False
    config: Path | None = None
    cli_settings: dict[str, Any] = field(default_factory=dict)
    report_dir: Path | None = None
    report_formats: set[str] = field(default_factory=lambda: {"json", "csv", "txt"})
    extract: Path | None = None
    extract_mode: str = "source"
    extract_accuracy: str = "accurate"
    only: set[str] = field(default_factory=set)
    exclude: set[str] = field(default_factory=set)
    quiet: bool = False


def _duration_in_range(
    start: datetime,
    duration: float,
    requested_start: datetime | None,
    requested_end: datetime | None,
) -> float:
    end = start + timedelta(seconds=duration)
    overlap_start = max(start, requested_start) if requested_start else start
    overlap_end = min(end, requested_end) if requested_end else end
    return max(0.0, (overlap_end - overlap_start).total_seconds())


def _normalize_gaps(
    gaps: list[TimelineGap], requested_start: datetime | None, requested_end: datetime | None
) -> list[TimelineGap]:
    clipped: list[TimelineGap] = []
    for gap in sorted(gaps, key=lambda item: item.start):
        start = max(gap.start, requested_start) if requested_start else gap.start
        end = min(gap.end, requested_end) if requested_end else gap.end
        if end <= start:
            continue
        if clipped and start <= clipped[-1].end:
            clipped[-1].end = max(clipped[-1].end, end)
            if gap.reason not in clipped[-1].reason:
                clipped[-1].reason += f"; {gap.reason}"
        else:
            clipped.append(TimelineGap(start, end, gap.reason))
    return clipped


def run_scan(request: ScanRequest) -> tuple[ScanReport, dict[str, Path], list[Path]]:
    started = time.monotonic()
    notify = None if request.quiet else lambda message: print(message, flush=True)
    config = load_config(request.config)
    initial_decoder = PyAVDecoder(str(request.cli_settings.get("hwdecode") or "none"))
    recordings, camera, recording_date, _, issues = prepare_recordings(
        request.root,
        initial_decoder,
        recursive=request.recursive,
        settle_seconds=request.settle_seconds,
        camera=request.camera,
        date_selector=request.date,
        strict=request.strict,
        probe=False,
        notify=notify,
    )
    settings = resolve_settings(config, camera, request.cli_settings)
    decoder = PyAVDecoder(settings.hwdecode)
    requested = build_time_range(
        recording_date,
        time_spec=request.time_spec,
        from_time=request.from_time,
        to_time=request.to_time,
    )
    usable = []
    unprocessed_gaps: list[TimelineGap] = []
    if notify:
        notify("Checking video metadata and durations...")
    metadata_interval = max(1, len(recordings) // 20)
    for metadata_index, recording in enumerate(recordings, 1):
        if notify and (
            metadata_index == 1
            or metadata_index == len(recordings)
            or metadata_index % metadata_interval == 0
        ):
            notify(f"[metadata {metadata_index:,}/{len(recordings):,}] {recording.relative_path}")
        try:
            info = decoder.probe(recording)
            recording.duration_seconds = info.duration_seconds
            usable.append(recording)
        except DetectorUnavailableError:
            raise
        except Exception as exc:
            if request.strict:
                raise StrictRecordingError(
                    f"Could not read {recording.relative_path}: {exc}"
                ) from exc
            issues.append(ProcessingIssue(recording.relative_path, str(exc), recording.start))
            unprocessed_gaps.append(
                TimelineGap(
                    recording.start,
                    recording.start + timedelta(seconds=recording.duration_seconds or 60),
                    "recording could not be probed",
                )
            )
    recordings = usable
    if not recordings:
        raise NoRecordingsError("No readable matching recordings were found")
    if notify:
        notify(
            f"Metadata check complete: {len(recordings):,} readable, "
            f"{len(unprocessed_gaps):,} skipped.\n"
        )
    selected = [
        item
        for item in recordings
        if recording_overlaps(item, requested, warmup_seconds=settings.warmup)
    ]
    if not selected:
        raise NoRecordingsError("No recordings overlap the requested time range")
    gaps = list(unprocessed_gaps)
    detector = MOG2MotionDetector(settings)
    event_builder = EventBuilder(
        settings.trigger_frames, settings.quiet_seconds, settings.merge_gap
    )
    performance = PerformanceStats()
    performance.video_decoder = decoder.decoder_name
    scene_changes = 0
    previous_end: datetime | None = None
    model_ready_at: datetime | None = None
    interrupted = False
    if not request.quiet:
        range_label = (
            "ALL" if requested.all else f"{requested.start:%H:%M:%S} - {requested.end:%H:%M:%S}"
        )
        print(
            f"Camera: {camera}\nDate: {recording_date.isoformat()}\n"
            f"Range: {range_label}\nFiles: {len(selected)}\n"
            f"Video decoder: {decoder.decoder_name}\n"
        )
    try:
        for index, recording in enumerate(selected, 1):
            if previous_end is not None:
                gap_seconds = (recording.start - previous_end).total_seconds()
                if gap_seconds > settings.reset_gap or gap_seconds < -1:
                    event_builder.break_continuity()
                    detector.reset()
                    model_ready_at = None
            first_frame_seconds: float | None = None
            last_frame_seconds: float | None = None
            last_frame_interval = 1.0 / settings.motion_fps
            try:
                for frame in decoder.iter_frames(
                    recording,
                    sample_fps=settings.motion_fps,
                    end_seconds=(
                        max(0.0, (requested.end - recording.start).total_seconds())
                        if requested.end and requested.end >= recording.start
                        else None
                    ),
                ):
                    if first_frame_seconds is None:
                        first_frame_seconds = frame.relative_seconds
                    if last_frame_seconds is not None:
                        last_frame_interval = frame.relative_seconds - last_frame_seconds
                    last_frame_seconds = frame.relative_seconds
                    if model_ready_at is None:
                        model_ready_at = frame.absolute_datetime + timedelta(
                            seconds=settings.warmup
                        )
                    sample = detector.process_frame(frame)
                    performance.motion_frames += 1
                    if frame.absolute_datetime < model_ready_at:
                        continue
                    if sample.scene_change:
                        scene_changes += 1
                    if requested.contains(frame.absolute_datetime):
                        event_builder.process(sample)
                performance.files_processed += 1
                if first_frame_seconds is not None and last_frame_seconds is not None:
                    decoded_duration = last_frame_seconds + last_frame_interval
                    recording.duration_seconds = decoded_duration
                    performance.video_seconds += _duration_in_range(
                        recording.start + timedelta(seconds=first_frame_seconds),
                        decoded_duration - first_frame_seconds,
                        requested.start,
                        requested.end,
                    )
            except DetectorUnavailableError:
                raise
            except Exception as exc:
                event_builder.break_continuity()
                detector.reset()
                model_ready_at = None
                if request.strict:
                    raise StrictRecordingError(
                        f"Failed processing {recording.relative_path}: {exc}"
                    ) from exc
                issue_kind = (
                    "network_or_filesystem_error"
                    if isinstance(exc, RecordingDecodeError) and exc.retryable
                    else "corrupt_or_unreadable"
                )
                issues.append(
                    ProcessingIssue(
                        recording.relative_path,
                        str(exc),
                        recording.start,
                        issue_kind,
                    )
                )
                performance.files_skipped += 1
                failed_from = recording.start
                reason = "recording could not be processed"
                if isinstance(exc, RecordingDecodeError):
                    reason += f" ({exc.stage} stage)"
                    if exc.last_successful_seconds is not None:
                        failed_from += timedelta(seconds=exc.last_successful_seconds)
                gaps.append(
                    TimelineGap(
                        failed_from,
                        recording.end or recording.start + timedelta(seconds=60),
                        reason,
                    )
                )
            previous_end = recording.end
            if not request.quiet:
                print(
                    f"[{index}/{len(selected)}] {recording.start:%H:%M:%S}  "
                    f"motion events: {len(event_builder._events)}",
                    end="\r" if index < len(selected) else "\n",
                    flush=True,
                )
    except KeyboardInterrupt:
        interrupted = True
    events = event_builder.finish(camera)
    for event in events:
        event.sources = source_segments_for_window(recordings, event.start, event.end)
    gaps = [*detect_gaps(recordings), *gaps]
    performance.files_skipped = len(
        [
            issue
            for issue in issues
            if issue.kind
            in {"unsettled_file", "corrupt_or_unreadable", "network_or_filesystem_error"}
        ]
    )
    performance.video_decoder = decoder.decoder_name
    performance.wall_seconds = time.monotonic() - started
    report_dir = request.report_dir or Path.cwd()
    report = ScanReport(
        camera=camera,
        recording_date=recording_date,
        source_root=request.root.resolve(),
        requested_range=requested,
        settings=settings,
        events=events,
        gaps=_normalize_gaps(gaps, requested.start, requested.end),
        issues=issues,
        performance=performance,
        scene_changes=scene_changes,
        status=(
            "interrupted"
            if interrupted
            else "motion_complete_classification_pending"
            if settings.classify
            else "complete"
        ),
    )
    if settings.classify and not interrupted:
        if notify:
            notify(
                "Motion scan complete. Saving a recoverable motion-only checkpoint "
                "before classification..."
            )
        checkpoint_paths = write_reports(
            report, report_dir, request.report_formats, display_events=events
        )
        if notify:
            notify(
                "Motion checkpoint saved. If classification fails, resume with: "
                f'camreview classify "{checkpoint_paths["json"].resolve()}"'
            )
    if settings.classify and not interrupted:
        object_detector = UltralyticsDetector(settings.model, settings.device, settings.confidence)
        if not request.quiet:
            print(f"Object detector: {object_detector.name}")
        classify_events(
            events,
            recordings,
            decoder,
            object_detector,
            settings,
            performance,
            notify=notify,
        )
        if not request.quiet:
            print(f"Device: {performance.device}")
        report.status = "complete"
    performance.video_decoder = decoder.decoder_name
    performance.wall_seconds = time.monotonic() - started
    displayed = filter_events(events, request.only, request.exclude)
    if notify:
        notify(
            f"Writing {', '.join(sorted(request.report_formats)).upper()} reports to "
            f"{report_dir.resolve()}..."
        )
    paths = write_reports(report, report_dir, request.report_formats, display_events=displayed)
    if notify:
        notify("Report writing complete.")
    extracted: list[Path] = []
    if request.extract is not None and not interrupted:
        if request.extract_mode == "source":
            extracted = extract_source_files(
                displayed,
                recordings,
                request.extract,
                notify=notify,
            )
        else:
            extracted = extract_events(
                camera,
                displayed,
                recordings,
                request.extract,
                pre_roll=settings.pre_roll,
                post_roll=settings.post_roll,
                accuracy=request.extract_accuracy,
                notify=notify,
            )
    if interrupted:
        raise KeyboardInterrupt
    return report, paths, extracted


def request_from_args(args: Any) -> ScanRequest:
    setting_names = {
        "motion_fps",
        "sensitivity",
        "min_motion_area",
        "var_threshold",
        "trigger_frames",
        "quiet_seconds",
        "merge_gap",
        "reset_gap",
        "warmup",
        "pre_roll",
        "post_roll",
        "scene_change_threshold",
        "mask",
        "analysis_width",
        "hwdecode",
        "classify",
        "classify_fps",
        "batch_size",
        "model",
        "device",
        "confidence",
        "motion_object_overlap",
    }
    cli_settings = {
        name: getattr(args, name)
        for name in setting_names
        if hasattr(args, name) and getattr(args, name) is not None
    }
    return ScanRequest(
        root=args.root,
        camera=args.camera,
        date=args.date,
        time_spec=args.time_spec,
        from_time=args.from_time,
        to_time=args.to_time,
        recursive=args.recursive,
        settle_seconds=args.settle_seconds,
        strict=args.strict,
        config=args.config,
        cli_settings=cli_settings,
        report_dir=args.report_dir,
        report_formats={item.strip() for item in args.report_format.split(",") if item.strip()},
        extract=args.extract,
        extract_mode=args.extract_mode,
        extract_accuracy=args.extract_accuracy,
        only=parse_categories(args.only),
        exclude=parse_categories(args.exclude),
        quiet=args.quiet,
    )


def print_completion(report: ScanReport, paths: dict[str, Path], extracted: list[Path]) -> None:
    motion_seconds = sum(item.duration_seconds for item in report.events)
    print(
        "\nScan complete.\n\n"
        f"Files processed:      {report.performance.files_processed}\n"
        f"Video scanned:        {report.performance.video_seconds:.1f}s\n"
        f"Video decoder:        {report.performance.video_decoder or 'CPU'}\n"
        f"Motion events:        {len(report.events)}\n"
        f"Total motion:         {motion_seconds:.1f}s\n"
        f"Effective speed:      {report.performance.to_dict()['effective_realtime_speed']:.1f}x\n"
        "\nReports:"
    )
    for path in paths.values():
        print(path.resolve())
    if extracted:
        print(f"Extracted files: {len(extracted)}")
