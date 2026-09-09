from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np


def iso_millis(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds")


@dataclass(slots=True)
class RecordingFile:
    path: Path
    source_root: Path
    camera: str
    start: datetime
    extension: str
    duration_seconds: float | None = None

    @property
    def end(self) -> datetime | None:
        if self.duration_seconds is None:
            return None
        from datetime import timedelta

        return self.start + timedelta(seconds=self.duration_seconds)

    @property
    def relative_path(self) -> str:
        try:
            return self.path.relative_to(self.source_root).as_posix()
        except ValueError:
            return self.path.name


@dataclass(slots=True)
class DecodedFrame:
    image: np.ndarray
    relative_seconds: float
    absolute_datetime: datetime
    recording: RecordingFile


@dataclass(slots=True)
class MotionSample:
    timestamp: datetime
    relative_seconds: float
    recording: RecordingFile
    positive: bool
    score: float
    foreground_ratio: float
    bounding_boxes: tuple[tuple[int, int, int, int], ...] = ()
    scene_change: bool = False


@dataclass(slots=True)
class SourceSegment:
    file: str
    relative_start: float
    relative_end: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "relative_start": round(self.relative_start, 3),
            "relative_end": round(self.relative_end, 3),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SourceSegment:
        return cls(
            file=str(value["file"]),
            relative_start=float(value["relative_start"]),
            relative_end=float(value["relative_end"]),
        )


@dataclass(slots=True)
class ObjectDetection:
    class_name: str
    category: str
    confidence: float
    box: tuple[float, float, float, float]


@dataclass(slots=True)
class ClassifiedObject:
    class_name: str
    category: str
    hits: int
    max_confidence: float
    mean_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": self.class_name,
            "category": self.category,
            "hits": self.hits,
            "max_confidence": round(self.max_confidence, 4),
            "mean_confidence": round(self.mean_confidence, 4),
        }


@dataclass(slots=True)
class EventClassification:
    categories: list[str]
    objects: list[ClassifiedObject]
    visible_objects: list[ClassifiedObject] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "categories": self.categories,
            "objects": [item.to_dict() for item in self.objects],
            "visible_objects": [item.to_dict() for item in self.visible_objects],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EventClassification:
        def parse(items: list[dict[str, Any]]) -> list[ClassifiedObject]:
            return [
                ClassifiedObject(
                    class_name=str(item["class"]),
                    category=str(item["category"]),
                    hits=int(item["hits"]),
                    max_confidence=float(item["max_confidence"]),
                    mean_confidence=float(item.get("mean_confidence", item["max_confidence"])),
                )
                for item in items
            ]

        return cls(
            categories=[str(item) for item in value.get("categories", [])],
            objects=parse(value.get("objects", [])),
            visible_objects=parse(value.get("visible_objects", [])),
        )


@dataclass(slots=True)
class MotionEvent:
    id: str
    start: datetime
    end: datetime
    max_score: float
    mean_score: float
    max_foreground_ratio: float
    sources: list[SourceSegment] = field(default_factory=list)
    classification: EventClassification | None = None

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": iso_millis(self.start),
            "end": iso_millis(self.end),
            "duration_seconds": round(self.duration_seconds, 3),
            "motion": {
                "max_score": round(self.max_score, 6),
                "mean_score": round(self.mean_score, 6),
                "max_foreground_ratio": round(self.max_foreground_ratio, 6),
            },
            "classification": (
                self.classification.to_dict() if self.classification is not None else None
            ),
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MotionEvent:
        motion = value.get("motion", {})
        classification = value.get("classification")
        return cls(
            id=str(value["id"]),
            start=datetime.fromisoformat(value["start"]),
            end=datetime.fromisoformat(value["end"]),
            max_score=float(motion.get("max_score", 0.0)),
            mean_score=float(motion.get("mean_score", 0.0)),
            max_foreground_ratio=float(motion.get("max_foreground_ratio", 0.0)),
            sources=[SourceSegment.from_dict(item) for item in value.get("sources", [])],
            classification=(
                EventClassification.from_dict(classification) if classification else None
            ),
        )


@dataclass(slots=True)
class TimelineGap:
    start: datetime
    end: datetime
    reason: str = "no footage available"

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": iso_millis(self.start),
            "end": iso_millis(self.end),
            "duration_seconds": round(self.duration_seconds, 3),
            "reason": self.reason,
        }


