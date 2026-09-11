# CamReview

Build a production-quality Python CLI application called **CamReview** for retrospectively analyzing security-camera recordings.

The application is NOT an NVR and must NOT run continuously. It processes existing video recordings on demand, produces motion-event reports, optionally classifies what caused the motion using an NVIDIA GPU, and optionally extracts the relevant video clips.

The primary use cases are:

1. Run manually on a Windows desktop with an AMD CPU and NVIDIA GPU to investigate a specific day/time range.
2. Run manually against an entire day.
3. Run automatically once per night on a Linux camera/storage server to create a simple list of every motion event for later review.
4. Optionally take an existing motion report later and classify or extract only those events.

The program must remain lightweight and stateless.

DO NOT add:

* PostgreSQL
* SQLite
* vector databases
* embeddings
* face recognition
* Ollama
* LLM descriptions
* web servers
* continuously running monitoring services
* cloud APIs

All video analysis must happen locally.

---

# 1. Recording format

Recordings are short video files, normally approximately one minute each.

Example:

```text
upstairs_2026-08-12_03-33-00.mkv
upstairs_2026-08-12_03-34-00.mkv
upstairs_2026-08-12_03-35-00.mkv
```

The filename is authoritative for the wall-clock starting timestamp.

Support at minimum:

```text
<camera>_YYYY-MM-DD_HH-MM-SS.mkv
```

Also support:

```text
.mp4
.mov
.avi
```

The camera name may contain underscores.

Therefore parse from the RIGHT side of the filename rather than splitting naively on underscores.

Example regex concept:

```regex
^(?P<camera>.+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})\.(?P<ext>mkv|mp4|mov|avi)$
```

Invalid filenames should not crash a run. Warn and skip them unless `--strict` is specified.

Sort recordings using the parsed datetime, never filesystem creation/modification time.

Absolute event timestamp:

```text
filename timestamp + timestamp/PTS within video
```

Example:

```text
File:
upstairs_2026-08-12_03-33-00.mkv

Motion begins 12.25 seconds into video.

Absolute timestamp:
2026-08-12 03:33:12.250
```

Keep the original local wall-clock time from the filename. Do not silently convert it to UTC.

---

# 2. Core CLI

Install a console command:

```text
camreview
```

Use Python's `argparse` unless there is a compelling reason for another dependency.

Primary commands:

```text
camreview scan
camreview daily
camreview classify
camreview extract
camreview inspect
```

`scan` is the main command.

---

# 3. Basic scan commands

Whole day:

```powershell
camreview scan "D:\Recordings\2026-08-12" --time all
```

Specific interval:

```powershell
camreview scan "D:\Recordings\2026-08-12" --time 08:00-12:00
```

Seconds should also work:

```powershell
camreview scan "D:\Recordings\2026-08-12" --time 08:15:30-10:42:15
```

Alternative explicit syntax should also be supported:

```powershell
camreview scan "D:\Recordings\2026-08-12" --from 08:00 --to 12:00
```

Do not permit contradictory combinations.

Examples:

```text
--time all
```

and:

```text
--from 08:00 --to 12:00
```

are valid.

Using both at once should produce a useful validation error.

---

# 4. Camera selection

Normally the directory should contain recordings for only one camera.

Automatically infer the camera name from filenames.

If several camera prefixes exist, print them and require:

```text
--camera upstairs
```

Support:

```text
--recursive
```

for situations where recordings are contained in subdirectories.

Example:

```powershell
camreview scan "D:\Recordings\2026-08-12" --camera upstairs --time all
```

---

# 5. Basic motion detection

The default operation should perform ONLY motion detection.

Example:

```powershell
camreview scan "D:\Recordings\2026-08-12" --time all
```

No AI model should load during this command unless `--classify` is supplied.

Use OpenCV BackgroundSubtractorMOG2 as the initial motion detector.

The design must allow replacing the motion detector later via an interface such as:

```python
class MotionDetector:
    def process_frame(...)
    def reset(...)
```

## Processing

For motion analysis:

1. Decode frames sequentially.
2. Downscale before motion processing.
3. Convert to grayscale.
4. Apply a small Gaussian blur.
5. Feed to MOG2.
6. Clean the foreground mask with morphology.
7. Find meaningful foreground regions.
8. Calculate:

   * total moving-pixel ratio
   * largest moving contour
   * bounding region(s)
9. Apply temporal debouncing.
10. Turn adjacent motion frames into motion EVENTS.

Do not treat every individual frame as an event.

---

# 6. Sampling

The motion detector does not need to analyze every source frame.

Default:

```text
--motion-fps 4
```

Meaning approximately four motion-analysis samples per second.

Make this configurable.

Examples:

```powershell
--motion-fps 2
--motion-fps 4
--motion-fps 8
```

Higher FPS:

* better sensitivity to very brief movement
* more CPU usage

Lower FPS:

* faster
* may miss extremely brief movement

