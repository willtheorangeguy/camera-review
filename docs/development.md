# Development guide

## Set up a development environment

CamReview targets Python 3.11 and newer and uses Hatchling as its build backend. From the
repository root:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The development extra installs pytest, pytest-cov, Ruff, and mypy. Install `.[detect,dev]`
only when working on the real Ultralytics integration; ordinary tests use fakes and do not
need the model stack.

## Validate a change

Run the full configured test suite and static checks:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy camreview
```

The base development extra currently lacks the optional import packages needed for a clean
mypy run; this is tracked in the
[internal known-issues record](https://github.com/willtheorangeguy/camera-review/blob/HEAD/docs/internal/known-issues.md).
Pytest and both Ruff checks remain independently useful while that packaging decision is
unresolved.

Coverage can be collected with:

```bash
python -m pytest --cov=camreview --cov-report=term-missing
```

Integration tests are registered with the `integration` marker and create tiny synthetic
videos using local codecs. They do not download a model. Run only unit tests with
`python -m pytest -m "not integration"`, or only integration tests with
`python -m pytest -m integration`.

## Test organization

| Area | Tests |
| --- | --- |
| CLI and configuration | `test_cli.py`, `test_config.py` |
| Naming and time selection | `test_filenames.py`, `test_time_ranges.py` |
| Timeline continuity | `test_timeline_gaps.py`, `test_event_merging.py` |
| Decoding and network paths | `test_decoder.py`, `test_network_paths.py` |
| Classification | `test_category_mapping.py`, `test_classification.py` |
| Reports | `test_reports.py` |
| Real codec pipeline | `integration/test_motion_scan.py`, `integration/test_extraction.py` |

Tests that touch network behaviour simulate filesystem and decoder failures; they do not
require a real share. The decoder suite checks seek fallback, midstream retry without
duplicate samples, hardware selection, and safe CPU fallback.

## Design boundaries

New decoders implement `decoding.base.VideoDecoder`; new motion detectors implement
`motion.base.MotionDetector`; object detectors implement `detection.base.ObjectDetector`.
Keep command orchestration in `commands/` and serialization compatibility in `models.py` and
`reports/io.py`. The architecture and rationale are detailed in
[Architecture](./architecture.md).

When changing JSON, treat `schema_version` as a compatibility boundary. Both standalone
reprocessing commands load version 1 reports, so additions should remain readable or ship
with a deliberate version and migration decision. Update [Report schema](./schema.md) and
round-trip tests with any contract change.

## Contribution checklist

Before submitting a change:

1. Add focused unit coverage and an integration case when real codec behavior matters.
2. Preserve streaming iteration and bounded batches; do not accumulate day-long frame lists.
3. Keep source recordings immutable and output writes atomic.
4. Exercise strict and non-strict error paths for new recording failures.
5. Update command, configuration, and schema docs when public behavior changes.
6. Run pytest, Ruff lint, Ruff format check, and mypy.

Use the org-wide [Contributing Guide](https://github.com/willtheorangeguy/.github/blob/main/CONTRIBUTING.md)
and [Code of Conduct](https://github.com/willtheorangeguy/.github/blob/main/CODE_OF_CONDUCT.md).
