# CamReview — Known Issues

This internal record contains actionable implementation defects found while documenting the
project. It is separate from the reader-facing [roadmap](../roadmap.md).

## TOML numeric settings are not validated consistently

**Severity:** Medium

**Where:** `camreview/config.py`, `validate_settings()`

**What:** CLI parsers reject negative or zero values according to each option's contract,
but TOML values for `min_motion_area`, `var_threshold`, `merge_gap`, `reset_gap`, `warmup`,
`pre_roll`, and `post_roll` are not checked by `validate_settings()`.

**Why it matters:** A configuration file can accept values the equivalent CLI flag rejects.
A negative contour threshold can produce misleading events, while negative timing or
extraction values can change event continuity or generate invalid clip windows without a
clear configuration error.

**Suggested fix:** Extend `validate_settings()` with positive checks for optional motion
threshold overrides and nonnegative checks for gap, warm-up, and roll durations. Keep CLI
and TOML validation covered by parameterized tests; decide separately whether zero is valid
for each threshold override.

## The documented base development environment cannot complete mypy

**Severity:** Low

**Where:** `pyproject.toml`, the `dev` optional dependency group and mypy configuration

**What:** The documented `pip install -e ".[dev]"` environment omits `torch` and
`ultralytics`, but mypy follows their imports in `ultralytics_detector.py` and reports both
as missing. On Python 3.14, NumPy's installed stubs also use syntax newer than the configured
`python_version = "3.11"` target.

**Why it matters:** A contributor following the repository's complete static-check workflow
cannot get a clean mypy result from the advertised development installation, making it
unclear whether later type errors are regressions or environment noise.

**Suggested fix:** Decide whether typing should install the detection extra, exclude or
conditionally type optional vendor imports, or use missing-import overrides. Test mypy on
the supported Python matrix and constrain dependencies if their stubs no longer parse for
the configured target.
