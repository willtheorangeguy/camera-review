from __future__ import annotations

import errno
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from camreview.decoding.pyav_decoder import PyAVDecoder, RecordingDecodeError
from camreview.errors import DetectorUnavailableError
from camreview.models import DecodedFrame, RecordingFile


class SeekFailingDecoder(PyAVDecoder):
    def __init__(self) -> None:
        super().__init__()
        self.attempts: list[bool] = []

    def _iter_frames_once(
        self,
        recording: RecordingFile,
        *,
        sample_fps: float,
        start_seconds: float,
        end_seconds: float | None,
        seek: bool,
    ) -> Iterator[DecodedFrame]:
        self.attempts.append(seek)
        if seek:
            raise OSError(22, "Invalid argument", recording.path.name)
        yield DecodedFrame(
            np.zeros((10, 10, 3), dtype=np.uint8),
            start_seconds,
            recording.start,
            recording,
        )


def test_failed_event_seek_reopens_and_decodes_sequentially(recording) -> None:
    decoder = SeekFailingDecoder()
    frames = list(decoder.iter_frames(recording, sample_fps=2, start_seconds=10))
    assert len(frames) == 1
    assert decoder.attempts == [True, False]


class MidstreamFailingDecoder(PyAVDecoder):
    def __init__(self) -> None:
        super().__init__(read_retries=2)
        self.starts: list[float] = []

    def _iter_frames_once(
        self,
        recording: RecordingFile,
        *,
        sample_fps: float,
        start_seconds: float,
        end_seconds: float | None,
        seek: bool,
    ) -> Iterator[DecodedFrame]:
        self.starts.append(start_seconds)
        if len(self.starts) == 1:
            yield DecodedFrame(
                np.zeros((10, 10, 3), dtype=np.uint8),
                0.0,
                recording.start,
                recording,
            )
            yield DecodedFrame(
                np.zeros((10, 10, 3), dtype=np.uint8),
                0.5,
                recording.start,
                recording,
            )
            raise OSError(errno.EIO, "temporary network read failure")
        for relative in (1.0, 1.5):
            yield DecodedFrame(
                np.zeros((10, 10, 3), dtype=np.uint8),
                relative,
                recording.start,
                recording,
            )


def test_midstream_network_failure_reopens_and_resumes_without_duplicates(recording) -> None:
    decoder = MidstreamFailingDecoder()
    frames = list(decoder.iter_frames(recording, sample_fps=2))
    assert [frame.relative_seconds for frame in frames] == [0.0, 0.5, 1.0, 1.5]
    assert decoder.starts == [0.0, 1.0]


class AlwaysFailingDecoder(PyAVDecoder):
    def _iter_frames_once(
        self,
        recording: RecordingFile,
        *,
        sample_fps: float,
        start_seconds: float,
        end_seconds: float | None,
        seek: bool,
    ) -> Iterator[DecodedFrame]:
        raise OSError(errno.EIO, "share disconnected")
        yield  # pragma: no cover


def test_exhausted_retries_report_stage_path_and_attempt_count(recording) -> None:
    decoder = AlwaysFailingDecoder(read_retries=2)
    with pytest.raises(RecordingDecodeError) as caught:
        list(decoder.iter_frames(recording, sample_fps=2))
    assert caught.value.stage == "decode"
    assert caught.value.attempts == 3
    assert caught.value.retryable
    assert str(recording.path.resolve()) in str(caught.value)


def test_open_passes_an_absolute_path_to_pyav(recording, monkeypatch) -> None:
    opened: list[str] = []
    sentinel = object()

    def fake_open(path: str, **kwargs):
        opened.append(path)
        return sentinel

    monkeypatch.setattr("camreview.decoding.pyav_decoder.av.open", fake_open)
    assert PyAVDecoder()._open(recording) is sentinel
    assert Path(opened[0]).is_absolute()


def test_auto_hardware_selection_tries_backends_in_order(recording, monkeypatch) -> None:
    decoder = PyAVDecoder("auto")
    attempted: list[str] = []
    monkeypatch.setattr(decoder, "_auto_hardware_candidates", lambda: ("cuda", "d3d11va"))

    def probe_backend(_recording: RecordingFile, backend: str) -> None:
        attempted.append(backend)
        if backend == "cuda":
            raise RuntimeError("CUDA unavailable")

    monkeypatch.setattr(decoder, "_probe_hardware_backend", probe_backend)
    decoder._select_hardware(recording)
    assert attempted == ["cuda", "d3d11va"]
    assert decoder.active_hwdecode == "d3d11va"
    assert decoder.decoder_name == "d3d11va hardware acceleration"


def test_auto_hardware_selection_safely_falls_back_to_cpu(recording, monkeypatch) -> None:
    decoder = PyAVDecoder("auto")
    monkeypatch.setattr(decoder, "_auto_hardware_candidates", lambda: ("cuda",))
    monkeypatch.setattr(
        decoder,
        "_probe_hardware_backend",
        lambda *_: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    decoder._select_hardware(recording)
    assert decoder.active_hwdecode == "none"
    assert decoder.decoder_name == "CPU (automatic hardware fallback)"


def test_explicit_unavailable_hardware_decoder_fails(recording, monkeypatch) -> None:
    decoder = PyAVDecoder("cuda")
    monkeypatch.setattr(
        decoder,
        "_probe_hardware_backend",
        lambda *_: (_ for _ in ()).throw(RuntimeError("driver mismatch")),
    )
    with pytest.raises(DetectorUnavailableError, match="--hwdecode auto or none"):
        decoder._select_hardware(recording)


class CloseFailingContainer:
    def close(self) -> None:
        raise OSError(errno.EINVAL, "mapped share rejected close")


def test_close_error_after_complete_read_does_not_discard_frames(recording) -> None:
    PyAVDecoder._close_input(
        CloseFailingContainer(),  # type: ignore[arg-type]
        recording,
        completed=True,
        unwinding=False,
    )