The implementation must sample according to presentation timestamps/time rather than assuming all recordings have exactly the same source FPS.

Target timestamp accuracy should normally be within approximately one motion sampling interval.

---

# 7. Decoder architecture

Create a decoder abstraction rather than tightly coupling motion analysis to OpenCV VideoCapture.

For example:

```python
class VideoDecoder:
    def probe(...)
    def iter_frames(...)
```

Preferred initial decoder:

```text
PyAV / FFmpeg
```

Frames should expose:

```python
DecodedFrame(
    image,
    relative_seconds,
    absolute_datetime,
)
```

Use actual video PTS/time-base data when available.

Do not blindly calculate timestamp as:

```python
frame_number / assumed_fps
```

unless no usable timestamps exist.

Fall back gracefully if PTS information is malformed.

---

# 8. Optional hardware decoding

Do NOT make GPU video decoding a requirement for version 1.

The program must work correctly using CPU decoding.

However, architect the decoder so a future FFmpeg/NVDEC decoder can be added.

If practical without making the first implementation fragile, support:

```text
--hwdecode auto
--hwdecode none
--hwdecode cuda
```

But correctness is more important than implementing CUDA video decoding in the first release.

NVIDIA acceleration is essential for object detection, not necessarily for initial video decoding.

---

# 9. Motion detector continuity across files

This is critical.

The recordings are approximately one minute long but represent one continuous camera stream.

DO NOT reset MOG2 at every file.

When files are consecutive:

```text
03:33:00
03:34:00
03:35:00
```

preserve the background model between files.

Otherwise the beginning of every one-minute file may incorrectly appear as motion while MOG2 relearns the background.

Reset the motion model only if:

* camera changes
* resolution changes significantly
* there is a substantial recording gap
* explicitly requested

Add configurable:

```text
--reset-gap 10
```

meaning reset the background model when a gap larger than 10 seconds is discovered.

---

# 10. Warm-up

MOG2 needs an initial background-learning period.

Default:

```text
--warmup 3
```

seconds.

Do not report motion during initial warm-up.

If the requested search begins in the middle of existing footage:

```text
--time 14:00-15:00
```

attempt to decode several seconds immediately before 14:00 so the background model is already initialized when the requested interval begins.

Those warm-up frames MUST NOT be included in the report.

---

# 11. Motion sensitivity

Expose understandable tuning controls.

At minimum:

```text
--sensitivity low
--sensitivity medium
--sensitivity high
```

Default:

```text
medium
```

Internally these can map to parameters such as:

* minimum foreground area
* contour area
* foreground percentage
* number of consecutive frames
* MOG2 variance threshold

Also expose advanced overrides:

```text
--min-motion-area
--var-threshold
--trigger-frames
--quiet-seconds
```

Do not force ordinary users to use advanced parameters.

Document exactly what the three sensitivity presets mean.

---

# 12. Trigger and event debouncing

Motion should be grouped into useful time windows.

For example:

```text
03:33:12.250 motion begins
03:33:12.500 motion
03:33:12.750 motion
...
03:33:18.000 final motion
```

should result in ONE event:

```text
03:33:12.250 - 03:33:18.000
```

not dozens of events.

Default logic:

* require approximately 2 positive motion samples to begin an event
* keep the event alive through short quiet periods
* close after approximately 1.5 seconds without qualifying motion
* merge events separated by <= 2 seconds

Make configurable:

```text
--trigger-frames 2
--quiet-seconds 1.5
--merge-gap 2
```

Also store:

* maximum motion score
* average motion score
* maximum foreground ratio

---

# 13. Event pre-roll and post-roll

Reporting should preserve actual detected motion timestamps.

Extraction should optionally include additional context.

Defaults:

```text
--pre-roll 2
--post-roll 3
```

Example:

Detected:

```text
10:42:17 - 10:42:23
```

Extracted:

```text
10:42:15 - 10:42:26
```

But the report must still state that the actual detected event was:

```text
10:42:17 - 10:42:23
```

---

# 14. Scene-change protection

Security cameras can produce global changes from:

* IR mode switching
* lights turning on
* exposure changes
* reconnects
* corrupted frames
* camera shake

A sudden change covering most of the image should not automatically become a ten-minute "motion" event.

Implement a configurable global-scene-change threshold.

For example:

```text
--scene-change-threshold 0.60
```

If more than approximately 60% of the analyzed frame changes simultaneously:

* flag it as a possible scene change
* temporarily allow the background model to adapt
* do not blindly treat the entire image as meaningful movement

Include scene-change statistics/warnings in the report.

Do not discard subsequent localized motion.

---

# 15. Ignore masks

Support optional camera-specific masks for areas that should not contribute to motion.

Example:

```powershell
camreview scan ... --mask upstairs-mask.png
```

Mask image dimensions may differ from the analysis resolution; resize appropriately.

Typical masked areas:

