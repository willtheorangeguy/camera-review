from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..models import ObjectDetection


class ObjectDetector(ABC):
    name: str
    device_name: str

    @abstractmethod
    def load(self) -> None:
        """Load model state and select its compute device."""

    @abstractmethod
    def detect(self, images: list[np.ndarray]) -> list[list[ObjectDetection]]:
        """Detect objects in a bounded batch of BGR images."""

    def close(self) -> None:
        """Release backend resources."""
        return None