@dataclass(slots=True)
class ProcessingIssue:
    file: str
    error: str
    expected_start: datetime | None = None
    kind: str = "corrupt_or_unreadable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "error": self.error,
            "expected_start": iso_millis(self.expected_start) if self.expected_start else None,
            "kind": self.kind,
        }


@dataclass(slots=True)
class TimeRange:
    start: datetime | None
    end: datetime | None

    @property
    def all(self) -> bool:
        return self.start is None and self.end is None

    def contains(self, timestamp: datetime) -> bool:
        return (self.start is None or timestamp >= self.start) and (
            self.end is None or timestamp <= self.end
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": iso_millis(self.start) if self.start else None,
            "end": iso_millis(self.end) if self.end else None,
            "all": self.all,
        }


@dataclass(slots=True)
class ScanSettings:
    motion_fps: float = 4.0
    sensitivity: str = "medium"
    min_motion_area: float | None = None
    var_threshold: float | None = None
    trigger_frames: int = 2
    quiet_seconds: float = 1.5
    merge_gap: float = 2.0
    reset_gap: float = 10.0
    warmup: float = 3.0
    pre_roll: float = 2.0
    post_roll: float = 3.0
    scene_change_threshold: float = 0.60
    mask: Path | None = None
    analysis_width: int = 640
    hwdecode: str = "none"
    classify: bool = False
    classify_fps: float = 2.0
    batch_size: int = 8
    model: str = "yolo26n.pt"
    device: str = "auto"
    confidence: float = 0.35
    motion_object_overlap: float = 0.10

    def to_dict(self) -> dict[str, Any]:
        return {
            "motion_fps": self.motion_fps,
            "sensitivity": self.sensitivity,
            "min_motion_area": self.min_motion_area,
            "var_threshold": self.var_threshold,
            "trigger_frames": self.trigger_frames,
            "quiet_seconds": self.quiet_seconds,
            "merge_gap_seconds": self.merge_gap,
            "reset_gap_seconds": self.reset_gap,
            "warmup_seconds": self.warmup,
            "pre_roll_seconds": self.pre_roll,
            "post_roll_seconds": self.post_roll,
            "scene_change_threshold": self.scene_change_threshold,
            "mask": str(self.mask) if self.mask else None,
            "analysis_width": self.analysis_width,
            "hwdecode": self.hwdecode,
            "classification": {
                "enabled": self.classify,
                "classify_fps": self.classify_fps,
                "batch_size": self.batch_size,
                "model": self.model,
                "device": self.device,
                "confidence": self.confidence,
                "motion_object_overlap": self.motion_object_overlap,
            },
        }


@dataclass(slots=True)
class PerformanceStats:
    wall_seconds: float = 0.0
    video_seconds: float = 0.0
    motion_frames: int = 0
    classification_frames: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    device: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "wall_clock_seconds": round(self.wall_seconds, 3),
            "video_seconds_analyzed": round(self.video_seconds, 3),
            "effective_realtime_speed": (
                round(self.video_seconds / self.wall_seconds, 3) if self.wall_seconds else 0.0
            ),
            "motion_frames_sampled": self.motion_frames,
            "classification_frames_processed": self.classification_frames,
            "device": self.device,
            "files_processed": self.files_processed,
            "files_skipped": self.files_skipped,
        }


@dataclass(slots=True)
class ScanReport:
    camera: str
    recording_date: date
    source_root: Path
    requested_range: TimeRange
    settings: ScanSettings
    events: list[MotionEvent]
    gaps: list[TimelineGap]
    issues: list[ProcessingIssue]
    performance: PerformanceStats
    scene_changes: int = 0
    status: str = "complete"
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        motion_seconds = sum(event.duration_seconds for event in self.events)
        return {
            "schema_version": 1,
            "run": {"status": self.status, "created_at": iso_millis(self.created_at)},
            "camera": self.camera,
            "recording_date": self.recording_date.isoformat(),
            "source_root": str(self.source_root),
            "requested_range": self.requested_range.to_dict(),
            "settings": self.settings.to_dict(),
            "summary": {
                "files_scanned": self.performance.files_processed,
                "files_skipped": self.performance.files_skipped,
                "seconds_scanned": round(self.performance.video_seconds, 3),
                "motion_events": len(self.events),
                "motion_seconds": round(motion_seconds, 3),
                "scene_changes": self.scene_changes,
                "timeline_gaps": len(self.gaps),
            },
            "performance": self.performance.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "timeline_gaps": [gap.to_dict() for gap in self.gaps],
            "issues": [issue.to_dict() for issue in self.issues],
        }