* tree outside a window
* television
* timestamp overlay
* constantly moving curtain
* road visible through window

White/black semantics must be clearly documented.

Prefer:

```text
white = analyze
black = ignore
```

---

# 16. Report output

NO DATABASE.

Every scan creates a standalone report.

Canonical format:

```text
JSON
```

Also generate human-friendly:

```text
TXT
CSV
```

unless disabled.

Example default filenames:

```text
upstairs_2026-08-12_motion.json
upstairs_2026-08-12_motion.csv
upstairs_2026-08-12_motion.txt
```

Allow:

```text
--report-dir D:\CameraReports
```

and:

```text
--report-format json,csv,txt
```

JSON is canonical. CSV/TXT can be regenerated from it.

---

# 17. Human-readable report

Example TXT report:

```text
CamReview Motion Report
Camera: upstairs
Date: 2026-08-12
Requested range: ALL

Files scanned: 1,438
Video duration scanned: 23:57:42
Motion events: 37
Total motion time: 00:14:21

EVENTS

#001
03:33:12.250 - 03:33:19.750
Duration: 7.50 sec
Classification: not run
Source:
  upstairs_2026-08-12_03-33-00.mkv
  00:12.250 - 00:19.750

#002
04:17:51.000 - 04:18:04.250
Duration: 13.25 sec
Classification: not run
Sources:
  upstairs_2026-08-12_04-17-00.mkv
  upstairs_2026-08-12_04-18-00.mkv
```

Events MUST be allowed to span file boundaries.

---

# 18. Canonical JSON structure

Use a versioned schema.

Approximately:

```json
{
  "schema_version": 1,
  "camera": "upstairs",
  "recording_date": "2026-08-12",
  "source_root": "D:\\Recordings\\2026-08-12",
  "requested_range": {
    "start": null,
    "end": null,
    "all": true
  },
  "settings": {
    "motion_fps": 4,
    "sensitivity": "medium",
    "pre_roll_seconds": 2,
    "post_roll_seconds": 3
  },
  "summary": {
    "files_scanned": 1438,
    "seconds_scanned": 86262,
    "motion_events": 37,
    "motion_seconds": 861
  },
  "events": [
    {
      "id": "upstairs-20260812-033312-001",
      "start": "2026-08-12T03:33:12.250",
      "end": "2026-08-12T03:33:19.750",
      "duration_seconds": 7.5,
      "motion": {
        "max_score": 0.123,
        "mean_score": 0.052
      },
      "classification": null,
      "sources": [
        {
          "file": "upstairs_2026-08-12_03-33-00.mkv",
          "relative_start": 12.25,
          "relative_end": 19.75
        }
      ]
    }
  ]
}
```

Store source files RELATIVE to `source_root` whenever possible.

This makes reports portable between:

```text
Linux server:
 /media/recordings/...

Windows desktop:
 Z:\recordings\...
```

Commands consuming a report must allow:

```text
--source-root
```

to relocate the source tree.

---

# 19. CSV format

At minimum:

```text
event_id
camera
start
end
duration_seconds
categories
raw_objects
max_confidence
source_files
```

One row per event.

---

# 20. Console output

While running, print useful progress:

```text
Camera: upstairs
Date: 2026-08-12
Range: ALL
Files: 1438

[432/1438] 07:11:00  motion events: 11
```

At completion:

```text
Scan complete.

Files processed:      1438
Video scanned:        23h 57m 42s
Motion events:        37
Total motion:         14m 21s

Report:
D:\CameraReports\upstairs_2026-08-12_motion.txt
```

Do not spam one console line for every analyzed frame.

Support:

```text
--quiet
--verbose
```

---

# 21. Optional object classification

Classification is opt-in.

Example:

```powershell
camreview scan "D:\Recordings\2026-08-12" --time all --classify
```

When `--classify` is absent:

* do not import/load the detection model unnecessarily
* do not initialize CUDA
* do not download a model
* motion scanning must work with only the basic dependencies installed

When present, run object detection ONLY on motion-event frames.

Do not run YOLO across the full day.

---

# 22. Detector architecture

Define a clean detector interface:

```python
class ObjectDetector:
    def load(...)
    def detect(...)
    def close(...)
```

Implement an Ultralytics YOLO backend initially.

Default model should be a SMALL current pretrained COCO detection model appropriate at development time.

At the time this specification was written, a nano/small Ultralytics YOLO model is appropriate.

Make the exact model configurable:

```text
--model yolo26n.pt
```

or whatever current compatible default is selected during implementation.

Do not hard-wire the rest of the application to Ultralytics.

This should make it possible to add another ONNX/PyTorch detector later.

---

# 23. GPU selection

Default:

```text
--device auto
```

Behavior:

1. If NVIDIA CUDA is available, use it.
2. Otherwise fall back to CPU with a clear message.

Also support:

```text
--device cuda:0
--device cpu
```

If the user explicitly requests CUDA and it is unavailable, return an error rather than silently using CPU.

