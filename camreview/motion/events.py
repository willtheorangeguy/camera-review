from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..models import MotionEvent, MotionSample


@dataclass(slots=True)
class _Accumulator:
    start: datetime
    last_positive: datetime
    score_sum: float = 0.0
    score_count: int = 0
    max_score: float = 0.0
    max_foreground_ratio: float = 0.0

    def add(self, sample: MotionSample) -> None:
        if sample.positive:
            self.last_positive = sample.timestamp
            self.score_sum += sample.score
            self.score_count += 1
            self.max_score = max(self.max_score, sample.score)
            self.max_foreground_ratio = max(self.max_foreground_ratio, sample.foreground_ratio)


@dataclass(slots=True)
class EventBuilder:
    trigger_frames: int
    quiet_seconds: float
    merge_gap_seconds: float
    _pending: list[MotionSample] = field(default_factory=list)
    _active: _Accumulator | None = None
    _events: list[MotionEvent] = field(default_factory=list)

    def process(self, sample: MotionSample) -> None:
        if self._active is None:
            if sample.positive:
                self._pending.append(sample)
                if len(self._pending) >= self.trigger_frames:
                    first = self._pending[0]
                    self._active = _Accumulator(first.timestamp, first.timestamp)
                    for pending in self._pending:
                        self._active.add(pending)
                    self._pending.clear()
            else:
                self._pending.clear()
            return
        if sample.positive:
            self._active.add(sample)
            return
        quiet = (sample.timestamp - self._active.last_positive).total_seconds()
        if quiet >= self.quiet_seconds:
            self._finish_active()

    def break_continuity(self) -> None:
        self._pending.clear()
        self._finish_active()

    def _finish_active(self) -> None:
        if self._active is None:
            return
        active = self._active
        event = MotionEvent(
            id="",
            start=active.start,
            end=active.last_positive,
            max_score=active.max_score,
            mean_score=active.score_sum / max(1, active.score_count),
            max_foreground_ratio=active.max_foreground_ratio,
        )
        if (
            self._events
            and (event.start - self._events[-1].end).total_seconds() <= self.merge_gap_seconds
        ):
            previous = self._events[-1]
            previous_count = max(1, round(previous.duration_seconds))
            event_count = max(1, round(event.duration_seconds))
            previous.end = max(previous.end, event.end)
            previous.max_score = max(previous.max_score, event.max_score)
            previous.max_foreground_ratio = max(
                previous.max_foreground_ratio, event.max_foreground_ratio
            )
            previous.mean_score = (
                previous.mean_score * previous_count + event.mean_score * event_count
            ) / (previous_count + event_count)
        else:
            self._events.append(event)
        self._active = None

    def finish(self, camera: str) -> list[MotionEvent]:
        self._finish_active()
        for index, event in enumerate(self._events, 1):
            event.id = f"{camera}-{event.start:%Y%m%d-%H%M%S}-{index:03d}"
        return self._events
