from pathlib import Path

from camreview.config import resolve_settings


def test_config_precedence() -> None:
    config = {
        "defaults": {"motion_fps": 2, "sensitivity": "low"},
        "classification": {"confidence": 0.4},
        "cameras": {"upstairs": {"motion_fps": 6, "mask": "mask.png"}},
    }
    settings = resolve_settings(config, "upstairs", {"motion_fps": 8})
    assert settings.motion_fps == 8
    assert settings.sensitivity == "low"
    assert settings.confidence == 0.4
    assert settings.mask == Path("mask.png")
