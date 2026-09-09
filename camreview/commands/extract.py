from __future__ import annotations

from pathlib import Path
from typing import Any

from ..decoding import PyAVDecoder
from ..extraction import extract_events, extract_source_files
from ..reports import load_report
from .common import filter_events, parse_categories, prepare_recordings


def run_extract(args: Any) -> list[Path]:
    report = load_report(args.report)
    source_root = args.source_root or report.source_root
    recordings, _, _, _, _ = prepare_recordings(
        source_root,
        PyAVDecoder(),
        recursive=True,
        settle_seconds=0,
        camera=report.camera,
        date_selector=report.recording_date.isoformat(),
        strict=args.strict,
        notify=lambda message: print(message, flush=True),
    )
    events = filter_events(
        report.events, parse_categories(args.only), parse_categories(args.exclude)
    )
    print(
        f"Extracting {len(events):,} selected event(s) in {args.extract_mode} mode...",
        flush=True,
    )
    if args.extract_mode == "source":
        return extract_source_files(
            events,
            recordings,
            args.output,
            notify=lambda message: print(message, flush=True),
        )
    return extract_events(
        report.camera,
        events,
        recordings,
        args.output,
        pre_roll=args.pre_roll if args.pre_roll is not None else report.settings.pre_roll,
        post_roll=args.post_roll if args.post_roll is not None else report.settings.post_roll,
        accuracy=args.extract_accuracy,
        notify=lambda message: print(message, flush=True),
    )
