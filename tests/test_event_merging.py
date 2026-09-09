from datetime import timedelta

from camreview.models import MotionSample
from camreview.motion.events import EventBuilder


def sample(recording, seconds: float, positive: bool) -> MotionSample:
    return MotionSample(
        recording.start + timedelta(seconds=seconds),
        seconds,
        recording,
        positive,
        0.05 if positive else 0,
        0.05 if positive else 0,
    )


def test_trigger_quiet_and_merge(recording) -> None:
    builder = EventBuilder(trigger_frames=2, quiet_seconds=1.0, merge_gap_seconds=2.0)
    for seconds, positive in [
        (1.0, True),
        (1.25, True),
        (1.5, True),
        (2.5, False),
        (3.0, True),
        (3.25, True),
        (4.25, False),
    ]:
        builder.process(sample(recording, seconds, positive))
    events = builder.finish("living_room")
    assert len(events) == 1
    assert events[0].start == recording.start + timedelta(seconds=1)
    assert events[0].end == recording.start + timedelta(seconds=3.25)
    assert events[0].id.startswith("living_room-20260812-033301")


def test_cross_file_continuity(recording) -> None:
    builder = EventBuilder(trigger_frames=2, quiet_seconds=1.0, merge_gap_seconds=2.0)
    for seconds in (58.0, 58.25, 59.75, 60.0, 60.25, 63.0):
        builder.process(sample(recording, seconds, seconds < 61))
    events = builder.finish("living_room")
    assert len(events) == 1
    assert events[0].start == recording.start + timedelta(seconds=58)
    assert events[0].end == recording.start + timedelta(seconds=60.25)
