# CamReview

CamReview is a stateless, local CLI for retrospectively reviewing security-camera
recordings. It scans existing short video files, groups motion into useful events, writes
portable JSON/CSV/TXT reports, and can optionally classify or extract only those events.
It is not an NVR, daemon, scheduler, web server, or database.

Footage and decoded frames remain on the local machine. CamReview has no telemetry and
uses no cloud API. A model may be downloaded by Ultralytics when classification is
explicitly requested and the configured model is not already cached.

## How it works

The timestamp in each filename is the authoritative local wall-clock start time:

```text
<camera>_YYYY-MM-DD_HH-MM-SS.mkv
living_room_2026-08-12_03-33-00.mp4
```

Camera names may contain underscores. MKV, MP4, MOV, and AVI are supported. PyAV/FFmpeg
decodes frames and supplies presentation timestamps (PTS); CamReview adds those offsets
to the filename time without converting to UTC.

The streaming pipeline is:

```text
filename timeline -> PTS-aware sampled decode -> downscaled MOG2 -> event debouncing
                  -> JSON/CSV/TXT -> optional event-only YOLO -> optional FFmpeg extract
```

The background model continues across consecutive one-minute files. It resets for a
large timeline gap or resolution change, so each file boundary does not become a false
event. Processing uses iterators and bounded classification batches; memory does not grow
with the duration of the recording set.

## Installation

Python 3.11 or newer and FFmpeg/ffprobe on `PATH` are required. Python 3.12 is
recommended.

### Windows

Install a current Python from python.org and FFmpeg using your preferred package manager,
then from this repository run:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
ffmpeg -version
ffprobe -version
camreview --help
```

### Linux

On Debian/Ubuntu, for example:

```bash
sudo apt update
sudo apt install -y python3-venv ffmpeg
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
camreview --help
```

The basic installation contains no PyTorch or YOLO dependency and never initializes
CUDA. It is suitable for a motion-only storage server.

### Optional classification and NVIDIA GPU

Install the detection extra only on systems that need object classification:

```powershell
pip install -e ".[detect]"
```

Install a PyTorch build matching the installed NVIDIA driver/CUDA environment according
to the PyTorch instructions. Verify it before a long run:

```powershell
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

`--device auto` selects `cuda:0` when CUDA is available and CPU otherwise. Explicit
`--device cuda:0` fails with exit code 5 when CUDA is unavailable. The default small COCO
model is `yolo26n.pt`; set a local path with `--model D:\Models\yolo26n.pt` to prevent a
download. Review Ultralytics' current dependency and model licensing for your use case.

## First run

Inspect filenames and gaps without decoding video:

```powershell
camreview inspect "D:\Cameras\upstairs\2026-08-12"
```

Scan the entire day using motion detection only:

```powershell
camreview scan "D:\Cameras\upstairs\2026-08-12" --time all
```

Use automatic hardware-accelerated video decoding when the machine supports it:

```powershell
camreview scan "D:\Cameras\upstairs\2026-08-12" --time all --hwdecode auto
```

By default, the current directory receives deterministic files such as:

```text
upstairs_2026-08-12_motion.json
upstairs_2026-08-12_motion.csv
upstairs_2026-08-12_motion.txt
```

JSON is always written because it is the canonical, versioned report. Choose the output
directory and companion formats with `--report-dir` and `--report-format json,txt`.

## SMB and network storage

CamReview supports Windows mapped drives, Windows UNC paths, and SMB/CIFS mounts exposed
as ordinary Linux filesystem paths:

```powershell
camreview scan "X:\living\2026-08-12" --time all
camreview scan "\\camera-nas\recordings\living\2026-08-12" --time all
```

```bash
camreview daily /mnt/cameras/living/2026-08-12 \
  --report-dir /mnt/cameras/living/2026-08-12
```

Authentication and mounting remain the operating system's responsibility. Recording paths
are canonicalized before they are passed to FFmpeg/PyAV, so a relative path under a Windows
mapped drive is decoded through its absolute UNC path. Brief SMB failures during open or
decoding are retried; a mid-stream retry resumes after the last emitted sample without
duplicating frames. Reports use destination-side temporary files and same-directory atomic
renames, and unsupported network `fsync` operations degrade safely. Source copying does not
require the share to permit timestamp changes. Fast concat extraction translates
drive-letter and UNC paths into explicit file URLs.

Bare YOLO model names are always cached on the local PC rather than beside footage on the
share: `%LOCALAPPDATA%\CamReview\models` on Windows or
`${XDG_CACHE_HOME:-~/.cache}/camreview/models` on Linux. Override the central directory
with `CAMREVIEW_MODEL_DIR`. A directory-qualified or absolute `--model PATH` is honored;
for example, use `--model .\yolo26n.pt` to explicitly select a current-directory file.

