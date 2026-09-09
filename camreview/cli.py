from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .commands.classify import run_classify
from .commands.extract import run_extract
from .commands.inspect import run_inspect
from .commands.scan import print_completion, request_from_args, run_scan
from .errors import (
    CamReviewError,
    ConfigurationError,
    DetectorUnavailableError,
    ExtractionError,
    NoRecordingsError,
    StrictRecordingError,
)

EXIT_UNEXPECTED = 1
EXIT_NO_RECORDINGS = 2
EXIT_STRICT_RECORDING = 3
EXIT_CONFIGURATION = 4
EXIT_DETECTOR = 5
EXIT_EXTRACTION = 6


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return parsed


def _probability(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def _add_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--camera", help="camera prefix when the directory contains multiple cameras"
    )
    parser.add_argument("--date", help="recording date (YYYY-MM-DD or yesterday)")
    parser.add_argument("--recursive", action="store_true", help="search subdirectories")
    parser.add_argument("--strict", action="store_true", help="abort on invalid or corrupt files")


def _add_scan_options(parser: argparse.ArgumentParser, *, daily: bool = False) -> None:
    _add_selection(parser)
    parser.add_argument("--time", dest="time_spec")
    parser.add_argument("--from", dest="from_time", help="range start (HH:MM[:SS])")
    parser.add_argument("--to", dest="to_time", help="range end (HH:MM[:SS])")
    parser.add_argument(
        "--settle-seconds",
        type=_nonnegative_float,
        default=30.0 if daily else 0.0,
        help="skip recently modified files (daily default: 30)",
    )
    parser.add_argument("--config", type=_path, help="TOML configuration file")
    parser.add_argument("--motion-fps", type=_positive_float, default=None)
    parser.add_argument("--sensitivity", choices=["low", "medium", "high"], default=None)
    parser.add_argument("--min-motion-area", type=_positive_float, default=None)
    parser.add_argument("--var-threshold", type=_positive_float, default=None)
    parser.add_argument("--trigger-frames", type=int, default=None)
    parser.add_argument("--quiet-seconds", type=_positive_float, default=None)
    parser.add_argument("--merge-gap", type=_nonnegative_float, default=None)
    parser.add_argument("--reset-gap", type=_nonnegative_float, default=None)
    parser.add_argument("--warmup", type=_nonnegative_float, default=None)
    parser.add_argument("--pre-roll", type=_nonnegative_float, default=None)
    parser.add_argument("--post-roll", type=_nonnegative_float, default=None)
    parser.add_argument("--scene-change-threshold", type=_probability, default=None)
    parser.add_argument("--mask", type=_path, default=None, help="white=analyze, black=ignore")
    parser.add_argument("--analysis-width", type=int, default=None)
    parser.add_argument("--hwdecode", choices=["auto", "none", "cuda"], default=None)
    parser.add_argument("--classify", action="store_true", default=None)
    parser.add_argument("--classify-fps", type=_positive_float, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--confidence", type=_probability, default=None)
    parser.add_argument("--motion-object-overlap", type=_probability, default=None)
    parser.add_argument("--only", help="comma-separated classification categories")
    parser.add_argument("--exclude", help="comma-separated classification categories")
    parser.add_argument("--extract", type=_path, help="optional extraction output directory")
    parser.add_argument("--extract-mode", choices=["source", "event"], default="source")
    parser.add_argument("--extract-accuracy", choices=["accurate", "fast"], default="accurate")
    parser.add_argument("--report-dir", type=_path)
    parser.add_argument("--report-format", default="json,csv,txt")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--quiet", action="store_true")
    output.add_argument("--verbose", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="camreview",
        description="Retrospectively find motion in local security-camera recordings.",
    )
    parser.add_argument("--version", action="version", version=f"CamReview {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="scan recordings for motion")
    scan.add_argument("root", type=_path)
    _add_scan_options(scan)

    daily = commands.add_parser("daily", help="run an unattended all-day motion scan")
    daily.add_argument("root", type=_path)
    _add_scan_options(daily, daily=True)

    classify = commands.add_parser("classify", help="classify events in an existing report")
    classify.add_argument("report", type=_path)
    classify.add_argument("--source-root", type=_path)
    classify.add_argument("--output", type=_path)
    classify.add_argument("--in-place", action="store_true")
    classify.add_argument("--model")
    classify.add_argument("--device")
    classify.add_argument("--confidence", type=_probability)
    classify.add_argument("--classify-fps", type=_positive_float)
    classify.add_argument("--batch-size", type=int)
    classify.add_argument("--motion-object-overlap", type=_probability)
    classify.add_argument("--only")
    classify.add_argument("--exclude")
    classify.add_argument("--strict", action="store_true")

    extract = commands.add_parser("extract", help="extract events from an existing report")
    extract.add_argument("report", type=_path)
    extract.add_argument("--source-root", type=_path)
    extract.add_argument("--output", type=_path, required=True)
    extract.add_argument("--only")
    extract.add_argument("--exclude")
    extract.add_argument("--extract-mode", choices=["source", "event"], default="source")
    extract.add_argument("--extract-accuracy", choices=["accurate", "fast"], default="accurate")
    extract.add_argument("--pre-roll", type=_nonnegative_float)
    extract.add_argument("--post-roll", type=_nonnegative_float)
    extract.add_argument("--strict", action="store_true")

    inspect = commands.add_parser("inspect", help="inspect filenames and timeline without decoding")
    inspect.add_argument("root", type=_path)
    _add_selection(inspect)
    return parser


def _validate_categories(args: argparse.Namespace) -> None:
    allowed = {"person", "pet", "vehicle", "animal", "other", "unknown"}
    for option in ("only", "exclude"):
        if not hasattr(args, option):
            continue
        values = {
            item.strip().casefold()
            for item in (getattr(args, option) or "").split(",")
            if item.strip()
        }
        unknown = values - allowed
        if unknown:
            raise ConfigurationError(
                f"--{option} contains unknown categories: {', '.join(sorted(unknown))}"
            )
    if getattr(args, "command", None) in {"scan", "daily"}:
        filtered = bool(getattr(args, "only", None) or getattr(args, "exclude", None))
        if filtered and not getattr(args, "classify", False):
            raise ConfigurationError("--only/--exclude require --classify during a scan")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    try:
        _validate_categories(args)
        if args.command in {"scan", "daily"}:
            report, paths, extracted = run_scan(request_from_args(args))
            if not args.quiet:
                print_completion(report, paths, extracted)
        elif args.command == "inspect":
            run_inspect(
                args.root,
                camera=args.camera,
                date=args.date,
                recursive=args.recursive,
                strict=args.strict,
            )
        elif args.command == "classify":
            output, device = run_classify(args)
            print(f"Classification complete ({device}): {output.resolve()}")
        elif args.command == "extract":
            created = run_extract(args)
            print(f"Extracted {len(created)} file(s) to {args.output.resolve()}")
        return 0
    except KeyboardInterrupt:
        print("Interrupted. Any partial report is explicitly marked interrupted.", file=sys.stderr)
        return 130
    except NoRecordingsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_NO_RECORDINGS
    except StrictRecordingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_STRICT_RECORDING
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIGURATION
    except DetectorUnavailableError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_DETECTOR
    except ExtractionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_EXTRACTION
    except CamReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED
    except Exception as exc:
        if getattr(args, "verbose", False):
            logging.exception("Unexpected application error")
        else:
            print(f"Unexpected error: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED


if __name__ == "__main__":
    raise SystemExit(main())
