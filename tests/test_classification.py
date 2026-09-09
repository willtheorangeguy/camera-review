from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import cv2
import numpy as np

from camreview.decoding.base import VideoDecoder, VideoInfo
from camreview.detection.base import ObjectDetector
from camreview.detection.classification import classify_events
from camreview.models import (
    DecodedFrame,
    MotionEvent,
    ObjectDetection,
    PerformanceStats,
    RecordingFile,
    ScanSettings,
    SourceSegment,
)


class FakeDecoder(VideoDecoder):
    def probe(self, recording: RecordingFile) -> VideoInfo:
        return VideoInfo(3, 100, 100, 4)

    def iter_frames(
        self,
        recording: RecordingFile,
        *,
        sample_fps: float,
        start_seconds: float = 0,
        end_seconds: float | None = None,
    ) -> Iterator[DecodedFrame]:
        for seconds, x in [(0.5, None), (1.0, 35), (1.5, 45)]:
            image = np.zeros((100, 100, 3), dtype=np.uint8)
            if x is not None:
                cv2.rectangle(image, (x, 35), (x + 20, 65), (255, 255, 255), -1)
            yield DecodedFrame(
                image,
                seconds,
                recording.start + timedelta(seconds=seconds),
                recording,
            )


class FakeDetector(ObjectDetector):
    name = "fake"
    device_name = "test CPU"

    def load(self) -> None:
        return None

    def detect(self, images: list[np.ndarray]) -> list[list[ObjectDetection]]:
        return [
            [
                ObjectDetection("dog", "pet", 0.8, (25, 25, 75, 75)),
                ObjectDetection("car", "vehicle", 0.9, (0, 0, 20, 20)),
            ]
            for _ in images
        ]


def test_only_objects_overlapping_motion_determine_category(recording) -> None:
    event = MotionEvent(
        "event-001",
        recording.start + timedelta(seconds=1),
        recording.start + timedelta(seconds=2),
        0.1,
        0.05,
        0.1,
        [SourceSegment(recording.relative_path, 1, 2)],
    )
    performance = PerformanceStats()
    classify_events(
        [event],
        [recording],
        FakeDecoder(),
        FakeDetector(),
        ScanSettings(batch_size=1, classify_fps=2, motion_object_overlap=0.05),
        performance,
    )
    assert event.classification is not None
    assert event.classification.categories == ["pet"]
    assert [item.class_name for item in event.classification.objects] == ["dog"]
    assert {item.class_name for item in event.classification.visible_objects} == {
        "dog",
        "car",
    }
    assert performance.classification_frames == 2