## Commands

### `scan`

```powershell
camreview scan DAY --time all
camreview scan DAY --time 08:00-12:00
camreview scan DAY --time 08:15:30-10:42:15
camreview scan DAY --from 08:00 --to 12:00
```

Do not combine `--time` with `--from/--to`. A file starting before the requested range is
included when it overlaps the range; earlier frames may warm the detector but cannot
appear in the report.

If more than one camera or date is present, select it explicitly:

```powershell
camreview scan DAY --camera upstairs --date 2026-08-12 --recursive --time all
```

Useful output controls are `--quiet`, `--verbose`, `--report-dir`, and
`--report-format`. `--strict` aborts on an invalid filename or unreadable video. Without
it, CamReview records the problem and missing/unprocessed interval in the report.

### `daily`

`daily` is an unattended `scan --time all`. It defaults to motion only, all three report
formats, no extraction, and `--settle-seconds 30` so the newest file is not read while it
is still being written.

```bash
camreview daily /media/recordings/upstairs/2026-08-12 \
  --report-dir /media/reports/upstairs
```

Use `--date yesterday` when one directory contains several days. Report names are
deterministic and writes are atomic, so rerunning the same date replaces the prior report
without creating duplicates. No scheduling daemon is included.

### `classify`

Classification is opt-in and runs only on frames inside previously detected motion
events:

```powershell
camreview scan DAY --time all --classify --device auto
camreview classify upstairs_2026-08-12_motion.json `
  --source-root "Z:\Cameras\upstairs\2026-08-12"
```

The second command is useful when a lightweight server creates a nightly report and a
GPU desktop classifies it later. It writes `*_classified.json/csv/txt` by default. Use
`--output result.json` or `--in-place`; all writes remain atomic.

Categories are:

- `person`: person
- `pet`: dog, cat
- `vehicle`: car, truck, bus, motorcycle, bicycle
- `animal`: bird, horse, sheep, cow, elephant, bear, zebra, giraffe
- `other`: another accepted moving COCO object
- `unknown`: motion occurred, but no accepted moving object was identified

CamReview dilates a frame-difference motion mask and requires overlap with a detected
object box. Static visible objects are retained separately in JSON as `visible_objects`
but do not normally determine the event category. Tune with `--motion-object-overlap`.

Filter human-facing CSV/TXT output and extraction with `--only person,pet` or
`--exclude vehicle`. Canonical JSON continues to preserve every motion event.

### `extract`

Extract during a scan or later from a report:

```powershell
camreview scan DAY --time all --extract "D:\Review" --extract-mode source
camreview extract report.json --output "D:\Review" --only pet
camreview extract report.json --output "D:\Review" `
  --extract-mode event --extract-accuracy accurate
```

`source` is the default and copies each original recording containing a selected event
once, without transcoding or modifying originals. `event` creates one MKV per event,
including the default two-second pre-roll and three-second post-roll. Cross-file events
remain one logical output.

Accurate extraction re-encodes H.264 and closely follows the requested timestamps. Fast
extraction uses stream copy and may start at a nearby keyframe. No large day-long
intermediate or frame dump is created.

## Motion tuning

The default sampling rate is four samples per second. `--motion-fps 2` is faster but may
miss very short movement; `--motion-fps 8` improves short-event sensitivity at higher CPU
cost.

## Hardware video decoding

CPU decoding remains the default. `--hwdecode auto` (also spelled
`--hardware-decode auto`) tests suitable backends for the current operating system and
codec, then uses the first backend that can both decode and transfer a frame for OpenCV.
If none work, automatic mode prints a warning and safely uses CPU decoding.

An explicit backend fails with exit code 5 instead of silently using the CPU:

```powershell
camreview scan DAY --time all --hwdecode cuda
camreview classify report.json --hwdecode cuda
```

Supported backend names are `cuda`, `d3d11va`, `d3d12va`, `dxva2`, `qsv`, `vaapi`,
`videotoolbox`, and `vdpau`. Actual availability depends on the operating system, GPU,
driver, FFmpeg/PyAV build, and recording codec. The selected decoder is printed at startup
and stored as `performance.video_decoder` in the JSON report. Hardware decoding only
offloads video decompression; OpenCV motion analysis still uses CPU-addressable frames.

Sensitivity presets at the default analysis scale are:

