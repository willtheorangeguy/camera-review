# Command reference

CamReview's public interface is the `camreview` command. It exposes five subcommands and
returns stable process exit codes. Run `camreview COMMAND --help` for parser-generated help.

## Global options

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `-h`, `--help` | flag | off | Print command help and exit |
| `--version` | flag | off | Print the CamReview version and exit |

```bash
camreview --version
```

```text
CamReview 1.0.1
```

## `inspect`

`inspect` validates discovery, selection, and apparent timeline gaps without opening video
streams.

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `ROOT` | path | required | Directory searched for recordings |
| `--camera` | string | inferred | Camera prefix; required when more than one is present |
| `--date` | date | inferred | `YYYY-MM-DD` or `yesterday`; required for multiple dates |
| `--recursive` | flag | off | Search descendant directories |
| `--strict` | flag | off | Fail on an unrecognized or inaccessible video file |

```powershell
camreview inspect "D:\Cameras\garage" --recursive --camera garage --date 2026-08-12
```

## `scan`

`scan` discovers one camera-day, probes metadata, detects motion, writes reports, and can
classify or extract its events.

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `ROOT` | path | required | Directory searched for recordings |
| `--camera` | string | inferred | Camera prefix; required when more than one is present |
| `--date` | date | inferred | `YYYY-MM-DD` or `yesterday`; required for multiple dates |
| `--recursive` | flag | off | Search descendant directories |
| `--strict` | flag | off | Abort on malformed, inaccessible, or unreadable input |
| `--time` | range | `all` | `all` or `HH:MM[:SS]-HH:MM[:SS]` |
| `--from` | time | unset | Range start; requires `--to` and conflicts with `--time` |
| `--to` | time | unset | Range end; requires `--from` and conflicts with `--time` |
| `--settle-seconds` | nonnegative float | `0` | Skip files modified more recently than this many seconds |
| `--config` | path | `./camreview.toml` if present | TOML configuration file |
| `--motion-fps` | positive float | `4` | Samples decoded per second for motion analysis |
| `--sensitivity` | choice | `medium` | One of `low`, `medium`, or `high` |
| `--min-motion-area` | positive float | preset | Minimum contour area in analysis-frame pixels |
| `--var-threshold` | positive float | preset | MOG2 variance threshold |
| `--trigger-frames` | integer | `2` | Consecutive positive samples that open an event |
| `--quiet-seconds` | positive float | `1.5` | Quiet duration that closes an event |
| `--merge-gap` | nonnegative float | `2` | Maximum gap across which closed events merge |
| `--reset-gap` | nonnegative float | `10` | Timeline gap that resets event and background state |
| `--warmup` | nonnegative float | `3` | Unreported model-learning time after a reset |
| `--pre-roll` | nonnegative float | `2` | Context seconds before event extraction |
| `--post-roll` | nonnegative float | `3` | Context seconds after event extraction |
| `--scene-change-threshold` | float, 0–1 | `0.60` | Foreground ratio suppressed as a scene change |
| `--mask` | path | unset | Grayscale mask where white is analyzed and black ignored |
| `--analysis-width` | integer | `640` | Maximum width for motion analysis |
| `--hwdecode`, `--hardware-decode` | choice | `none` | `auto`, `none`, or a supported hardware backend |
| `--classify` | flag | off | Classify frames inside motion events |
| `--classify-fps` | positive float | `2` | Event samples per second for classification |
| `--batch-size` | integer | `8` | Maximum detector batch size |
| `--model` | string or path | `yolo26n.pt` | Ultralytics model name or path |
| `--device` | string | `auto` | PyTorch/Ultralytics device such as `cpu` or `cuda:0` |
| `--confidence` | float, 0–1 | `0.35` | Object detector confidence threshold |
| `--motion-object-overlap` | float, 0–1 | `0.10` | Object-box fraction that must overlap changed pixels |
| `--only` | category list | unset | Include categories in CSV, text, and extraction |
| `--exclude` | category list | unset | Exclude categories from CSV, text, and extraction |
| `--extract` | path | unset | Extract selected footage after reporting |
| `--extract-mode` | choice | `source` | `source` copies recordings; `event` makes event clips |
| `--extract-accuracy` | choice | `accurate` | `accurate` re-encodes; `fast` stream-copies |
| `--report-dir` | path | current directory | Report destination |
| `--report-format` | format list | `json,csv,txt` | Output formats; `json` is mandatory |
| `--quiet` | flag | off | Suppress progress and completion output |
| `--verbose` | flag | off | Enable debug logs; conflicts with `--quiet` |