At startup with classification enabled, print:

```text
Object detector: YOLO ...
Device: NVIDIA GeForce ...
```

Do not require GPU support for ordinary motion-only scans.

---

# 24. Classification sampling

Default:

```text
--classify-fps 2
```

Only sample frames INSIDE motion events for object detection.

Do not necessarily classify every motion-analysis frame.

Batch GPU inference where practical.

Make batch size configurable:

```text
--batch-size 8
```

Avoid retaining an entire long event uncompressed in memory.

Use bounded batches.

---

# 25. Classification categories

The report should expose simple high-level categories.

Required categories:

```text
person
pet
vehicle
animal
other
unknown
```

Default raw-class mapping:

```text
person:
  person

pet:
  dog
  cat

vehicle:
  car
  truck
  bus
  motorcycle
  bicycle

animal:
  bird
  horse
  sheep
  cow
  elephant
  bear
  zebra
  giraffe
```

Exact classes should follow the detector's pretrained dataset.

Retain the original detector class too.

Example event:

```json
"classification": {
  "categories": ["person", "pet"],
  "objects": [
    {
      "class": "person",
      "category": "person",
      "hits": 7,
      "max_confidence": 0.91
    },
    {
      "class": "dog",
      "category": "pet",
      "hits": 5,
      "max_confidence": 0.87
    }
  ]
}
```

If motion exists but no relevant moving object can be identified:

```text
unknown
```

---

# 26. Important: classify the CAUSE of motion

Do NOT simply run YOLO on a frame and label the event with every object visible.

Example:

A parked car is always visible in the driveway.

A dog walks past.

YOLO sees:

```text
car
dog
```

The event should ideally be:

```text
pet / dog
```

not:

```text
vehicle + pet
```

because the car did not move.

Associate object detections with the motion mask.

For each detection bounding box:

1. Dilate the motion mask slightly.
2. Calculate overlap between the detection box and active foreground pixels.
3. Count the detection as causing/participating in the event only if motion overlaps it sufficiently.

Make threshold configurable:

```text
--motion-object-overlap 0.10
```

Alternative sensible heuristics are acceptable if well tested.

Store detections that overlap motion separately from merely visible objects.

The high-level classification should primarily use moving detections.

---

# 27. Classification confidence

Default:

```text
--confidence 0.35
```

Store:

* class
* high-level category
* number of frames detected
* maximum confidence
* mean confidence if useful

Avoid promoting a class into the final event category based solely on one extremely weak detection.

Implement a reasonable hit/confidence aggregation strategy.

Make it configurable where useful.

---

# 28. Unknown events

`unknown` is not an object-detector class.

An event becomes:

```text
unknown
```

when:

* real motion was detected
* classification was requested
* no accepted moving person/pet/vehicle/animal/etc. detection survived thresholds

Example causes:

* shadows
* insects near camera
* branches
* unrecognized object
* motion too blurry for detector
* lighting changes not rejected by scene-change logic

Do not discard unknown events.

They may be important.

---

# 29. Classification filters

Support output filtering after classification.

Example:

```powershell
camreview scan ... --classify --only person
```

Multiple categories:

```powershell
--only person,pet
```

Exclusions:

```powershell
--exclude vehicle
```

Filtering should affect console/report presentation and optional extraction as documented.

Prefer preserving the full canonical event data in JSON even when a display/extraction filter is used.

---

# 30. Extract clips

Support:

```powershell
camreview scan "D:\Recordings\2026-08-12" --time 12:00-14:00 --extract "D:\Review"
```

Two extraction modes are required.

## Mode 1: source

```text
--extract-mode source
```

This copies the ORIGINAL one-minute recording files containing motion.

No transcoding.

This should be the fastest/default mode.

Example output:

```text
D:\Review\
  upstairs_2026-08-12_12-14-00.mkv
  upstairs_2026-08-12_12-15-00.mkv
```

Never modify originals.

Do not copy the same source file repeatedly if several events occur in it.

## Mode 2: event

```text
--extract-mode event
```

Create one video around each detected event using:

```text
pre-roll + event + post-roll
```

Example filename:

```text
upstairs_2026-08-12_12-14-17_person_pet.mkv
```

If classification was not run:

```text
upstairs_2026-08-12_12-14-17_motion.mkv
```

Events spanning two one-minute source files should produce ONE logical extracted event if reasonably possible.

---

# 31. Accurate versus fast extraction

Support:

```text
--extract-accuracy accurate
--extract-accuracy fast
```

`accurate`:

* default for event extraction
* decode/re-encode as necessary
* start/end should closely match requested timestamps

On NVIDIA Windows desktop, optionally use NVENC when available.

CPU fallback should work using a broadly compatible codec such as H.264.

`fast`:

* allow FFmpeg stream copy
* document that cuts can start at nearby keyframes
* much faster and lossless

For `--extract-mode source`, simple filesystem copying should be used rather than FFmpeg.

