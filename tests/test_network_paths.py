from __future__ import annotations

import errno
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

from camreview import filesystem
from camreview.detection.ultralytics_detector import UltralyticsDetector
from camreview.extraction.ffmpeg import _ffmpeg_file_url
from camreview.timeline import discover_recordings


def test_ffmpeg_urls_cover_mapped_unc_and_linux_paths() -> None:
    assert (
        _ffmpeg_file_url(PureWindowsPath("X:/living/2026-08-12/clip.mkv"))
        == "file:X:/living/2026-08-12/clip.mkv"
    )
    assert (
        _ffmpeg_file_url(PureWindowsPath("//nas/cameras/living/clip.mkv"))
        == "file://nas/cameras/living/clip.mkv"
    )
    assert (
        _ffmpeg_file_url(PurePosixPath("/mnt/cameras/living/clip.mkv"))
        == "/mnt/cameras/living/clip.mkv"
    )


def test_discovery_canonicalizes_relative_recording_paths(tmp_path: Path, monkeypatch) -> None:
    recording = tmp_path / "living_2026-08-12_03-33-00.mkv"
    recording.touch()
    monkeypatch.chdir(tmp_path.parent)
    result = discover_recordings(Path(tmp_path.name))
    assert result.recordings[0].path == recording.resolve()
    assert result.recordings[0].source_root == tmp_path.resolve()
    assert result.recordings[0].relative_path == recording.name


def test_atomic_replace_retries_transient_share_error(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "report.tmp"
    destination = tmp_path / "report.json"
    source.write_text("complete", encoding="utf-8")
    real_replace = os.replace
    attempts = 0

    def flaky_replace(first, second) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError(errno.EACCES, "share temporarily busy")
        real_replace(first, second)

    monkeypatch.setattr(filesystem.os, "replace", flaky_replace)
    monkeypatch.setattr(filesystem.time, "sleep", lambda _: None)
    filesystem.atomic_replace(source, destination)
    assert attempts == 2
    assert destination.read_text(encoding="utf-8") == "complete"


def test_default_model_uses_local_cache_not_recording_directory(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "yolo26n.pt").write_bytes(b"existing working-directory model")
    cache = tmp_path / "local-cache"
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(cache))
        expected = cache / "CamReview" / "models" / "yolo26n.pt"
    else:
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
        expected = cache / "camreview" / "models" / "yolo26n.pt"
    detector = UltralyticsDetector("yolo26n.pt", "auto", 0.35)
    assert detector._resolved_model() == expected
    assert str(expected) in detector.name


def test_model_cache_override_and_explicit_path(tmp_path: Path, monkeypatch) -> None:
    central = tmp_path / "central-models"
    monkeypatch.setenv("CAMREVIEW_MODEL_DIR", str(central))
    assert (
        UltralyticsDetector("yolo26n.pt", "auto", 0.35).resolved_model_path
        == central / "yolo26n.pt"
    )
    explicit = tmp_path / "custom" / "detector.pt"
    assert UltralyticsDetector(str(explicit), "auto", 0.35).resolved_model_path == explicit
