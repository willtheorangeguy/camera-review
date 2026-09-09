from __future__ import annotations

from pathlib import Path

from ..decoding import PyAVDecoder
from ..timeline import detect_gaps
from .common import prepare_recordings


def run_inspect(
    root: Path,
    *,
    camera: str | None,
    date: str | None,
    recursive: bool,
    strict: bool,
) -> None:
    recordings, selected_camera, selected_date, discovered, _ = prepare_recordings(
        root,
        PyAVDecoder(),
        recursive=recursive,
        settle_seconds=0,
        camera=camera,
        date_selector=date,
        strict=strict,
        probe=False,
    )
    gaps = detect_gaps(recordings)
    extensions = ", ".join(sorted({item.extension.upper() for item in recordings}))
    print(f"Detected camera: {selected_camera}")
    print(f"Detected date: {selected_date.isoformat()}")
    print(f"Video files: {len(recordings):,}")
    print(f"First: {recordings[0].start:%H:%M:%S}")
    print(f"Last: {recordings[-1].start:%H:%M:%S}")
    print(f"Apparent missing intervals: {len(gaps)}")
    for gap in gaps[:20]:
        print(f"  {gap.start:%H:%M:%S} - {gap.end:%H:%M:%S}")
    if len(gaps) > 20:
        print(f"  ... and {len(gaps) - 20} more")
    print(f"Unrecognized filenames: {len(discovered.unrecognized)}")
    for path in discovered.unrecognized[:10]:
        print(f"  {path.name}")
    if len(discovered.unrecognized) > 10:
        print(f"  ... and {len(discovered.unrecognized) - 10} more")
    print(f"Extensions: {extensions}")