---

# 32. Classification + extraction

Example:

```powershell
camreview scan "D:\Recordings\2026-08-12" `
    --time 15:00-18:00 `
    --classify `
    --only pet `
    --extract "D:\Review" `
    --extract-mode event
```

This should:

1. detect motion
2. classify motion
3. report all canonical motion data
4. select pet events
5. extract only matching pet events

---

# 33. Run classification later from a report

This is an important feature.

Nightly server scans may run motion detection only.

Later the desktop should be able to take that report and classify ONLY the previously detected events.

Example:

```powershell
camreview classify "upstairs_2026-08-12_motion.json"
```

If recordings are available at a different root:

```powershell
camreview classify "upstairs_2026-08-12_motion.json" `
    --source-root "Z:\Cameras\upstairs\2026-08-12"
```

This command must:

* read the JSON
* locate event source footage
* process only event windows
* run GPU detector
* add classifications
* write an updated JSON
* regenerate CSV/TXT

Default behavior should preserve the original report or make an atomic safe update.

Provide:

```text
--output
```

and optionally:

```text
--in-place
```

Do not risk corrupting the only report.

---

# 34. Run extraction later from a report

Example:

```powershell
camreview extract "upstairs_2026-08-12_motion.json" `
    --output "D:\Review"
```

Filter:

```powershell
camreview extract report.json `
    --only person `
    --output "D:\Review"
```

This avoids rescanning the day's footage.

---

# 35. Daily / nightly mode

Implement:

```text
camreview daily
```

This is intended for cron/systemd timers/Task Scheduler.

Example:

```bash
camreview daily /media/recordings/upstairs/2026-08-12 \
    --report-dir /media/camera-reports/upstairs
```

It should effectively perform:

```text
scan --time all
```

with behavior suitable for unattended execution.

Default daily behavior:

* motion detection only
* no object model
* no extracted clips
* write JSON + TXT + CSV
* noninteractive
* stable machine-readable logging
* sensible exit codes
* atomic report writes

It should determine camera/date from filenames.

If multiple dates exist, require a date selector rather than accidentally combining days.

Optionally support:

```text
--date 2026-08-12
```

and:

```text
--date yesterday
```

When parsing `yesterday`, use the local machine date.

---

# 36. Nightly file-settle protection

Do not analyze video files that are still actively being written.

Provide:

```text
--settle-seconds 30
```

Before processing a candidate file, ensure it has not been modified for at least that period.

For old/manual footage, this is irrelevant.

For nightly automation it prevents processing the final incomplete recording.

Skipped-unsettled files must appear in warnings/report metadata.

---

# 37. Idempotent daily operation

Running the same daily command twice should not create confusing duplicate reports.

Default report name is deterministic:

```text
upstairs_2026-08-12_motion.json
```

Write reports atomically:

```text
report.json.tmp
```

then replace/rename to:

```text
report.json
```

A crash must not leave a partially valid JSON report pretending to be complete.

Include run status:

```json
"run": {
    "status": "complete"
}
```

---

# 38. Configuration file

Support an optional TOML config:

```text
camreview.toml
```

Python 3.11+ `tomllib` can read it.

Example:

```toml
[defaults]
motion_fps = 4
sensitivity = "medium"
quiet_seconds = 1.5
merge_gap = 2.0
pre_roll = 2.0
post_roll = 3.0

[classification]
model = "yolo26n.pt"
confidence = 0.35
classify_fps = 2
device = "auto"

[cameras.upstairs]
mask = "masks/upstairs.png"
sensitivity = "medium"

[cameras.garage]
mask = "masks/garage.png"
sensitivity = "low"
```

Precedence:

```text
built-in defaults
    <
config defaults
    <
camera-specific config
    <