| Preset | Minimum changed ratio | Minimum contour | MOG2 variance threshold |
| --- | ---: | ---: | ---: |
| `low` | 0.8% | 500 px | 32 |
| `medium` | 0.3% | 180 px | 24 |
| `high` | 0.1% | 60 px | 16 |

The detector requires two positive samples to trigger, closes after 1.5 seconds of quiet,
and merges events separated by no more than two seconds. Advanced controls are:

```text
--min-motion-area --var-threshold --trigger-frames --quiet-seconds
--merge-gap --reset-gap --warmup --analysis-width
--scene-change-threshold
```

A foreground ratio at or above `--scene-change-threshold 0.60` is flagged and suppressed
as a likely exposure, lighting, IR, reconnect, or shake event while MOG2 adapts quickly.

### Ignore masks

Pass a PNG with `--mask upstairs-mask.png`. White pixels are analyzed and black pixels
are ignored. Gray values are thresholded at the midpoint. The mask is resized with
nearest-neighbor interpolation to match the analysis resolution, so it may be created
from a full-resolution screenshot. Paint transient subjects' normal paths white; paint
timestamps, televisions, roads, trees, or curtains black.

## Configuration

Copy `camreview.example.toml` to `camreview.toml`, or pass `--config PATH`. Precedence is:

```text
built-in defaults < config defaults < camera table < command-line arguments
```

The example includes `[defaults]`, `[classification]`, and `[cameras.NAME]` tables.
Relative paths are resolved from the process working directory.

## Report format

Schema version 1 JSON includes the source root, naive local requested range, full settings,
summary and performance statistics, events and source-relative spans, scene changes,
timeline gaps, skipped/corrupt-file issues, and `run.status`. Source paths are relative to
the scan root wherever possible, allowing a report created on Linux to be reprocessed from
a Windows mapped drive with `--source-root`.

CSV contains one event per row. TXT is intended for direct review. Report writes use a
temporary sibling, flush it, and atomically replace the destination. An interrupted scan
writes a JSON report marked `run.status = "interrupted"` and exits 130.

## Nightly automation

Cron example (run at 00:10 for the previous day):

```cron
10 0 * * * /opt/camreview/.venv/bin/camreview daily /media/cameras/upstairs --recursive --date yesterday --report-dir /media/reports/upstairs --quiet
```

A systemd service can use the same command as `ExecStart=` and be activated by an ordinary
calendar timer. In Windows Task Scheduler, create a daily task whose Program is
`C:\path\to\.venv\Scripts\camreview.exe` and whose arguments are, for example:

```text
daily D:\Cameras\upstairs --recursive --date yesterday --report-dir D:\Reports\upstairs --quiet
```

Run one independent command per camera. CamReview intentionally does not coordinate or
continuously monitor multiple cameras.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | success; non-strict warnings may still be present in the report |
| 1 | unexpected application error |
| 2 | no matching/readable recordings |
| 3 | invalid/corrupt recording while strict mode is active |
| 4 | invalid CLI or configuration combination |
| 5 | requested object detector or GPU unavailable |
| 6 | FFmpeg or extraction failure |
| 130 | interrupted by Ctrl+C |

## Troubleshooting and performance

- Run `camreview inspect DAY` first when camera/date inference fails.
- Confirm filenames match the documented pattern; filesystem timestamps are ignored.
- Run `ffmpeg -version` and `ffprobe -version` when extraction or decoding fails.
- Lower `--motion-fps` or `--analysis-width` for faster CPU scanning.
- Raise sensitivity only after trying an ignore mask; weather, trees, and shadows can
  otherwise create many events.
- Use `--verbose` for decoder/model details and `--strict` when diagnosing a bad clip.
- If classification falls back to CPU, verify `torch.cuda.is_available()` and ensure the
  installed PyTorch build, driver, and GPU are compatible.
- Preload a model with a short explicit classification run before an offline nightly job.

## Known limitations

- Motion detection can react to shadows, weather, camera shake, insects, or codec damage.
- Object detection can miss small, distant, blurred, or obscured subjects.
- `unknown` means the cause was not classified; it does not mean nothing happened.
- Filename timestamps are authoritative local wall-clock values; DST ambiguity is not
  resolved automatically.
- Accuracy depends on sampling rate, sensitivity, scene, and mask quality.
- Classification identifies COCO classes, not individual people, faces, or individual pets.
- Fast stream-copy extraction is keyframe-inexact; accurate cuts require re-encoding.
- Some hardware/codec combinations cannot transfer decoded frames to OpenCV; use
  `--hwdecode auto` for a tested fallback or `--hwdecode none` to force CPU decoding.

## Development

```powershell
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

Integration tests create tiny synthetic videos locally. They do not download a model.
