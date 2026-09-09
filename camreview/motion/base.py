from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import DecodedFrame, MotionSample


class MotionDetector(ABC):
    @abstractmethod
    def process_frame(self, frame: DecodedFrame) -> MotionSample:
        """Analyze one sampled frame."""

    @abstractmethod
    def reset(self) -> None:
        """Discard learned scene state."""
