from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from camreview.decoding.pyav_decoder import PyAVDecoder
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
