from __future__ import annotations

import errno
import logging
import time
from collections.abc import Iterator
from datetime import timedelta
from fractions import Fraction
from pathlib import Path

import av

from ..models import DecodedFrame, RecordingFile
from .base import VideoDecoder, VideoInfo

LOG = logging.getLogger(__name__)

_TRANSIENT_DECODE_ERRNOS = {
    errno.EAGAIN,
    errno.EBUSY,
    errno.ECONNABORTED,
    errno.ECONNRESET,
    errno.EHOSTUNREACH,
    errno.EINTR,
    errno.EINVAL,
    errno.EIO,
    errno.ENETDOWN,
    errno.ENETRESET,
    errno.ENETUNREACH,
    errno.ETIMEDOUT,
}
if hasattr(errno, "ESTALE"):
    _TRANSIENT_DECODE_ERRNOS.add(errno.ESTALE)

_TRANSIENT_WINERRORS = {5, 21, 32, 33, 53, 59, 64, 67, 121, 1231, 1232}
_DECODE_EXCEPTIONS = (OSError, ValueError, av.error.FFmpegError)


class RecordingDecodeError(RuntimeError):
    """A recording failure with enough context for reports and recovery."""

    def __init__(
        self,
        stage: str,
        path: Path,
        cause: BaseException,
        *,
        attempts: int = 1,
        last_successful_seconds: float | None = None,
    ) -> None:
        self.stage = stage
        self.path = path
        self.cause = cause
        self.attempts = attempts
        self.last_successful_seconds = last_successful_seconds
        super().__init__(str(self))

    @property
    def retryable(self) -> bool:
        error_number = getattr(self.cause, "errno", None)
        windows_error = getattr(self.cause, "winerror", None)
        return error_number in _TRANSIENT_DECODE_ERRNOS or windows_error in _TRANSIENT_WINERRORS

    def __str__(self) -> str:
        progress = (
            f" at {self.last_successful_seconds:.3f}s"
            if self.last_successful_seconds is not None
            else ""
        )
        attempts = f" after {self.attempts} attempts" if self.attempts > 1 else ""
        return f"{self.stage} stage failed{progress}{attempts} for {self.path}: {self.cause}"


