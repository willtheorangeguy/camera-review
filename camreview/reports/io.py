from __future__ import annotations

import csv
import json
import os
import tempfile
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from ..errors import ConfigurationError
from ..filesystem import atomic_replace, flush_file
from ..models import (
    MotionEvent,
    PerformanceStats,
    ProcessingIssue,
    ScanReport,
    ScanSettings,
    TimelineGap,
    TimeRange,
)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            flush_file(handle)
        atomic_replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _classification_text(event: MotionEvent) -> str:
    if event.classification is None:
        return "not run"
    return ", ".join(event.classification.categories) or "unknown"


def render_text(report: ScanReport, events: Iterable[MotionEvent] | None = None) -> str:
    selected = list(report.events if events is None else events)
    requested = "ALL"
    if not report.requested_range.all:
        assert report.requested_range.start and report.requested_range.end
        requested = (
            f"{report.requested_range.start:%H:%M:%S} - {report.requested_range.end:%H:%M:%S}"
        )
    motion_seconds = sum(item.duration_seconds for item in selected)
    lines = [
        "CamReview Motion Report",
        f"Camera: {report.camera}",
        f"Date: {report.recording_date.isoformat()}",
        f"Requested range: {requested}",
        f"Status: {report.status}",
        "",
        f"Files scanned: {report.performance.files_processed:,}",
        f"Files skipped: {report.performance.files_skipped:,}",
        f"Video duration scanned: {_duration(report.performance.video_seconds)}",
        f"Video decoder: {report.performance.video_decoder or 'CPU'}",
        f"Motion events: {len(selected):,}",
        f"Total motion time: {_duration(motion_seconds)}",
        f"Scene changes suppressed: {report.scene_changes:,}",
        f"Missing/unprocessed intervals: {len(report.gaps):,}",
        "",
    ]
    if report.gaps:
        lines.append("MISSING / UNPROCESSED FOOTAGE")
        for gap in report.gaps:
            lines.append(f"{gap.start:%H:%M:%S} - {gap.end:%H:%M:%S}: {gap.reason}")
        lines.append("")
    if report.issues:
        lines.append("WARNINGS")
        for issue in report.issues:
            lines.append(f"{issue.file}: {issue.error}")
        lines.append("")
    lines.extend(["EVENTS", ""])
    for index, event in enumerate(selected, 1):
        lines.extend(
            [
                f"#{index:03d}  {event.id}",
                f"{event.start:%H:%M:%S.%f}"[:-3] + " - " + f"{event.end:%H:%M:%S.%f}"[:-3],
                f"Duration: {event.duration_seconds:.2f} sec",
                f"Classification: {_classification_text(event)}",
            ]
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def _duration(seconds: float) -> str:
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def render_csv(report: ScanReport, events: Iterable[MotionEvent] | None = None) -> str:
    import io

    selected = report.events if events is None else events
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "event_id",
            "camera",
            "start",
            "end",
            "duration_seconds",
            "categories",
            "raw_objects",
            "max_confidence",
        ],
    )
    writer.writeheader()
    for event in selected:
        classification = event.classification
        objects = classification.objects if classification else []
        writer.writerow(
            {
                "event_id": event.id,
                "camera": report.camera,
                "start": event.start.isoformat(timespec="milliseconds"),
                "end": event.end.isoformat(timespec="milliseconds"),
                "duration_seconds": round(event.duration_seconds, 3),
                "categories": ";".join(classification.categories) if classification else "",
                "raw_objects": ";".join(item.class_name for item in objects),
                "max_confidence": max((item.max_confidence for item in objects), default=""),
            }
        )
    return output.getvalue()