CLI arguments
```

CLI always wins.

---

# 39. Inspect command

Provide:

```powershell
camreview inspect "D:\Recordings\2026-08-12"
```

It should NOT process video.

It should print:

```text
Detected camera: upstairs
Detected date: 2026-08-12
Video files: 1,438
First: 00:00:00
Last: 23:59:00
Apparent missing intervals: ...
Unrecognized filenames: ...
Extensions: MKV
```

This is useful before launching a long scan.

---

# 40. Missing clips / gaps

Detect timeline gaps.

Example:

```text
10:41:00
10:42:00
10:45:00
```

Report:

```text
Possible recording gap: 10:43:00 - 10:45:00
```

Do NOT silently imply that "no motion" occurred during missing footage.

Canonical report must distinguish:

```text
no detected motion
```

from:

```text
no footage available
```

---

# 41. Corrupt videos

One corrupt MKV must not normally destroy a 24-hour scan.

Default:

* record error
* skip corrupt file
* continue
* finish report with warning
* report missing/unprocessed interval

With:

```text
--strict
```

abort immediately.

Record:

```text
file
exception/error
expected start
```

in JSON.

---

# 42. Ctrl+C and interruption

Handle Ctrl+C cleanly.

Do not leave:

* corrupted reports
* half-renamed extracted files
* orphan temporary files

Optionally write an explicitly marked partial report:

```json
"status": "interrupted"
```

but never confuse it with a complete daily report.

---

# 43. Exit codes

Define and document stable exit codes.

Suggested:

```text
0 = success
1 = unexpected application error
2 = no matching recordings
3 = recordings skipped/corrupt and strict mode failed
4 = invalid CLI/configuration
5 = requested detector/GPU unavailable
6 = FFmpeg/extraction failure
130 = interrupted where appropriate
```

For non-strict runs with a few corrupted clips, a completed report may still exit 0 but clearly include warnings.

Choose and document consistent semantics.

---

# 44. No giant temporary files

Do not extract the whole day's footage into intermediate formats.

Do not create frame dumps.

Do not save hundreds of thousands of JPEGs.

Frames should be processed in memory and discarded.

Temporary event-extraction files should be deleted after completion/failure.

Persistent artifacts should normally be only:

```text
JSON report
CSV report
TXT report
optional extracted video
```

---

# 45. Memory bounds

The application must handle a full 24-hour camera day without memory use growing with video duration.

Use:

* iterators/generators
* bounded frame buffers
* bounded classification batches

The event list can remain in memory because it should be comparatively small.

Never store every analyzed frame.

---

# 46. Performance statistics

Record useful timing information:

```text
wall-clock processing time
video duration analyzed
effective x realtime speed
motion frames sampled
classification frames processed
GPU/CPU device used
files processed
files skipped
```

Example:

```text
Analyzed 24h00m video in 31m18s
Effective speed: 46.0x realtime
```

Do not set an artificial performance requirement because hardware varies.

---

# 47. Optional benchmark command

If straightforward, provide:

```powershell
camreview benchmark some-video.mkv
```

Run approximately 60 seconds and print:

```text
decode speed
motion processing speed
YOLO FPS if installed
device
```

This is optional but useful.

---

# 48. Package architecture

Use a maintainable layout similar to:

```text
camreview/
    __init__.py
    __main__.py
    cli.py

    models.py
    config.py
    filenames.py
    timeline.py

    decoding/
        __init__.py
        base.py
        pyav_decoder.py

    motion/
        __init__.py
        base.py
        mog2.py
        events.py

    detection/
        __init__.py
        base.py
        ultralytics_detector.py
        categories.py

    reports/
        __init__.py
        json_report.py
        csv_report.py
        text_report.py

    extraction/
        __init__.py
        ffmpeg.py

    commands/
        scan.py
        daily.py
        classify.py
        extract.py
        inspect.py

tests/
    test_filenames.py
    test_time_ranges.py
    test_event_merging.py
    test_reports.py
    test_category_mapping.py
    test_timeline_gaps.py
    test_motion.py
    test_extraction.py
    integration/
```

Do not create abstractions solely for abstraction's sake, but keep decoder, motion detector, and object detector replaceable.

---

# 49. Python packaging

Use:

```text
pyproject.toml
```

Expose:

```toml
[project.scripts]
camreview = "camreview.cli:main"
```

Target:

```text
Python 3.11+
```

Prefer Python 3.12 during development for broad package compatibility.

Core dependencies should remain minimal.

Suggested core:

```text
numpy
opencv-python-headless
av
```

Classification optional dependencies:

```text
torch
ultralytics
```

Do not force a huge CUDA-enabled PyTorch install onto a Linux server that will only run motion detection.

Use optional extras, e.g.:

```bash
pip install -e .
pip install -e ".[detect]"
```

FFmpeg should be treated as an external executable and checked with:

```text
ffmpeg -version
ffprobe -version
```

where required.

---

# 50. Model download behavior

Do not unexpectedly download a model during a nightly motion-only job.

Classification commands may download the configured pretrained model if that is normal behavior for the detector library, but:

* tell the user clearly
* preferably provide a setup command or documentation to preload it
* permit a local explicit model path

Example:

```text
--model D:\Models\yolo26n.pt
```

---

# 51. Tests: filename parser

Test:

```text
upstairs_2026-08-12_03-33-00.mkv
living_room_2026-08-12_03-33-00.mkv
front_door_camera_2026-08-12_23-59-59.mkv
```

Ensure camera names with underscores work.

Test malformed names.

---

# 52. Tests: time filtering

Test:

```text
--time all
--time 03:00-04:00
--time 03:33:15-03:35:45
```

Ensure a file that starts before the requested interval but overlaps it is included.

Example:

```text
File starts: 03:33:00
Requested start: 03:33:30
```

The clip must be considered.

Motion before 03:33:30 may be used for detector warm-up but MUST NOT appear as an event.

---

# 53. Tests: cross-file event

Construct synthetic videos:

```text
clip 1:
motion 00:58 - 01:00

