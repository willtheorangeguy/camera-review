# Report schema

JSON is CamReview's canonical, portable report. CSV and text are review-oriented projections
and may be filtered without removing events from JSON. All formats are written atomically
with deterministic names unless an explicit classified-output stem is supplied.

## File naming and compatibility

A scan writes `CAMERA_YYYY-MM-DD_motion.json`, `.csv`, and `.txt`. Standalone classification
writes `INPUT_STEM_classified.*` by default. `schema_version` is currently `1`; the
`classify` and `extract` commands reject any other version.

Paths in event source segments are relative to `source_root` wherever possible. Supply
`--source-root` when processing a report on a machine where the recording tree has moved.
Timestamps are ISO 8601 local wall-clock values with millisecond precision and no timezone
offset.

## Top-level JSON object

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Report contract version; currently `1` |
| `run` | object | `status` and report `created_at` timestamp |
| `camera` | string | Selected filename camera prefix |
| `recording_date` | date string | Selected local recording date |
| `source_root` | string | Recording root used for the run |
| `requested_range` | object | Requested `start`, `end`, and `all` flag |
| `settings` | object | Effective motion, decode, extraction, and classification settings |
| `summary` | object | Counts and durations for quick inspection |
| `performance` | object | Timing, sampling, decoder, device, and file statistics |
| `events` | array | Every canonical motion event, regardless of display filters |
| `timeline_gaps` | array | Missing or unprocessed time windows |
| `issues` | array | Per-file discovery or processing warnings |

`run.status` is `complete`, `motion_complete_classification_pending`, or `interrupted`.
The pending value identifies a recoverable checkpoint written before optional classification.

## Settings

The settings object records the effective values, not merely those supplied by the user:

```json
{
  "motion_fps": 4.0,
  "sensitivity": "medium",
  "min_motion_area": null,
  "var_threshold": null,
  "trigger_frames": 2,
  "quiet_seconds": 1.5,
  "merge_gap_seconds": 2.0,
  "reset_gap_seconds": 10.0,
  "warmup_seconds": 3.0,
  "pre_roll_seconds": 2.0,
  "post_roll_seconds": 3.0,
  "scene_change_threshold": 0.6,
  "mask": null,
  "analysis_width": 640,
  "hwdecode": "none",
  "classification": {
    "enabled": false,
    "classify_fps": 2.0,
    "batch_size": 8,
    "model": "yolo26n.pt",
    "device": "auto",
    "confidence": 0.35,
    "motion_object_overlap": 0.1
  }
}
```

## Summary and performance

`summary` contains `files_scanned`, `files_skipped`, `seconds_scanned`, `motion_events`,
`motion_seconds`, `scene_changes`, and `timeline_gaps`. Counts reflect the full JSON event
set, not filtered CSV or text views.

`performance` contains `wall_clock_seconds`, `video_seconds_analyzed`,
`effective_realtime_speed`, `motion_frames_sampled`, `classification_frames_processed`,
`device`, `video_decoder`, `files_processed`, and `files_skipped`. The effective speed is
video seconds divided by wall-clock seconds. `device` remains null when classification did
not run.

## Events

Each event has this shape:

```json
{
  "id": "garage-20260812-081530-001",
  "start": "2026-08-12T08:15:30.250",
  "end": "2026-08-12T08:15:36.500",
  "duration_seconds": 6.25,
  "motion": {
    "max_score": 0.035,
    "mean_score": 0.018,
    "max_foreground_ratio": 0.042
  },
  "classification": null,
  "sources": [
    {"file": "garage_2026-08-12_08-15-00.mkv", "relative_start": 30.25, "relative_end": 36.5}
  ]
}
```

`sources` may contain multiple entries when an event crosses file boundaries. Each segment
uses seconds relative to that source recording. Event IDs combine camera, event-start time,
and the event's sequence within the report.

After classification, `classification` contains sorted `categories`, accepted moving
`objects`, and accepted `visible_objects`. Each object records `class`, broad `category`,
`hits`, `max_confidence`, and `mean_confidence`. `visible_objects` can include objects that
did not overlap motion; `objects` contains only those that did. No accepted moving object
produces the category `unknown`.

## Gaps and issues

Each `timeline_gaps` entry contains `start`, `end`, `duration_seconds`, and a `reason` such
as no footage or failed processing. Overlapping gaps are normalized and their distinct
reasons are combined.

Each issue contains `file`, `error`, optional `expected_start`, and `kind`. Current kinds are
`unrecognized_filename`, `unsettled_file`, `corrupt_or_unreadable`, and
`network_or_filesystem_error`. Issues identify observed problems; gaps represent their time
impact where CamReview can estimate it.

## CSV projection

CSV has one row per displayed event with columns:

| Column | Meaning |
| --- | --- |
| `event_id` | Stable event identifier within this run |
| `camera` | Selected camera |
| `start`, `end` | ISO local timestamps with milliseconds |
| `duration_seconds` | Event duration |
| `categories` | Semicolon-separated broad categories |
| `raw_objects` | Semicolon-separated moving detector class names |
| `max_confidence` | Highest moving-object confidence, if classified |
| `source_files` | Semicolon-separated source segment filenames |

## Text projection

Text begins with run identity, status, summary statistics, missing/unprocessed intervals,
and warnings. Its event blocks show local times, duration, categories, and source-relative
spans. It is intended for reading, not round-trip processing; use JSON as machine input.
