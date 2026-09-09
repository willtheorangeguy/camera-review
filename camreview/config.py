from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any

from .errors import ConfigurationError
from .models import ScanSettings

ALIASES = {
    "merge_gap_seconds": "merge_gap",
    "reset_gap_seconds": "reset_gap",
    "warmup_seconds": "warmup",
    "pre_roll_seconds": "pre_roll",
    "post_roll_seconds": "post_roll",
}


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        default = Path("camreview.toml")
        if not default.is_file():
            return {}
        path = default
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Could not load config {path}: {exc}") from exc


def resolve_settings(
    config: dict[str, Any], camera: str, cli_values: dict[str, Any]
) -> ScanSettings:
    valid = {item.name for item in fields(ScanSettings)}
    merged: dict[str, Any] = {}
    for section in (
        config.get("defaults", {}),
        config.get("classification", {}),
        config.get("cameras", {}).get(camera, {}),
        cli_values,
    ):
        if not isinstance(section, dict):
            raise ConfigurationError("Configuration sections must be TOML tables")
        for key, value in section.items():
            normalized = ALIASES.get(key, key)
            if normalized in valid and value is not None:
                merged[normalized] = value
    if merged.get("mask") is not None:
        merged["mask"] = Path(merged["mask"])
    settings = ScanSettings(**merged)
    validate_settings(settings)
    return settings


def validate_settings(settings: ScanSettings) -> None:
    positive = {
        "motion_fps": settings.motion_fps,
        "trigger_frames": settings.trigger_frames,
        "quiet_seconds": settings.quiet_seconds,
        "analysis_width": settings.analysis_width,
        "classify_fps": settings.classify_fps,
        "batch_size": settings.batch_size,
    }
    for name, value in positive.items():
        if value <= 0:
            raise ConfigurationError(f"{name.replace('_', '-')} must be greater than zero")
    if settings.sensitivity not in {"low", "medium", "high"}:
        raise ConfigurationError("sensitivity must be low, medium, or high")
    if settings.hwdecode not in {"auto", "none", "cuda"}:
        raise ConfigurationError("hwdecode must be auto, none, or cuda")
    for name, value in {
        "scene_change_threshold": settings.scene_change_threshold,
        "confidence": settings.confidence,
        "motion_object_overlap": settings.motion_object_overlap,
    }.items():
        if not 0 <= value <= 1:
            raise ConfigurationError(f"{name.replace('_', '-')} must be between 0 and 1")
