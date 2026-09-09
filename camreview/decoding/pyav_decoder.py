from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import timedelta
from fractions import Fraction

import av

from ..models import DecodedFrame, RecordingFile
from .base import VideoDecoder, VideoInfo

LOG = logging.getLogger(__name__)


class PyAVDecoder(VideoDecoder):
    """CPU-first FFmpeg decoder using PyAV and actual frame PTS values."""

    def __init__(self, hwdecode: str = "none") -> None:
        self.hwdecode = hwdecode
        self._seek_warning_shown = False
        if hwdecode == "cuda":
            LOG.warning("PyAV CUDA decoding is not enabled in v1; using CPU decoding")

    @staticmethod
    def _video_stream(container: av.container.InputContainer) -> av.video.stream.VideoStream:
        if not container.streams.video:
            raise ValueError("file contains no video stream")
        return container.streams.video[0]

    @staticmethod
    def _open(recording: RecordingFile) -> av.container.InputContainer:
        """Open a recording, retrying brief SMB/network interruptions."""
        for attempt in range(3):
            try:
                return av.open(str(recording.path))
            except (OSError, av.error.FFmpegError):
                if attempt == 2:
                    raise
                time.sleep(0.2 * (2**attempt))
        raise RuntimeError("unreachable")

    def probe(self, recording: RecordingFile) -> VideoInfo:
        info: VideoInfo | None = None
        with self._open(recording) as container:
            stream = self._video_stream(container)
            duration: float | None = None
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration = float(container.duration / av.time_base)
            if duration is None or duration <= 0:
                raise ValueError("video duration is unavailable or invalid")
            fps = float(stream.average_rate) if stream.average_rate else None
            info = VideoInfo(duration, stream.width, stream.height, fps)
        if info is None:
            raise ValueError("video probe did not produce stream information")
        return info

    def iter_frames(
        self,
        recording: RecordingFile,
        *,
        sample_fps: float,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Iterator[DecodedFrame]:
        attempted_seek = start_seconds > 1.0
        yielded = False
        try:
            for frame in self._iter_frames_once(
                recording,
                sample_fps=sample_fps,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                seek=attempted_seek,
            ):
                yielded = True
                yield frame
        except (OSError, ValueError, av.error.FFmpegError) as exc:
            if not attempted_seek or yielded:
                raise
            if not self._seek_warning_shown:
                LOG.warning(
                    "Direct event seek is unsupported for %s (%s); "
                    "reopening and decoding sequentially",
                    recording.path,
                    exc,
                )
                self._seek_warning_shown = True
            yield from self._iter_frames_once(
                recording,
                sample_fps=sample_fps,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                seek=False,
            )

    def _iter_frames_once(
        self,
        recording: RecordingFile,
        *,
        sample_fps: float,
        start_seconds: float,
        end_seconds: float | None,
        seek: bool,
    ) -> Iterator[DecodedFrame]:
        interval = 1.0 / sample_fps
        next_sample = max(0.0, start_seconds)
        with self._open(recording) as container:
            stream = self._video_stream(container)
            fallback_fps = float(stream.average_rate) if stream.average_rate else 25.0
            stream_origin = (
                float(stream.start_time * stream.time_base)
                if stream.start_time is not None and stream.time_base is not None
                else 0.0
            )
            seeked = False
            if seek and stream.time_base is not None:
                seek_seconds = max(0.0, start_seconds - 1.0) + stream_origin
                container.seek(
                    int(seek_seconds / float(stream.time_base)),
                    stream=stream,
                    backward=True,
                    any_frame=False,
                )
                seeked = True
            decoded_index = max(0, int((start_seconds - 1.0) * fallback_fps)) if seeked else 0
            last_relative = -1.0
            for frame in container.decode(stream):
                if frame.pts is not None and frame.time_base is not None:
                    relative = float(Fraction(frame.pts) * frame.time_base) - stream_origin
                elif frame.time is not None:
                    relative = float(frame.time) - stream_origin
                else:
                    relative = decoded_index / fallback_fps
                decoded_index += 1
                if relative < 0 or relative + 1e-6 < last_relative:
                    relative = max(last_relative + 1.0 / fallback_fps, decoded_index / fallback_fps)
                last_relative = relative
                if end_seconds is not None and relative > end_seconds + interval:
                    break
                if relative + 1e-6 < next_sample:
                    continue
                while next_sample + interval <= relative:
                    next_sample += interval
                next_sample += interval
                image = frame.to_ndarray(format="bgr24")
                yield DecodedFrame(
                    image=image,
                    relative_seconds=relative,
                    absolute_datetime=recording.start + timedelta(seconds=relative),
                    recording=recording,
                )
