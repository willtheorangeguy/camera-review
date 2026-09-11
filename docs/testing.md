# Testing

CamReview uses pytest for domain, command, filesystem, and codec-pipeline coverage. The
suite has unit tests plus integration tests that generate short local videos.

## Test stack

| Tool | Purpose |
| --- | --- |
| pytest 8 or newer | Test discovery, fixtures, assertions, and markers |
| pytest-cov 5 or newer | Optional coverage collection and terminal reports |
| OpenCV and NumPy | Synthetic moving-video fixtures and frame assertions |
| FFmpeg and PyAV | Integration coverage for real decoding and extraction |

## Running the tests

Install the development dependencies, then run the configured suite:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

The current suite reports:

```text
46 passed
```

The test count changes as coverage grows. A passing run exits `0`.

### Select one test

Use a node ID to isolate one behavior:

```bash
python -m pytest tests/test_filenames.py::test_malformed_filename_is_not_parsed -q
```

### Select by marker

Integration tests are registered under the `integration` marker:

```bash
python -m pytest -m integration -q
python -m pytest -m "not integration" -q
```

They create synthetic videos locally and don't download a classification model.

## Coverage

The project configures the coverage plugin but doesn't enforce a percentage threshold. Run:

```bash
python -m pytest --cov=camreview --cov-report=term-missing
```

Treat uncovered recovery branches as candidates for targeted tests rather than optimizing
only for the aggregate percentage.

## Test layout

```text
tests/
├── conftest.py                 Shared recording fixture
├── test_cli.py                 Exit-code behavior
├── test_config.py              Configuration precedence
├── test_decoder.py             PTS, retries, seeks, and hardware selection
├── test_event_merging.py       Trigger, quiet, merge, and continuity rules
├── test_filenames.py           Recording filename grammar
├── test_network_paths.py       Mapped paths and atomic share operations
├── test_reports.py             JSON round trips and projections
├── test_time_ranges.py         Range parsing and overlap
└── integration/
    ├── test_motion_scan.py     Synthetic end-to-end scans
    └── test_extraction.py      Source and event extraction
```

Additional unit files cover category mapping, classification overlap, and timeline gaps.

## Writing tests

Put deterministic domain behavior in a top-level `test_*.py` file. Use the `recording`
fixture from `conftest.py` for timestamped recording metadata. Stub decoder and detector
interfaces when exercising retries or classification; use `integration/` only when a real
codec boundary matters. Mark those cases with `@pytest.mark.integration`.

Never require network access or model downloads. Build tiny videos inside pytest's
`tmp_path`, and assert both the report data and the relevant progress or failure signal.
