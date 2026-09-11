# Troubleshooting

Start with `camreview inspect ROOT`. Add `--verbose` to a scan for decoder and model details,
and use `--strict` when diagnosis should stop at the first malformed or unreadable file.

## No recognized recording files were found

Confirm the directory exists, add `--recursive` if recordings are below it, and check names:

```text
<camera>_YYYY-MM-DD_HH-MM-SS.mkv
```

Supported extensions are MKV, MP4, MOV, and AVI, case-insensitively. Dates and times must be
real calendar/clock values. Filesystem timestamps are not a fallback.

## Multiple cameras or dates found

Discovery requires one camera-day. Run `inspect`, then add the printed selection:

```bash
camreview scan ROOT --recursive --camera garage --date 2026-08-12 --time all
```

For scheduled runs, `--date yesterday` is evaluated using the machine's local date.

## A file is skipped or appears as a gap

Read `issues` and `timeline_gaps` in JSON. In non-strict mode CamReview continues past
unrecognized, unsettled, inaccessible, corrupt, or unreadable files. Use `--strict` to make
these fatal. For a file still being written, increase `--settle-seconds`; `daily` already
defaults to 30 seconds.

For network storage, verify the task account's mount or share access. Prefer a UNC path in
Windows scheduled tasks because mapped drive letters may not exist in non-interactive
sessions. Brief retryable failures are handled automatically, but exhausted retries remain
explicit in the report.

## Motion is missed

Try changes in this order:

1. Confirm the requested time and filename timestamp are correct.
2. Raise `--motion-fps` to sample briefer movement.
3. Change `--sensitivity medium` to `high`.
4. Raise `--analysis-width` for small or distant subjects.
5. Lower `--trigger-frames`, `--min-motion-area`, or `--var-threshold` carefully.
6. Check that a supplied mask is white over the subject's path.

The first `warmup` seconds after startup, a resolution change, or a reset-sized gap are not
reported. Foreground ratios at `scene_change_threshold` or above are suppressed.

## Too many motion events

Prefer an ignore mask for repeat nuisance regions such as roads, timestamps, televisions,
trees, or curtains. Otherwise reduce `--motion-fps`, use `--sensitivity low`, lower
`--analysis-width`, increase `--trigger-frames`, or increase the area/variance thresholds.
Weather, shadows, insects, camera shake, lighting changes, and codec damage can all affect
background subtraction.

## Classification dependencies or CUDA are unavailable

Install the optional stack with `python -m pip install -e ".[detect]"`. Verify PyTorch:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

`--device auto` uses CPU if CUDA is absent. `--device cuda:0` intentionally returns exit 5
instead. Check that the PyTorch build, driver, GPU, and device index agree.

## A model cannot be loaded

Bare model names resolve to CamReview's local model cache and may need network access on the
first run. Check `CAMREVIEW_MODEL_DIR`, permissions, disk space, and the name. To avoid a
download, pass an existing directory-qualified path such as `--model ./models/yolo26n.pt`.

## Hardware decoding falls back or fails

Backend availability depends on OS, GPU, driver, PyAV/FFmpeg build, recording codec, and
frame-transfer support. `--hwdecode auto` warns and falls back to CPU. An explicit backend
returns exit 5; switch to `auto` for tested fallback or `none` for deterministic CPU decode.

## Event extraction fails

Event mode requires `ffmpeg` on `PATH`; run `ffmpeg -version` in the same environment as
CamReview. Confirm every `sources[].file` exists below the report's `source_root`, or pass
the relocated tree with `--source-root`. Accurate mode needs an FFmpeg build with H.264
encoding support. Fast mode also requires source streams that FFmpeg can concatenate.

Source mode does not require FFmpeg. It still needs write permission in the output directory
and read permission on every selected recording.

## A time or category option is rejected

Use either `--time START-END` or the pair `--from START --to END`, never both. The end must
be later on the same date; overnight ranges are not supported. Scan-time category filters
require `--classify`. Allowed categories are `person`, `pet`, `vehicle`, `animal`, `other`,
and `unknown`. JSON must remain in `--report-format`.

## Improve performance

Lower `--motion-fps` or `--analysis-width` to reduce CPU work. Hardware decode may help when
video decompression is the bottleneck, but motion processing remains on CPU. Classification
cost depends on event duration, `--classify-fps`, model size, device, and `--batch-size`.
Motion-only scanning on the storage server followed by classification on a GPU workstation
often gives the cleanest operational split.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Success; a non-strict report may still contain warnings |
| `1` | Unexpected application or internal CamReview error |
| `2` | No matching, overlapping, or readable recordings |
| `3` | Invalid or corrupt recording while strict mode is active |
| `4` | Invalid CLI/configuration combination or unsupported report input |
| `5` | Requested detector, model, CUDA device, or hardware decoder unavailable |
| `6` | FFmpeg or extraction failure |
| `130` | Interrupted with Ctrl+C; a scan report is marked `interrupted` |
