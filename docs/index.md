# CamReview

CamReview is a local command-line tool for developers and camera operators who need to find
motion in existing security-camera recordings. It groups motion into reviewable events,
writes portable reports, and can classify or extract selected footage without running an
NVR, service, or database.

## Key features

- Scans timestamped MKV, MP4, MOV, and AVI recordings as a continuous timeline.
- Uses sampled, presentation-timestamp-aware decoding with bounded memory.
- Records motion events, missing intervals, file problems, settings, and performance.
- Writes canonical JSON plus CSV and text views through atomic replacement.
- Supports local disks, mapped drives, UNC paths, and mounted SMB/CIFS shares.
- Optionally classifies moving COCO objects with Ultralytics YOLO.
- Copies source recordings or creates event-sized clips without changing originals.

## Quick start

From a clone, install CamReview and scan one directory of correctly named recordings:

```bash
python -m pip install -e .
camreview scan /recordings/garage/2026-08-12 --time all
```

The current directory receives `garage_2026-08-12_motion.json`, `.csv`, and `.txt`. See
[Getting started](getting-started.md) for input naming, verification, and a complete first
run.

## Where to next

<div class="wt-grid" markdown>

[:material-rocket-launch: **Getting started**<br>Go from a clone to a motion report](getting-started.md){ .wt-card }

[:material-download: **Installation**<br>Set up the base, detection, or development dependencies](installation.md){ .wt-card }

[:material-console: **Command reference**<br>Look up commands, flags, defaults, and examples](api.md){ .wt-card }

[:material-tune: **Configuration**<br>Configure motion, decoding, classification, and masks](configuration.md){ .wt-card }

[:material-sitemap: **Architecture**<br>Follow the processing pipeline and code boundaries](architecture.md){ .wt-card }

[:material-file-document-outline: **Report schema**<br>Consume canonical JSON and its projections](schema.md){ .wt-card }

</div>

## Support

File a [GitHub issue](https://github.com/willtheorangeguy/camera-review/issues/new/choose)
with the command, exit code, relevant console output, and the `issues` section from the JSON
report. Do not attach private footage unless you intend to share it.