class PyAVDecoder(VideoDecoder):
    """CPU-first FFmpeg decoder using PyAV and actual frame PTS values."""

    def __init__(self, hwdecode: str = "none", *, read_retries: int = 3) -> None:
        self.hwdecode = hwdecode
        self.read_retries = max(0, read_retries)
        self._seek_warning_shown = False
        if hwdecode == "cuda":
            LOG.warning("PyAV CUDA decoding is not enabled in v1; using CPU decoding")

    @staticmethod
    def _video_stream(container: av.container.InputContainer) -> av.video.stream.VideoStream:
        if not container.streams.video:
            raise ValueError("file contains no video stream")
        return container.streams.video[0]

    @staticmethod
    def _resolved_path(recording: RecordingFile) -> Path:
        """Return an absolute native-library-safe path, including on mapped drives."""
        return recording.path.expanduser().resolve()

    @classmethod
    def _open(cls, recording: RecordingFile) -> av.container.InputContainer:
        """Open a recording, retrying brief SMB/network interruptions."""
        path = cls._resolved_path(recording)
        for attempt in range(3):
            try:
                return av.open(str(path))
            except (OSError, av.error.FFmpegError):
                if attempt == 2:
                    raise
                time.sleep(0.2 * (2**attempt))
        raise RuntimeError("unreachable")

    @staticmethod
    def _close_input(
        container: av.container.InputContainer,
        recording: RecordingFile,
        *,
        completed: bool,
        unwinding: bool,
    ) -> None:
        try:
            container.close()
        except (OSError, av.error.FFmpegError) as exc:
            # This is an input. Once all requested frames were read, close
            # cannot invalidate frames already handed to the caller.
            if completed:
                LOG.warning(
                    "close stage reported an SMB/filesystem error for %s after all "
                    "requested frames were read; keeping the processed frames: %s",
                    recording.relative_path,
                    exc,
                )
            elif unwinding:
                LOG.debug(
                    "close stage also failed for %s while handling another error: %s",
                    recording.relative_path,
                    exc,
                )
            else:
                raise RecordingDecodeError(
                    "close", PyAVDecoder._resolved_path(recording), exc
                ) from exc

    def probe(self, recording: RecordingFile) -> VideoInfo:
        container: av.container.InputContainer | None = None
        completed = False
        try:
            try:
                container = self._open(recording)
            except _DECODE_EXCEPTIONS as exc:
                raise RecordingDecodeError("open", self._resolved_path(recording), exc) from exc
            try:
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
            except _DECODE_EXCEPTIONS as exc:
                raise RecordingDecodeError("metadata", self._resolved_path(recording), exc) from exc
            completed = True
            return info
        finally:
            if container is not None:
                self._close_input(
                    container,
                    recording,
                    completed=completed,
                    unwinding=not completed,
                )

    def iter_frames(
        self,
        recording: RecordingFile,
        *,
        sample_fps: float,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Iterator[DecodedFrame]:
        interval = 1.0 / sample_fps
        resume_at = max(0.0, start_seconds)
        use_seek = resume_at > 1.0
        retries = 0
        last_successful: float | None = None

        while True:
            yielded_this_attempt = False
            try:
                for frame in self._iter_frames_once(
                    recording,
                    sample_fps=sample_fps,
                    start_seconds=resume_at,
                    end_seconds=end_seconds,
                    seek=use_seek,
                ):
                    # A coarse/keyframe seek may return an earlier frame. Never
                    # replay it into motion detection or classification.
                    if last_successful is not None and frame.relative_seconds <= last_successful:
                        continue
                    yielded_this_attempt = True
                    last_successful = frame.relative_seconds
                    yield frame
                return
            except (*_DECODE_EXCEPTIONS, RecordingDecodeError) as exc:
                failure = (
                    exc
                    if isinstance(exc, RecordingDecodeError)
                    else RecordingDecodeError(
                        "seek" if use_seek and not yielded_this_attempt else "decode",
                        self._resolved_path(recording),
                        exc,
                    )
                )

                # Broken or non-seekable MKV indexes are not fatal. Reopen and
                # decode forward from the beginning to the requested timestamp.
                if failure.stage == "seek" and use_seek and not yielded_this_attempt:
                    if not self._seek_warning_shown:
                        LOG.warning(
                            "seek stage is unsupported for %s (%s); reopening and "
                            "decoding sequentially",
                            recording.relative_path,
                            failure.cause,
                        )
                        self._seek_warning_shown = True
                    use_seek = False
                    continue

                if not failure.retryable or retries >= self.read_retries:
                    failure.attempts = retries + 1
                    failure.last_successful_seconds = last_successful
                    raise failure from exc

                retries += 1
                if last_successful is not None:
                    resume_at = last_successful + interval
                use_seek = resume_at > 1.0
                LOG.warning(
                    "%s stage hit a temporary SMB/filesystem error for %s%s; "
                    "reopening at %.3fs (retry %d/%d): %s",
                    failure.stage,
                    recording.relative_path,
                    f" after {last_successful:.3f}s" if last_successful is not None else "",
                    resume_at,
                    retries,
                    self.read_retries,
                    failure.cause,
                )
                time.sleep(0.2 * (2 ** (retries - 1)))

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
        container: av.container.InputContainer | None = None
        completed = False
        try:
            try:
                container = self._open(recording)
            except _DECODE_EXCEPTIONS as exc:
                raise RecordingDecodeError("open", self._resolved_path(recording), exc) from exc

            try:
                stream = self._video_stream(container)
                fallback_fps = float(stream.average_rate) if stream.average_rate else 25.0
                stream_origin = (
                    float(stream.start_time * stream.time_base)
                    if stream.start_time is not None and stream.time_base is not None
                    else 0.0
                )
            except _DECODE_EXCEPTIONS as exc:
                raise RecordingDecodeError(
                    "stream setup", self._resolved_path(recording), exc
                ) from exc

            seeked = False
            if seek and stream.time_base is not None:
                seek_seconds = max(0.0, start_seconds - 1.0) + stream_origin
                try:
                    container.seek(
                        int(seek_seconds / float(stream.time_base)),
                        stream=stream,
                        backward=True,
                        any_frame=False,
                    )
                except _DECODE_EXCEPTIONS as exc:
                    raise RecordingDecodeError("seek", self._resolved_path(recording), exc) from exc
                seeked = True

            decoded_index = max(0, int((start_seconds - 1.0) * fallback_fps)) if seeked else 0
            last_relative = -1.0
            try:
                for frame in container.decode(stream):
                    if frame.pts is not None and frame.time_base is not None:
                        relative = float(Fraction(frame.pts) * frame.time_base) - stream_origin
                    elif frame.time is not None:
                        relative = float(frame.time) - stream_origin
                    else:
                        relative = decoded_index / fallback_fps
                    decoded_index += 1
                    if relative < 0 or relative + 1e-6 < last_relative:
                        relative = max(
                            last_relative + 1.0 / fallback_fps,
                            decoded_index / fallback_fps,
                        )
                    last_relative = relative
                    if end_seconds is not None and relative > end_seconds + interval:
                        break
                    if relative + 1e-6 < next_sample:
                        continue
                    while next_sample + interval <= relative:
                        next_sample += interval
                    next_sample += interval
                    try:
                        image = frame.to_ndarray(format="bgr24")
                    except _DECODE_EXCEPTIONS as exc:
                        raise RecordingDecodeError(
                            "frame conversion", self._resolved_path(recording), exc
                        ) from exc
                    yield DecodedFrame(
                        image=image,
                        relative_seconds=relative,
                        absolute_datetime=recording.start + timedelta(seconds=relative),
                        recording=recording,
                    )
            except RecordingDecodeError:
                raise
            except _DECODE_EXCEPTIONS as exc:
                raise RecordingDecodeError("decode", self._resolved_path(recording), exc) from exc
            completed = True
        finally:
            if container is not None:
                self._close_input(
                    container,
                    recording,
                    completed=completed,
                    unwinding=not completed,
                )
