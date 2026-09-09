from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from ..models import DecodedFrame, RecordingFile


@dataclass(frozen=True, slots=True)
class VideoInfo:
    duration_seconds: float
    width: int
    height: int
    average_fps: float | None


class VideoDecoder(ABC):
    @abstractmethod
    def probe(self, recording: RecordingFile) -> VideoInfo:
        """Read stream metadata without decoding the full recording."""

    @abstractmethod
    def iter_frames(
        self,
        recording: RecordingFile,
        *,
        sample_fps: float,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Iterator[DecodedFrame]:
        """Yield sampled frames, timestamped using stream presentation timestamps."""
