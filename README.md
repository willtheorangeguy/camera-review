<!-- Logo -->
<h1 align="center">CamReview</h1>

<!-- Tagline -->
<h4 align="center">A private, local CLI for finding and reviewing motion in existing security-camera recordings.</h4>

<!-- Badges -->
<div align="center">
  <img alt="GitHub Issues" src="https://img.shields.io/github/issues/willtheorangeguy/camera-review">
  <img alt="GitHub Pull Requests" src="https://img.shields.io/github/issues-pr/willtheorangeguy/camera-review">
  <img alt="License" src="https://img.shields.io/github/license/willtheorangeguy/camera-review">
</div>

<!-- Nav -->
<p align="center">
  <a href="#key-features">Key Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#support">Support</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#license">License</a>
</p>

CamReview retrospectively scans timestamped MKV, MP4, MOV, and AVI files, groups motion
into events, and writes portable JSON, CSV, and text reports. Classification and clip
extraction are opt-in. It is not an NVR, service, scheduler, web application, or database.

Footage and decoded frames remain on the local machine. CamReview has no telemetry and
uses no cloud API; Ultralytics may download a model only when classification is requested
and the configured model is not already cached.

## Key Features

* Preserves motion continuity across short recording files without loading a day into memory.
* Uses filename wall-clock times and presentation timestamps to build an accurate timeline.
* Supports local disks, Windows mapped drives and UNC paths, and mounted SMB/CIFS shares.
* Produces atomic, deterministic JSON, CSV, and text reports with gaps and processing issues.
* Optionally classifies moving COCO objects with Ultralytics YOLO on CPU or NVIDIA CUDA.
* Copies source recordings or creates event-sized clips with FFmpeg without changing originals.
* Offers CPU-first decoding plus tested automatic or explicit hardware-decoder selection.

## Installation

Python 3.11 or newer is required. From a clone of this repository:

```bash
python -m venv .venv
python -m pip install -e .
```

Activate the environment using the command for your shell. FFmpeg is additionally required
for event-sized extraction. See [Installation](docs/installation.md) for platform-specific
steps, optional classification dependencies, and verification.

## Usage

Recordings must use `<camera>_YYYY-MM-DD_HH-MM-SS.<ext>` filenames. Inspect a directory,
then scan one camera-day:

```bash
camreview inspect /path/to/recordings
camreview scan /path/to/recordings --time all
```

The current directory receives canonical `CAMERA_DATE_motion.json` plus CSV and text
reports. Start with [Getting started](docs/getting-started.md) for a complete first run.

## Documentation

Full documentation lives in [`docs/`](docs/index.md):
[Getting started](docs/getting-started.md) · [Installation](docs/installation.md) · [Usage](docs/usage.md) · [Command reference](docs/api.md) · [Configuration](docs/configuration.md) · [Architecture](docs/architecture.md) · [Report schema](docs/schema.md) · [Automation](docs/deployment.md) · [Troubleshooting](docs/troubleshooting.md)

## Support

File an [issue](https://github.com/willtheorangeguy/camera-review/issues/new/choose).

## Contributing

Contributions welcome. See the org-wide [Contributing Guide](https://github.com/willtheorangeguy/.github/blob/main/CONTRIBUTING.md) and [Code of Conduct](https://github.com/willtheorangeguy/.github/blob/main/CODE_OF_CONDUCT.md).

## License

MIT — see [`LICENSE.md`](LICENSE.md).