clip 2:
motion 00:00 - 00:03
```

Expected:

ONE event spanning:

```text
03:33:58 - 03:34:03
```

not two separate events.

---

# 54. Tests: no-motion video

Create a synthetic static video.

After warm-up:

```text
0 events
```

Small codec noise must not result in constant motion.

---

# 55. Tests: moving object

Create synthetic fixed-background footage containing a moving rectangle/object.

Expect:

* event start near known start
* event end near known end
* timestamps within expected tolerance determined by `motion_fps`

---

# 56. Tests: lighting change

Create:

```text
dark scene
instant full-frame brightness increase
static bright scene
```

Ensure the global scene-change logic can recover rather than reporting endless motion.

---

# 57. Tests: object classification

Use a small set of fixed test images/fixtures.

Verify category mappings:

```text
person -> person
dog -> pet
cat -> pet
car -> vehicle
truck -> vehicle
```

Verify no detections:

```text
unknown
```

Do not make automated tests download huge models unless specifically marked as integration tests.

---

# 58. Tests: static object should not cause category

Critical integration case:

```text
parked car remains visible
person walks through another portion of image
```

If motion-mask association is functioning, result should primarily identify:

```text
person
```

not automatically classify the event as caused by the static car.

---

# 59. FFmpeg wrapper tests

All FFmpeg calls must:

* use argument arrays
* never concatenate shell command strings
* properly handle paths containing spaces
* check exit code
* capture stderr
* generate useful error messages

Do not use:

```python
shell = True
```

unless there is an extremely compelling and documented reason.

---

# 60. Path portability

Use `pathlib.Path`.

Support:

```text
Windows local paths
Windows mapped drives
UNC paths
Linux paths
SMB mounts represented as filesystem paths
```

Do not assume `/` or `\`.

---

# 61. Example workflows to document

## Find all motion from a day

```powershell
camreview scan "D:\Cameras\upstairs\2026-08-12" --time all
```

## Search only morning footage

```powershell
camreview scan "D:\Cameras\upstairs\2026-08-12" --time 06:00-10:00
```

## Detect and classify

```powershell
camreview scan "D:\Cameras\upstairs\2026-08-12" `
    --time all `
    --classify
```

## Find pets only

```powershell
camreview scan "D:\Cameras\upstairs\2026-08-12" `
    --time 08:00-18:00 `
    --classify `
    --only pet
```

## Copy every original recording containing motion

```powershell
camreview scan "D:\Cameras\upstairs\2026-08-12" `
    --time all `
    --extract "D:\Review" `
    --extract-mode source
```

## Generate event-sized videos

```powershell
camreview scan "D:\Cameras\upstairs\2026-08-12" `
    --time all `
    --classify `
    --extract "D:\Review" `
    --extract-mode event
```

## Nightly Linux report

```bash
camreview daily "/media/recordings/upstairs/2026-08-12" \
    --report-dir "/media/reports/upstairs"
```

## Later GPU classification on desktop

```powershell
camreview classify "Z:\Reports\upstairs_2026-08-12_motion.json" `
    --source-root "Z:\Recordings\upstairs\2026-08-12"
```

## Later extract only pet activity

```powershell
camreview extract "Z:\Reports\upstairs_2026-08-12_motion.json" `
    --source-root "Z:\Recordings\upstairs\2026-08-12" `
    --only pet `
    --output "D:\Review\Dog"
