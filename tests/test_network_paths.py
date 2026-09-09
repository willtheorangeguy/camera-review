from __future__ import annotations

import errno
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

from camreview import filesystem
from camreview.detection.ultralytics_detector import UltralyticsDetector
from camreview.extraction.ffmpeg import _ffmpeg_file_url


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
    cache = tmp_path / "local-cache"
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(cache))
        expected = cache / "CamReview" / "models" / "yolo26n.pt"
    else:
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
        expected = cache / "camreview" / "models" / "yolo26n.pt"
    detector = UltralyticsDetector("yolo26n.pt", "auto", 0.35)
    assert detector._resolved_model() == expected
