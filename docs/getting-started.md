# Getting started

<!-- markdownlint-disable MD046 -->

This walkthrough installs the motion-only application, checks a camera-day directory, and
creates its first JSON, CSV, and text reports.

## Prerequisites

| Requirement | Minimum version | Check with |
| --- | --- | --- |
| Python | 3.11 | `python --version` |
| Recording | MKV, MP4, MOV, or AVI | `camreview inspect D:\Cameras\garage\2026-08-12` |

Your recordings must use this filename form:

```text
<camera>_YYYY-MM-DD_HH-MM-SS.<extension>
garage_2026-08-12_08-00-00.mkv
```

Camera names may contain underscores. The filename timestamp is the authoritative local
start time; filesystem timestamps are ignored.

## Install

Create an isolated environment from the repository root and install the package:

=== "Windows"

    ```powershell
    py -3.12 -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install -e .
    ```

=== "macOS / Linux"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e .
    ```

See [Installation](installation.md) for the detection extra, development tools, upgrading,
and removal.

## First run

1. Verify the installed command.

    ```bash
    camreview --version
    ```

    ```text
    CamReview 1.0.0
    ```

2. Inspect filenames and inferred gaps without decoding video. Replace the path with a real
   camera-day directory.

    ```powershell
    camreview inspect "D:\Cameras\garage\2026-08-12"
    ```

    The output identifies one camera and date and ends with the detected extensions:

    ```text
    Detected camera: garage
    Detected date: 2026-08-12
    Video files: 1
    First: 08:00:00
    Last: 08:00:00
    Apparent missing intervals: 0
    Unrecognized filenames: 0
    Extensions: MKV
    ```

3. Scan the complete selected day.

    ```powershell
    camreview scan "D:\Cameras\garage\2026-08-12" --time all
    ```

    A successful run prints `Scan complete` followed by absolute paths to these files:

    ```text
    garage_2026-08-12_motion.json
    garage_2026-08-12_motion.csv
    garage_2026-08-12_motion.txt
    ```

## What happened

CamReview derived the recording timeline from filenames, probed video durations, sampled
frames through a persistent MOG2 background model, and grouped positive samples into events.
JSON preserves every event, timeline gap, warning, effective setting, and performance value.
CSV and text are review-oriented projections of the same run.

## Next steps

- [Usage](usage.md) selects ranges, classifies events, and extracts footage.
- [Configuration](configuration.md) tunes motion, decoding, models, and camera masks.
- [Command reference](api.md) lists every flag and default.
- [Nightly automation](deployment.md) runs one camera per scheduled process.