Hardware backends are `cuda`, `d3d11va`, `d3d12va`, `dxva2`, `qsv`, `vaapi`,
`videotoolbox`, and `vdpau`. Categories are `person`, `pet`, `vehicle`, `animal`, `other`,
and `unknown`. Scan-time filters require `--classify`.

```powershell
camreview scan "D:\Cameras\garage" --recursive --date 2026-08-12 --time 08:00-12:00 --report-dir "D:\Reports\garage"
```

## `daily`

`daily` runs the `scan` pipeline with unattended defaults. It accepts every `scan` flag.
Only the settle default differs at parser level.

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `ROOT` | path | required | Directory searched for recordings |
| All `scan` selection flags | mixed | same as `scan` | Select one camera and date |
| All `scan` range flags | mixed | `all` | Defaults to the complete selected day |
| `--settle-seconds` | nonnegative float | `30` | Avoid a file that may still be open for writing |
| All `scan` processing flags | mixed | same as `scan` | Configure motion, decoding, and classification |
| All `scan` output flags | mixed | same as `scan` | Configure reports and extraction |

```bash
camreview daily /media/cameras/garage --recursive --date yesterday --report-dir /media/reports/garage --quiet
```

CamReview doesn't schedule this command. See [Nightly automation](deployment.md).

## `classify`

`classify` adds object classifications to an existing schema-version-1 JSON report. It
always writes JSON, CSV, and text using the selected output stem.

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `REPORT` | JSON path | required | Canonical CamReview report |
| `--source-root` | path | report value | Relocated recording root |
| `--output` | JSON path | `REPORT_STEM_classified.json` | Output stem and directory; conflicts with `--in-place` |
| `--in-place` | flag | off | Replace the input report; conflicts with `--output` |
| `--model` | string or path | report value | Ultralytics model name or path |
| `--device` | string | report value | Inference device such as `cpu` or `cuda:0` |
| `--confidence` | float, 0–1 | report value | Detection confidence threshold |
| `--classify-fps` | positive float | report value | Event samples per second |
| `--batch-size` | integer | report value | Maximum inference batch size |
| `--hwdecode`, `--hardware-decode` | choice | report value | Decoder backend |
| `--motion-object-overlap` | float, 0–1 | report value | Required object/motion overlap |
| `--only` | category list | unset | Filter CSV and text; JSON keeps every event |
| `--exclude` | category list | unset | Filter CSV and text; JSON keeps every event |
| `--strict` | flag | off | Abort when source footage is invalid or unreadable |

```powershell
camreview classify "D:\Reports\garage_2026-08-12_motion.json" --source-root "Z:\Cameras\garage" --device auto
```

## `extract`

`extract` reads a schema-version-1 JSON report and copies source recordings or creates one
MKV per selected event.

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `REPORT` | JSON path | required | Canonical or classified CamReview report |
| `--output` | path | required | Extraction destination |
| `--source-root` | path | report value | Relocated recording root |
| `--only` | category list | unset | Extract events matching any listed category |
| `--exclude` | category list | unset | Skip events matching any listed category |
| `--extract-mode` | choice | `source` | `source` or `event` |
| `--extract-accuracy` | choice | `accurate` | `accurate` or `fast`; used by event mode |
| `--pre-roll` | nonnegative float | report value | Context seconds before each event |
| `--post-roll` | nonnegative float | report value | Context seconds after each event |
| `--strict` | flag | off | Abort when source footage is invalid or unreadable |

```powershell
camreview extract "D:\Reports\garage_2026-08-12_motion_classified.json" --output "D:\Review" --only person,pet --extract-mode event
```

Event mode requires `ffmpeg` on `PATH`. Source mode copies recordings without invoking
FFmpeg. See [Usage](usage.md#filter-and-extract) for output behaviour.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Success; non-strict reports may contain warnings |
| `1` | Unexpected application or internal CamReview error |
| `2` | No matching, overlapping, or readable recordings |
| `3` | Invalid or corrupt recording in strict mode |
| `4` | Invalid CLI/configuration combination or report input |
| `5` | Requested detector, model, CUDA device, or decoder unavailable |
| `6` | FFmpeg or extraction failure |
| `130` | Interrupted with Ctrl+C |