def write_reports(
    report: ScanReport,
    output_dir: Path,
    formats: set[str],
    *,
    stem: str | None = None,
    display_events: Iterable[MotionEvent] | None = None,
) -> dict[str, Path]:
    unknown = formats - {"json", "csv", "txt"}
    if unknown:
        raise ConfigurationError(f"Unknown report format(s): {', '.join(sorted(unknown))}")
    if "json" not in formats:
        raise ConfigurationError("JSON is canonical and cannot be disabled")
    stem = stem or f"{report.camera}_{report.recording_date.isoformat()}_motion"
    paths: dict[str, Path] = {}
    if "json" in formats:
        path = output_dir / f"{stem}.json"
        _atomic_write(path, json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n")
        paths["json"] = path
    if "csv" in formats:
        path = output_dir / f"{stem}.csv"
        _atomic_write(path, render_csv(report, display_events))
        paths["csv"] = path
    if "txt" in formats:
        path = output_dir / f"{stem}.txt"
        _atomic_write(path, render_text(report, display_events))
        paths["txt"] = path
    return paths


def load_report(path: Path) -> ScanReport:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Could not read report {path}: {exc}") from exc
    if value.get("schema_version") != 1:
        raise ConfigurationError(f"Unsupported report schema: {value.get('schema_version')!r}")
    requested = value.get("requested_range", {})
    settings_raw = value.get("settings", {})
    classification = settings_raw.get("classification", {})
    settings = ScanSettings(
        motion_fps=float(settings_raw.get("motion_fps", 4)),
        sensitivity=str(settings_raw.get("sensitivity", "medium")),
        min_motion_area=settings_raw.get("min_motion_area"),
        var_threshold=settings_raw.get("var_threshold"),
        trigger_frames=int(settings_raw.get("trigger_frames", 2)),
        quiet_seconds=float(settings_raw.get("quiet_seconds", 1.5)),
        merge_gap=float(settings_raw.get("merge_gap_seconds", 2)),
        reset_gap=float(settings_raw.get("reset_gap_seconds", 10)),
        warmup=float(settings_raw.get("warmup_seconds", 3)),
        pre_roll=float(settings_raw.get("pre_roll_seconds", 2)),
        post_roll=float(settings_raw.get("post_roll_seconds", 3)),
        scene_change_threshold=float(settings_raw.get("scene_change_threshold", 0.6)),
        analysis_width=int(settings_raw.get("analysis_width", 640)),
        hwdecode=str(settings_raw.get("hwdecode", "none")),
        classify=bool(classification.get("enabled", False)),
        classify_fps=float(classification.get("classify_fps", 2)),
        batch_size=int(classification.get("batch_size", 8)),
        model=str(classification.get("model", "yolo26n.pt")),
        device=str(classification.get("device", "auto")),
        confidence=float(classification.get("confidence", 0.35)),
        motion_object_overlap=float(classification.get("motion_object_overlap", 0.1)),
    )
    performance_raw = value.get("performance", {})
    summary = value.get("summary", {})
    performance = PerformanceStats(
        wall_seconds=float(performance_raw.get("wall_clock_seconds", 0)),
        video_seconds=float(
            performance_raw.get("video_seconds_analyzed", summary.get("seconds_scanned", 0))
        ),
        motion_frames=int(performance_raw.get("motion_frames_sampled", 0)),
        classification_frames=int(performance_raw.get("classification_frames_processed", 0)),
        files_processed=int(
            performance_raw.get("files_processed", summary.get("files_scanned", 0))
        ),
        files_skipped=int(performance_raw.get("files_skipped", summary.get("files_skipped", 0))),
        device=performance_raw.get("device"),
        video_decoder=performance_raw.get("video_decoder"),
    )
    return ScanReport(
        camera=str(value["camera"]),
        recording_date=date.fromisoformat(value["recording_date"]),
        source_root=Path(value["source_root"]),
        requested_range=TimeRange(
            datetime.fromisoformat(requested["start"]) if requested.get("start") else None,
            datetime.fromisoformat(requested["end"]) if requested.get("end") else None,
        ),
        settings=settings,
        events=[MotionEvent.from_dict(item) for item in value.get("events", [])],
        gaps=[
            TimelineGap(
                datetime.fromisoformat(item["start"]),
                datetime.fromisoformat(item["end"]),
                str(item.get("reason", "no footage available")),
            )
            for item in value.get("timeline_gaps", [])
        ],
        issues=[
            ProcessingIssue(
                file=str(item["file"]),
                error=str(item["error"]),
                expected_start=(
                    datetime.fromisoformat(item["expected_start"])
                    if item.get("expected_start")
                    else None
                ),
                kind=str(item.get("kind", "corrupt_or_unreadable")),
            )
            for item in value.get("issues", [])
        ],
        performance=performance,
        scene_changes=int(summary.get("scene_changes", 0)),
        status=str(value.get("run", {}).get("status", "complete")),
        created_at=datetime.fromisoformat(value.get("run", {}).get("created_at")),
    )
