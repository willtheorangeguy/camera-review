# Usage

## Recording layout

Pass either a directory containing recordings or, with `--recursive`, a parent directory.
Supported filenames are parsed from the right, so camera names may contain underscores:

```text
garage_2026-08-12_08-00-00.mkv
garage_2026-08-12_08-01-00.mkv
```

If discovery finds more than one camera or date, choose one with `--camera` and `--date`.
Use `--date yesterday` for unattended jobs. All timestamps remain naive local wall-clock
values; CamReview does not infer a timezone or resolve daylight-saving ambiguity.

## Inspect and scan

Inspect performs discovery and gap inference without opening the video streams:

```bash
camreview inspect /recordings/garage --recursive --camera garage --date 2026-08-12
```

Scan all selected footage or a closed time range:

```bash
camreview scan /recordings/garage --recursive --date 2026-08-12 --time all
camreview scan /recordings/garage --date 2026-08-12 --time 08:15:30-10:42:15
camreview scan /recordings/garage --date 2026-08-12 --from 08:00 --to 12:00
```

Do not combine `--time` with `--from` and `--to`. An overlapping file that starts before
the range may be decoded to warm the background model, but events outside the requested
range are not reported.

Choose output location and projections with:

```bash
camreview scan DAY --time all --report-dir /reports/garage --report-format json,txt
```

JSON is mandatory. Filtering with `--only` or `--exclude` affects CSV, text, and extraction,
while canonical JSON keeps every event.

## Tune motion detection

Start with `--sensitivity low`, `medium`, or `high`. At the default 640-pixel analysis width,
the presets change the minimum foreground ratio, contour size, and MOG2 variance threshold.
Use `--motion-fps 2` for speed or `--motion-fps 8` to improve sensitivity to brief motion.

For a persistent nuisance area, create a grayscale PNG and pass `--mask PATH`. White pixels
are analyzed, black pixels are ignored, and gray values are thresholded at 127. The mask is
resized to the analysis resolution with nearest-neighbour interpolation.

Advanced motion controls are listed in the [Command reference](api.md) and explained in
[Configuration](./configuration.md). Change one variable at a time and retain the JSON
settings block so results remain reproducible.

## Classify motion

After installing the `detect` extra, classify during a scan:

```bash
camreview scan DAY --time all --classify --device auto
```

CamReview first writes a recoverable motion-only checkpoint, then samples frames inside
events. A detection determines the category only when its box overlaps the frame-difference
motion mask; accepted static detections are retained separately as `visible_objects`.

To move classification to another computer, copy the JSON report and make the same source
tree available there:

```bash
camreview classify report.json --source-root /new/recording/root
```

The default output is `report_classified.json`, plus matching CSV and text files. Use
`--output NAME.json` or `--in-place`. Categories are `person`, `pet`, `vehicle`, `animal`,
`other`, and `unknown`; see [FAQ](./faq.md) for their meaning.

## Filter and extract

Filter classified, human-facing output or extraction with comma-separated categories:

```bash
camreview classify report.json --only person,pet
camreview extract report_classified.json --output /review --exclude vehicle
```

Source mode is the default. It atomically copies each original recording that contains a
selected event once and skips an existing destination with the same size:

```bash
camreview extract report.json --output /review --extract-mode source
```

Event mode makes one MKV per logical event and needs FFmpeg. Accurate mode re-encodes H.264;
fast mode uses stream copy and may start at a nearby keyframe:

```bash
camreview extract report.json --output /review --extract-mode event --extract-accuracy accurate
```

The default context is two seconds before and three seconds after motion. Cross-file events
remain one output clip. Original recordings are never modified.

## Network storage

Windows mapped drives, UNC paths, and mounted Linux SMB/CIFS paths work as normal paths:

```powershell
camreview scan "X:\living\2026-08-12" --time all
camreview scan "\\camera-nas\recordings\living\2026-08-12" --time all
```

Authentication and mounting are the operating system's responsibility. CamReview resolves
paths before handing them to native libraries, retries brief open/decode/share failures,
resumes sampling without duplicate frames, and writes destination-side temporary files
before atomic replacement. For nightly runs, continue to [Automation](./deployment.md).
