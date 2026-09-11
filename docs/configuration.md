# Configuration

Configuration applies to `scan` and `daily`. Copy `camreview.example.toml` to
`camreview.toml` in the process working directory, or select another file with
`--config PATH`. The standalone `classify` and `extract` commands read settings from their
JSON report and accept their own overrides; they do not load TOML.

## Precedence and tables

Values are merged in this order, with later sources winning:

```text
built-in defaults < [defaults] and [classification] < [cameras.NAME] < CLI flags
```

The camera table name must exactly match the camera prefix selected from filenames.
Unknown keys are ignored. A setting may be placed in any of the three supported tables,
although keeping classification settings under `[classification]` makes intent clearer.

## CLI overrides

The scan commands expose every effective setting as a flag. A supplied flag replaces the
camera, classification, and defaults-table value for that run.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--config` | path | `./camreview.toml` if present | Example: `--config D:\CamReview\nightly.toml` |
| `--motion-fps` | float | config or `4` | Example: `--motion-fps 8` |
| `--sensitivity` | choice | config or `medium` | Example: `--sensitivity high` |
| `--min-motion-area` | float | config or preset | Example: `--min-motion-area 120` |
| `--var-threshold` | float | config or preset | Example: `--var-threshold 20` |
| `--trigger-frames` | integer | config or `2` | Example: `--trigger-frames 3` |
| `--quiet-seconds` | float | config or `1.5` | Example: `--quiet-seconds 2` |
| `--merge-gap` | float | config or `2` | Example: `--merge-gap 1` |
| `--reset-gap` | float | config or `10` | Example: `--reset-gap 15` |
| `--warmup` | float | config or `3` | Example: `--warmup 5` |
| `--pre-roll` | float | config or `2` | Example: `--pre-roll 4` |
| `--post-roll` | float | config or `3` | Example: `--post-roll 6` |
| `--scene-change-threshold` | float | config or `0.60` | Example: `--scene-change-threshold 0.55` |
| `--mask` | path | config or unset | Example: `--mask masks/garage.png` |
| `--analysis-width` | integer | config or `640` | Example: `--analysis-width 960` |
| `--hwdecode` | choice | config or `none` | Example: `--hwdecode auto` |
| `--classify` | flag | config or off | Enables classification for the run |
| `--classify-fps` | float | config or `2` | Example: `--classify-fps 3` |
| `--batch-size` | integer | config or `8` | Example: `--batch-size 16` |
| `--model` | string or path | config or `yolo26n.pt` | Example: `--model D:\Models\yolo26n.pt` |
| `--device` | string | config or `auto` | Example: `--device cuda:0` |
| `--confidence` | float | config or `0.35` | Example: `--confidence 0.45` |
| `--motion-object-overlap` | float | config or `0.10` | Example: `--motion-object-overlap 0.2` |

The [Command reference](api.md#scan) documents selection, report, filter, and extraction
flags that aren't TOML settings.

```toml
[defaults]
motion_fps = 4
sensitivity = "medium"
quiet_seconds = 1.5
merge_gap = 2.0
reset_gap = 10.0
warmup = 3.0
pre_roll = 2.0
post_roll = 3.0
scene_change_threshold = 0.60
hwdecode = "none"

[classification]
model = "yolo26n.pt"
confidence = 0.35
classify_fps = 2
batch_size = 8
device = "auto"

