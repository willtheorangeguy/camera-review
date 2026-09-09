from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from ..errors import ExtractionError
from ..filesystem import atomic_copy
from ..models import MotionEvent, RecordingFile
from ..timeline import source_segments_for_window


def _ensure_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise ExtractionError("FFmpeg was not found on PATH")
    return executable


def _lookup(recordings: list[RecordingFile]) -> dict[str, RecordingFile]:
    result: dict[str, RecordingFile] = {}
    for recording in recordings:
        result[recording.relative_path] = recording
        result[recording.path.name] = recording
    return result


def extract_source_files(
    events: list[MotionEvent],
    recordings: list[RecordingFile],
    output: Path,
    *,
    notify: Callable[[str], None] | None = None,
) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    lookup = _lookup(recordings)
    sources = {source.file for event in events for source in event.sources}
    created: list[Path] = []
    ordered_sources = sorted(sources)
    for index, source in enumerate(ordered_sources, 1):
        if notify:
            notify(f"[extract {index:,}/{len(ordered_sources):,}] Copying {source}")
        recording = lookup.get(source)
        if recording is None or not recording.path.is_file():
            raise ExtractionError(f"Source recording is missing: {source}")
        destination = output / recording.path.name
        if destination.is_file() and destination.stat().st_size == recording.path.stat().st_size:
            created.append(destination)
            continue
        atomic_copy(recording.path, destination)
        created.append(destination)
    return created


def _event_name(camera: str, event: MotionEvent) -> str:
    categories = event.classification.categories if event.classification is not None else ["motion"]
    label = "_".join(item for item in categories if item) or "unknown"
    sequence = event.id.rsplit("-", maxsplit=1)[-1]
    return f"{camera}_{event.start:%Y-%m-%d_%H-%M-%S}_{label}_{sequence}.mkv"


def _run(arguments: list[str], output: Path) -> None:
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        output.unlink(missing_ok=True)
        detail = result.stderr.strip().splitlines()
        message = detail[-1] if detail else f"exit code {result.returncode}"
        raise ExtractionError(f"FFmpeg failed creating {output.name}: {message}")


def _ffmpeg_file_url(path: Path) -> str:
    value = path.as_posix()
    if value.startswith("//"):
        return f"file:{value}"
    if len(value) >= 3 and value[1] == ":" and value[2] == "/":
        return f"file:{value}"
    return value


def _manifest_line(path: Path) -> str:
    # FFmpeg concat quoting: embedded apostrophes terminate and restart the quote.
    escaped = _ffmpeg_file_url(path.resolve()).replace("'", "'\\''")
    return f"file '{escaped}'\n"


def _extract_fast(
    ffmpeg: str,
    source_paths: list[Path],
    offset: float,
    duration: float,
    temporary_output: Path,
    work: Path,
) -> None:
    manifest = work / "sources.txt"
    manifest.write_text("".join(_manifest_line(path) for path in source_paths), encoding="utf-8")
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest),
            "-ss",
            f"{offset:.6f}",
            "-t",
            f"{duration:.6f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c",
            "copy",
            "-y",
            str(temporary_output),
        ],
        temporary_output,
    )


def _extract_accurate(
    ffmpeg: str,
    paths_and_spans: list[tuple[Path, float, float]],
    temporary_output: Path,
) -> None:
    arguments = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    for path, start, end in paths_and_spans:
        arguments.extend(["-ss", f"{start:.6f}", "-to", f"{end:.6f}", "-i", str(path)])
    if len(paths_and_spans) == 1:
        arguments.extend(["-map", "0:v:0"])
    else:
        inputs = "".join(f"[{index}:v:0]" for index in range(len(paths_and_spans)))
        arguments.extend(
            [
                "-filter_complex",
                f"{inputs}concat=n={len(paths_and_spans)}:v=1:a=0[outv]",
                "-map",
                "[outv]",
            ]
        )
    arguments.extend(
        [
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-y",
            str(temporary_output),
        ]
    )
    _run(arguments, temporary_output)


def extract_events(
    camera: str,
    events: list[MotionEvent],
    recordings: list[RecordingFile],
    output: Path,
    *,
    pre_roll: float,
    post_roll: float,
    accuracy: str,
    notify: Callable[[str], None] | None = None,
) -> list[Path]:
    ffmpeg = _ensure_ffmpeg()
    output.mkdir(parents=True, exist_ok=True)
    lookup = _lookup(recordings)
    created: list[Path] = []
    for index, event in enumerate(events, 1):
        if notify:
            notify(f"[extract {index:,}/{len(events):,}] Creating clip for {event.id} ({accuracy})")
        start = event.start - timedelta(seconds=pre_roll)
        end = event.end + timedelta(seconds=post_roll)
        segments = source_segments_for_window(recordings, start, end)
        if not segments:
            raise ExtractionError(f"No source footage overlaps event {event.id}")
        paths_and_spans: list[tuple[Path, float, float]] = []
        for segment in segments:
            recording = lookup.get(segment.file)
            if recording is None or not recording.path.is_file():
                raise ExtractionError(f"Source recording is missing: {segment.file}")
            paths_and_spans.append((recording.path, segment.relative_start, segment.relative_end))
        destination = output / _event_name(camera, event)
        with tempfile.TemporaryDirectory(prefix="camreview-") as directory:
            work = Path(directory)
            temporary = work / destination.name
            if accuracy == "fast":
                first_recording = lookup[segments[0].file]
                offset = max(0.0, (start - first_recording.start).total_seconds())
                _extract_fast(
                    ffmpeg,
                    [item[0] for item in paths_and_spans],
                    offset,
                    max(0.001, (end - start).total_seconds()),
                    temporary,
                    work,
                )
            else:
                _extract_accurate(ffmpeg, paths_and_spans, temporary)
            atomic_copy(temporary, destination)
        created.append(destination)
    return created
