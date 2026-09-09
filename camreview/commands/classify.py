from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import validate_settings
from ..decoding import PyAVDecoder
from ..detection import UltralyticsDetector, classify_events
from ..errors import ConfigurationError
from ..reports import load_report, write_reports
from .common import filter_events, parse_categories, prepare_recordings


def run_classify(args: Any) -> tuple[Path, str]:
    if args.in_place and args.output is not None:
        raise ConfigurationError("Use either --in-place or --output, not both")
    report = load_report(args.report)
    source_root = args.source_root or report.source_root
    decoder = PyAVDecoder()
    recordings, _, _, _, issues = prepare_recordings(
        source_root,
        decoder,
        recursive=True,
        settle_seconds=0,
        camera=report.camera,
        date_selector=report.recording_date.isoformat(),
        strict=args.strict,
        notify=lambda message: print(message, flush=True),
    )
    report.issues.extend(issues)
    settings = report.settings
    for name in (
        "model",
        "device",
        "confidence",
        "classify_fps",
        "batch_size",
        "motion_object_overlap",
    ):
        value = getattr(args, name)
        if value is not None:
            setattr(settings, name, value)
    settings.classify = True
    validate_settings(settings)
    detector = UltralyticsDetector(settings.model, settings.device, settings.confidence)
    classify_events(
        report.events,
        recordings,
        decoder,
        detector,
        settings,
        report.performance,
        notify=lambda message: print(message, flush=True),
    )
    report.source_root = source_root.resolve()
    report.created_at = datetime.now()
    if args.in_place:
        output = args.report
    elif args.output is not None:
        output = args.output
    else:
        output = args.report.with_name(f"{args.report.stem}_classified.json")
    if output.suffix.lower() != ".json":
        raise ConfigurationError("Classification output must be a .json file")
    selected = filter_events(
        report.events, parse_categories(args.only), parse_categories(args.exclude)
    )
    print(f"Writing classified reports to {output.parent.resolve()}...", flush=True)
    write_reports(
        report,
        output.parent,
        {"json", "csv", "txt"},
        stem=output.stem,
        display_events=selected,
    )
    return output, detector.device_name