[cameras.upstairs]
mask = "masks/upstairs.png"
sensitivity = "medium"
```

Relative config and mask paths resolve from the process working directory, not from the
TOML file's directory. The aliases `merge_gap_seconds`, `reset_gap_seconds`,
`warmup_seconds`, `pre_roll_seconds`, and `post_roll_seconds` are also accepted.

## Motion settings

| Option | Type | Default | Description |
| --- | --- | ---: | --- |
| `motion_fps` | float | `4.0` | Positive samples per second; higher values catch briefer motion |
| `sensitivity` | string | `medium` | One of `low`, `medium`, or `high` |
| `min_motion_area` | float | unset | Positive contour area in analysis-frame pixels overriding the preset |
| `var_threshold` | float | unset | Positive MOG2 variance threshold overriding the preset |
| `trigger_frames` | integer | `2` | Positive count of consecutive motion samples needed to open an event |
| `quiet_seconds` | float | `1.5` | Positive quiet duration before an event closes |
| `merge_gap` | float | `2.0` | Nonnegative gap across which closed events merge |
| `reset_gap` | float | `10.0` | Nonnegative discontinuity that resets MOG2 and event state |
| `warmup` | float | `3.0` | Nonnegative time after a reset during which motion isn't reported |
| `scene_change_threshold` | float | `0.60` | Ratio from 0 through 1 suppressed as a scene change |
| `analysis_width` | integer | `640` | Positive maximum analysis width; smaller input isn't enlarged |
| `mask` | path | unset | Readable grayscale image; white is included and black excluded |
| `hwdecode` | string | `none` | `auto`, `none`, or a supported hardware backend |

At width 640, the built-in sensitivity presets are:

| Preset | Minimum changed ratio | Minimum contour | MOG2 variance threshold |
| --- | ---: | ---: | ---: |
| `low` | `0.008` | 500 px | 32 |
| `medium` | `0.003` | 180 px | 24 |
| `high` | `0.001` | 60 px | 16 |

`min_motion_area` controls the minimum individual contour size. The preset's changed-pixel
ratio still applies independently. Setting either override bypasses only that part of the
preset.

## Classification and extraction settings

| Option | Type | Default | Description |
| --- | --- | ---: | --- |
| `classify` | boolean | `false` | Enables classification after motion analysis |
| `classify_fps` | float | `2.0` | Positive event samples per second |
| `batch_size` | integer | `8` | Positive maximum detector batch size |
| `model` | string or path | `yolo26n.pt` | Bare model name or explicit filesystem path |
| `device` | string | `auto` | `auto`, `cpu`, `cuda`, `cuda:N`, or another supported device |
| `confidence` | float | `0.35` | Detector threshold from 0 through 1 |
| `motion_object_overlap` | float | `0.10` | Object-box overlap ratio from 0 through 1 |
| `pre_roll` | float | `2.0` | Nonnegative seconds added before event extraction |
| `post_roll` | float | `3.0` | Nonnegative seconds added after event extraction |

For accepted detections, CamReview prefers two observations but retains one strong hit when
its confidence is at least the greater of `0.65` and `confidence + 0.20`.

## Video decoding

`hwdecode = "none"` is deterministic CPU decoding. `auto` tests platform-appropriate
hardware backends against the first recording and falls back to CPU if none can decode and
transfer a BGR frame. Explicit backends fail if unavailable. Supported names are `cuda`,
`d3d11va`, `d3d12va`, `dxva2`, `qsv`, `vaapi`, `videotoolbox`, and `vdpau`.

Hardware decoding accelerates video decompression only. OpenCV motion analysis still needs
CPU-addressable frames. The active choice is written to `performance.video_decoder`.

## Environment variables

CamReview reads two environment variables. Their names are fixed rather than derived from
TOML keys.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `CAMREVIEW_MODEL_DIR` | path | platform cache | Directory for bare YOLO model names; for example `D:\Models\CamReview` |
| `XDG_CACHE_HOME` | path | `~/.cache` | Non-Windows cache root; for example `/var/cache/camreview-user` |

## Model storage

A bare name such as `yolo26n.pt` is resolved into a machine-local cache:

| Platform | Default directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\CamReview\models` |
| Linux and macOS | `${XDG_CACHE_HOME:-~/.cache}/camreview/models` |

Set `CAMREVIEW_MODEL_DIR` to replace that directory. An absolute or directory-qualified
model value is honored directly; for example, `--model ./models/yolo26n.pt` does not use the
central cache. If the resolved file is absent, Ultralytics may access the network to obtain
it. Preload weights before an offline run.

## Ignore-mask guidance

Build a mask from a representative frame. Paint regions to analyze white and nuisance areas
such as timestamps, televisions, roads, trees, or curtains black. Any image size is allowed;
CamReview resizes it to the analysis frame with nearest-neighbour interpolation and thresholds
values at 127. A completely black mask intentionally analyzes no pixels and cannot produce
ordinary motion events.

## Configuration troubleshooting

An unreadable file, malformed TOML, non-table section, invalid sensitivity, unknown hardware
backend, invalid probability, or invalid positive core setting exits with code `4`. Unknown
keys are ignored. Some numeric TOML fields currently lack the equivalent CLI validation; the
internal known-issues record tracks that discrepancy.
