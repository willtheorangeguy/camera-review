# Roadmap and limitations

This page records limits and future directions already present in the project's design and
implementation. It is not a promise or release schedule.

## Detection and classification limits

Motion detection can react to shadows, weather, camera shake, insects, codec damage, and
lighting or infrared transitions. Sampling may miss events shorter than the sampling
interval, and every reset has a warm-up period. Results depend on camera placement, scene,
mask, sampling rate, analysis scale, and sensitivity settings.

Object detection can miss small, distant, blurred, or obscured subjects. It is limited to
classes known by the configured model. `unknown` indicates unclassified motion, not absence
of activity. Classification assigns broad categories and does not identify faces,
individual people, or individual pets.

## Time and extraction limits

Filename timestamps are timezone-naive local wall-clock values. Daylight-saving ambiguity
is not resolved, and a requested time range cannot cross midnight. Gaps can be inferred only
from available filename times and probed or estimated durations.

Fast stream-copy extraction is keyframe-inexact. Accurate extraction re-encodes video and
therefore costs time and changes the encoded stream. Event outputs contain video only in
accurate mode; source mode remains the path for preserving an original recording and audio.

## Hardware limits

A named hardware decoder can exist on a platform yet fail for a particular recording codec,
profile, driver, PyAV/FFmpeg build, or transfer path. Automatic mode safely falls back to
CPU. Hardware decoding does not move OpenCV motion processing to the GPU.

CUDA classification depends on a compatible NVIDIA driver, GPU, and PyTorch build. CPU
classification remains available but can be substantially slower.

## Deliberate non-goals

CamReview is intentionally not an NVR, live monitor, recorder, web UI, database, retention
manager, scheduler, or background daemon. It does not manage share credentials. It processes
one camera-day per invocation and expects the operating system to coordinate independent
jobs.

## Evidenced future directions

The project plan identifies two possible additions that are not implemented:

- A `benchmark` command for measuring representative video performance.
- A multi-camera command above the current one-camera-per-process workflow.

The decoder and detector interfaces also allow alternative implementations without changing
the command pipeline. Any such work should preserve streaming memory bounds, local-only
processing, source immutability, portable reports, and explicit recovery behavior.

## Actionable defects

Implementation defects found during documentation are kept separately in the
[internal known-issues record](https://github.com/willtheorangeguy/camera-review/blob/HEAD/docs/internal/known-issues.md)
so limitations and bugs are not conflated.
