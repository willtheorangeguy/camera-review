from pathlib import Path

import pytest

from camreview.filenames import parse_recording_filename


@pytest.mark.parametrize(
    ("name", "camera", "hour"),
    [
        ("upstairs_2026-08-12_03-33-00.mkv", "upstairs", 3),
        ("living_room_2026-08-12_03-33-00.mp4", "living_room", 3),
        ("front_door_camera_2026-08-12_23-59-59.MOV", "front_door_camera", 23),
    ],
)
def test_parse_from_right(name: str, camera: str, hour: int) -> None:
    parsed = parse_recording_filename(Path(name))
    assert parsed is not None
    assert parsed.camera == camera
    assert parsed.start.hour == hour


@pytest.mark.parametrize(
    "name",
    ["camera.mkv", "camera_2026-13-12_03-33-00.mkv", "camera_2026-08-12_3-33.mkv"],
)
def test_malformed_filename_is_not_parsed(name: str) -> None:
    assert parse_recording_filename(Path(name)) is None
