from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..errors import ConfigurationError
from ..models import DecodedFrame, MotionSample, ScanSettings
from .base import MotionDetector


@dataclass(frozen=True, slots=True)
class SensitivityPreset:
    minimum_ratio: float
    minimum_contour_pixels: float
    variance_threshold: float


PRESETS = {
    "low": SensitivityPreset(0.008, 500.0, 32.0),
    "medium": SensitivityPreset(0.003, 180.0, 24.0),
    "high": SensitivityPreset(0.001, 60.0, 16.0),
}


class MOG2MotionDetector(MotionDetector):
    """Downscaled grayscale MOG2 detector whose model persists across files."""

    def __init__(self, settings: ScanSettings) -> None:
        self.settings = settings
        self.preset = PRESETS[settings.sensitivity]
        self._subtractor: cv2.BackgroundSubtractor | None = None
        self._shape: tuple[int, int] | None = None
        self._mask_source = self._load_mask(settings.mask)
        self._mask: np.ndarray | None = None
        self.reset()

    @staticmethod
    def _load_mask(path: Path | None) -> np.ndarray | None:
        if path is None:
            return None
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ConfigurationError(f"Could not read ignore mask: {path}")
        return image

    def reset(self) -> None:
        threshold = self.settings.var_threshold or self.preset.variance_threshold
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=max(100, int(self.settings.motion_fps * 30)),
            varThreshold=threshold,
            detectShadows=True,
        )
        self._shape = None
        self._mask = None

    def _prepare(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        target_width = min(width, self.settings.analysis_width)
        target_height = max(1, round(height * target_width / width))
        if target_width != width:
            image = cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def process_frame(self, frame: DecodedFrame) -> MotionSample:
        gray = self._prepare(frame.image)
        shape = gray.shape
        if self._shape is not None and self._shape != shape:
            self.reset()
        if self._shape is None:
            self._shape = shape
            if self._mask_source is not None:
                self._mask = cv2.resize(
                    self._mask_source,
                    (shape[1], shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )
                _, self._mask = cv2.threshold(self._mask, 127, 255, cv2.THRESH_BINARY)
        assert self._subtractor is not None
        foreground = self._subtractor.apply(gray)
        foreground[foreground < 240] = 0  # suppress MOG2 shadow values
        if self._mask is not None:
            foreground = cv2.bitwise_and(foreground, self._mask)
            analyzed_pixels = max(1, cv2.countNonZero(self._mask))
        else:
            analyzed_pixels = foreground.size
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2)
        changed_pixels = cv2.countNonZero(foreground)
        ratio = changed_pixels / analyzed_pixels
        scene_change = ratio >= self.settings.scene_change_threshold
        if scene_change:
            # A high learning rate lets MOG2 settle rapidly after lights/IR/exposure changes.
            self._subtractor.apply(gray, learningRate=0.5)
            return MotionSample(
                frame.absolute_datetime,
                frame.relative_seconds,
                frame.recording,
                False,
                ratio,
                ratio,
                scene_change=True,
            )
        contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        minimum_contour = self.settings.min_motion_area or self.preset.minimum_contour_pixels
        boxes: list[tuple[int, int, int, int]] = []
        meaningful_area = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= minimum_contour:
                meaningful_area += area
                x, y, width, height = cv2.boundingRect(contour)
                boxes.append((int(x), int(y), int(width), int(height)))
        score = meaningful_area / analyzed_pixels
        positive = ratio >= self.preset.minimum_ratio and bool(boxes)
        return MotionSample(
            timestamp=frame.absolute_datetime,
            relative_seconds=frame.relative_seconds,
            recording=frame.recording,
            positive=positive,
            score=score,
            foreground_ratio=ratio,
            bounding_boxes=tuple(boxes),
        )
