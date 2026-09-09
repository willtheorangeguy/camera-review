from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..decoding.base import VideoDecoder
from ..models import (
    ClassifiedObject,
    EventClassification,
    MotionEvent,
    ObjectDetection,
    PerformanceStats,
    RecordingFile,
    ScanSettings,
)
from .base import ObjectDetector


@dataclass(slots=True)
class _FrameForDetection:
    image: np.ndarray
    motion_mask: np.ndarray


def _overlap(detection: ObjectDetection, mask: np.ndarray) -> float:
    height, width = mask.shape
    x1, y1, x2, y2 = detection.box
    left = max(0, min(width, int(x1)))
    top = max(0, min(height, int(y1)))
    right = max(left, min(width, int(np.ceil(x2))))
    bottom = max(top, min(height, int(np.ceil(y2))))
    area = (right - left) * (bottom - top)
    if area <= 0:
        return 0.0
    return float(cv2.countNonZero(mask[top:bottom, left:right]) / area)


@dataclass(slots=True)
class _ClassificationAccumulator:
    overlap_threshold: float
    confidence: float
    moving: dict[tuple[str, str], list[float]] = field(default_factory=lambda: defaultdict(list))
    visible: dict[tuple[str, str], list[float]] = field(default_factory=lambda: defaultdict(list))

    def add(self, detections: list[ObjectDetection], mask: np.ndarray) -> None:
        for detection in detections:
            key = (detection.class_name, detection.category)
            self.visible[key].append(detection.confidence)
            if _overlap(detection, mask) >= self.overlap_threshold:
                self.moving[key].append(detection.confidence)

    def _accepted(self, values: dict[tuple[str, str], list[float]]) -> list[ClassifiedObject]:
        output: list[ClassifiedObject] = []
        for (class_name, category), confidences in values.items():
            # Two observations are preferred; retain one strong hit for brief events.
            if len(confidences) < 2 and max(confidences) < max(0.65, self.confidence + 0.20):
                continue
            output.append(
                ClassifiedObject(
                    class_name,
                    category,
                    len(confidences),
                    max(confidences),
                    sum(confidences) / len(confidences),
                )
            )
        return sorted(output, key=lambda item: (-item.max_confidence, item.class_name))

    def finish(self) -> EventClassification:
        moving_objects = self._accepted(self.moving)
        visible_objects = self._accepted(self.visible)
        categories = sorted({item.category for item in moving_objects}) or ["unknown"]
        return EventClassification(categories, moving_objects, visible_objects)


def _recording_lookup(recordings: list[RecordingFile]) -> dict[str, RecordingFile]:
    lookup: dict[str, RecordingFile] = {}
    for recording in recordings:
        lookup[recording.relative_path] = recording
        lookup[recording.path.name] = recording
        lookup[recording.path.as_posix()] = recording
    return lookup


def _process_batch(
    batch: list[_FrameForDetection],
    detector: ObjectDetector,
    accumulator: _ClassificationAccumulator,
    performance: PerformanceStats,
) -> None:
    if not batch:
        return
    results = detector.detect([item.image for item in batch])
    for detections, item in zip(results, batch, strict=True):
        accumulator.add(detections, item.motion_mask)
    performance.classification_frames += len(batch)
    batch.clear()


def classify_events(
    events: list[MotionEvent],
    recordings: list[RecordingFile],
    decoder: VideoDecoder,
    detector: ObjectDetector,
    settings: ScanSettings,
    performance: PerformanceStats,
    notify: Callable[[str], None] | None = None,
) -> None:
    """Classify event frames with memory bounded by the configured batch size."""
    lookup = _recording_lookup(recordings)
    if notify:
        notify(f"Loading object detector {detector.name}...")
    detector.load()
    performance.device = detector.device_name
    if notify:
        notify(f"Object detector ready. Device: {detector.device_name}")
    try:
        total = len(events)
        interval = max(1, total // 20)
        for event_index, event in enumerate(events, 1):
            if notify and (event_index == 1 or event_index == total or event_index % interval == 0):
                notify(
                    f"[classify {event_index:,}/{total:,}] {event.id} "
                    f"({event.duration_seconds:.1f}s)"
                )
            accumulator = _ClassificationAccumulator(
                settings.motion_object_overlap, settings.confidence
            )
            batch: list[_FrameForDetection] = []
            previous_gray: np.ndarray | None = None
            for source in event.sources:
                recording = lookup.get(source.file)
                if recording is None:
                    candidate = Path(source.file)
                    raise FileNotFoundError(f"Event source is not available: {candidate}")
                baseline = max(0.0, source.relative_start - 1.0 / settings.classify_fps)
                for frame in decoder.iter_frames(
                    recording,
                    sample_fps=settings.classify_fps,
                    start_seconds=baseline,
                    end_seconds=source.relative_end,
                ):
                    gray = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY)
                    if previous_gray is None or previous_gray.shape != gray.shape:
                        motion_mask = np.zeros_like(gray)
                    else:
                        difference = cv2.absdiff(previous_gray, gray)
                        _, motion_mask = cv2.threshold(difference, 20, 255, cv2.THRESH_BINARY)
                        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
                        motion_mask = cv2.dilate(motion_mask, kernel, iterations=2)
                    previous_gray = gray
                    if frame.relative_seconds + 1e-6 < source.relative_start:
                        continue
                    batch.append(_FrameForDetection(frame.image, motion_mask))
                    if len(batch) >= settings.batch_size:
                        _process_batch(batch, detector, accumulator, performance)
            _process_batch(batch, detector, accumulator, performance)
            event.classification = accumulator.finish()
        if notify:
            notify(
                f"Classification complete: {total:,} event(s), "
                f"{performance.classification_frames:,} sampled frame(s)."
            )
    finally:
        detector.close()