```

---

# 62. Cron / Task Scheduler documentation

Do NOT implement a scheduling daemon.

Instead document how the ordinary `daily` command can be invoked by:

```text
cron
systemd timer
Windows Task Scheduler
```

The command itself must be suitable for unattended scheduling.

This keeps scheduling outside CamReview.

---

# 63. Four-camera usage

Do not require one process to manage every camera.

The expected server workflow may simply execute the program four times:

```text
camreview daily ...living...
camreview daily ...upstairs...
camreview daily ...basement...
camreview daily ...garage...
```

Each camera produces an independent report.

A future multi-camera command can be added later.

Do not make it necessary for version 1.

---

# 64. Privacy / network behavior

The program should not need internet access after required software/model files are installed.

No footage or frames should be uploaded.

No telemetry should be added by CamReview itself.

Document any third-party dependency behavior that may contact the network to retrieve models.

---

# 65. README

Create a detailed README containing:

1. purpose
2. screenshots are not necessary
3. architecture
4. Windows installation
5. Linux installation
6. FFmpeg requirement
7. basic motion-only installation
8. optional NVIDIA/YOLO installation
9. command reference
10. examples
11. sensitivity tuning
12. ignore-mask creation
13. classification categories
14. report format
15. extraction behavior
16. nightly automation examples
17. troubleshooting
18. performance tuning
19. CUDA verification
20. known limitations

---

# 66. Important known limitations to document

Explain that:

* motion detection may react to shadows/weather/camera shake
* object classification can miss small or obscured subjects
* "unknown" does not mean nothing happened
* filename timestamps are considered authoritative
* detection accuracy depends on sampling rate and sensitivity
* object detection does not identify individual people or individual pets
* event extraction using stream-copy may be keyframe-inexact
* exact trimming can require re-encoding

---

# 67. Development sequence

Implement in this order.

## Phase 1 — project and timeline

Implement:

* package
* CLI
* filename parsing
* directory scanning
* sorting
* time ranges
* gap detection
* inspect command
* unit tests

Do not proceed until tests pass.

## Phase 2 — decoder and motion detection

Implement:

* PyAV decoder
* timestamp propagation
* MOG2
* warm-up
* event trigger/quiet logic
* event merging
* file-boundary continuity
* synthetic integration tests

Do not proceed until tests pass.

## Phase 3 — reports

Implement:

* versioned JSON
* CSV
* TXT
* atomic writes
* summary statistics
* daily command

Do not proceed until tests pass.

At this point the application is already useful.

## Phase 4 — extraction

Implement:

* source-file copy mode
* FFmpeg exact event mode
* FFmpeg fast mode
* cross-file events
* pre/post roll
* tests

## Phase 5 — optional object detection

Implement:

* optional detection dependencies
* detector interface
* CUDA auto-selection
* YOLO backend
* event-only classification
* bounded batching
* category mapping
* motion-mask/detection overlap
* unknown category

## Phase 6 — report reprocessing

Implement:

```text
camreview classify report.json
camreview extract report.json
```

Ensure relative paths and `--source-root` work.

## Phase 7 — polish

Implement:

* configuration file
* masks
* progress output
* graceful interruption
* benchmark if worthwhile
* complete README
* lint/type-check/test setup

---

# 68. Quality requirements

Use:

* type hints throughout
* dataclasses where appropriate
* descriptive exceptions
* logging rather than arbitrary print calls internally
* pathlib
* subprocess safely
* atomic report writes
* dependency isolation

Add:

```text
pytest
ruff
```

A type checker such as:

```text
mypy
```

or:

```text
pyright
```

is encouraged.

Keep functions reasonably small.

Avoid giant god classes.

---

# 69. Dataclasses / domain models

Use typed domain structures similar to:

```python
RecordingFile
DecodedFrame
MotionSample
MotionEvent
SourceSegment
ObjectDetection
EventClassification
ScanReport
ScanSettings
```

Do not pass unstructured dictionaries through the core analysis pipeline.

Convert domain objects to JSON-friendly structures only in the report layer.

---

# 70. Acceptance criteria

Version 1 is complete when all of the following work.

### A

Given:

```text
upstairs_2026-08-12_03-33-00.mkv
```

and motion from second 14 through second 20:

the report gives approximately:

```text
03:33:14 - 03:33:20
```

### B

This works:

```powershell
camreview scan DAY --time all
```

and produces a full-day motion list.

### C

This works:

```powershell
camreview scan DAY --time 12:00-15:00
```

and does not report events outside that range.

### D

A motion event crossing from one one-minute MKV into the next appears as one event.

### E

This works without PyTorch/YOLO installed:

```powershell
camreview scan DAY --time all
```

### F

This uses the NVIDIA GPU when properly installed:

```powershell
camreview scan DAY --time all --classify
```

### G

Classification reports useful categories such as:

```text
person
pet / dog
vehicle / car
unknown
```

### H

This copies original source MKVs:

```powershell
--extract DIR --extract-mode source
```

### I

This creates event-sized recordings:

```powershell
--extract DIR --extract-mode event
```

### J

This produces an unattended daily report:

```text
camreview daily DAY
```

### K

This can classify a nightly motion report later without rescanning non-motion portions of the entire day:

```text
camreview classify report.json
```

### L

No database is created.

### M

No frames/video leave the local computer.

### N

Memory usage remains bounded during 24-hour processing.

### O

Corrupt/missing files are clearly represented rather than silently interpreted as periods with no motion.

---

# 71. Design priority

Prioritize in this order:

1. timestamp correctness
2. reliable motion-event detection
3. no false events at every one-minute file boundary
4. clear reports
5. robust handling of missing/corrupt footage
6. easy CLI
7. classification accuracy
8. extraction
9. performance optimization

Do NOT prematurely optimize or add a database.

A simple correct streaming implementation is preferable to a complicated architecture.

---

# 72. Final deliverable expected from Codex

Do not merely provide sample code or a skeleton.

Build the complete repository.

At the end:

1. run all tests
2. run linting
3. inspect failures
4. fix them
5. verify CLI help
6. create synthetic test footage and perform an end-to-end motion scan
7. if CUDA is available in the environment, test classification
8. otherwise ensure CPU/fallback paths are tested
9. provide a concise implementation summary
10. list exact installation and first-run commands

Do not stop after creating scaffolding.

If implementation reveals a reasonable technical detail not specified here, make a sensible engineering decision and document it rather than asking for minor clarification.
