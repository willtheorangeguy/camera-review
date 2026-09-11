from __future__ import annotations

import errno
import logging
import platform
import time
from collections.abc import Iterator
from contextlib import suppress
from datetime import timedelta
from fractions import Fraction
from pathlib import Path

import av
from av.codec.hwaccel import HWAccel

from ..errors import DetectorUnavailableError
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

HARDWARE_DECODERS = {
    "cuda",
    "d3d11va",
    "d3d12va",
    "dxva2",
    "qsv",
    "vaapi",
    "videotoolbox",
    "vdpau",
}


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
        self.active_hwdecode: str | None = "none" if hwdecode == "none" else None
        self._auto_fell_back = False

    @property
    def decoder_name(self) -> str:
        if self.active_hwdecode is None:
            return "hardware selection pending"
        if self.active_hwdecode == "none":
            return "CPU (automatic hardware fallback)" if self._auto_fell_back else "CPU"
        return f"{self.active_hwdecode} hardware acceleration"

    @staticmethod
    def _auto_hardware_candidates() -> tuple[str, ...]:
        system = platform.system()
        if system == "Windows":
            return ("cuda", "d3d11va", "d3d12va", "dxva2", "qsv")
        if system == "Darwin":
            return ("videotoolbox",)
        if system == "Linux":
            return ("cuda", "vaapi", "qsv", "vdpau")
        return ("cuda", "vaapi", "qsv")

    @staticmethod
    def _video_stream(container: av.container.InputContainer) -> av.video.stream.VideoStream:
        if not container.streams.video:
            raise ValueError("file contains no video stream")
        return container.streams.video[0]

    @staticmethod
    def _resolved_path(recording: RecordingFile) -> Path:
        """Return an absolute native-library-safe path, including on mapped drives."""
        return recording.path.expanduser().resolve()

    @staticmethod
    def _open_candidate(path: Path, backend: str) -> av.container.InputContainer:
        if backend == "none":
            return av.open(str(path))
        return av.open(
            str(path),
            hwaccel=HWAccel(backend, allow_software_fallback=False),
        )

    def _probe_hardware_backend(self, recording: RecordingFile, backend: str) -> None:
        """Prove that a backend can decode and transfer one frame for this codec."""
        container: av.container.InputContainer | None = None
        try:
            container = self._open_candidate(self._resolved_path(recording), backend)
            stream = self._video_stream(container)
            frame = next(container.decode(stream), None)
            if frame is None:
                raise RuntimeError("recording contains no decodable video frame")
            if not stream.codec_context.is_hwaccel:
                raise RuntimeError("decoder opened without hardware acceleration")
            # CamReview needs CPU-addressable BGR frames for OpenCV. Some
            # accelerators can decode but cannot transfer their frames.
            frame.to_ndarray(format="bgr24")
        finally:
            if container is not None:
                with suppress(OSError, av.error.FFmpegError):
                    container.close()

    def _select_hardware(self, recording: RecordingFile) -> None:
        if self.active_hwdecode is not None:
            return
        candidates = (
            self._auto_hardware_candidates() if self.hwdecode == "auto" else (self.hwdecode,)
        )
        failures: list[str] = []
        for backend in candidates:
            try:
                self._probe_hardware_backend(recording, backend)
            except Exception as exc:
                failures.append(f"{backend}: {exc}")
                LOG.debug("Hardware decoder %s was unavailable: %s", backend, exc)
                continue
            self.active_hwdecode = backend
            LOG.info("Selected %s hardware video decoding", backend)
            return
        if self.hwdecode == "auto":
            self.active_hwdecode = "none"
            self._auto_fell_back = True
            LOG.warning("No compatible hardware video decoder was available; using CPU decoding")
            return
        detail = failures[0] if failures else f"{self.hwdecode}: unavailable"
        raise DetectorUnavailableError(
            f"Hardware video decoder {self.hwdecode!r} is unavailable for "
            f"{recording.relative_path} ({detail}). Use --hwdecode auto or none."
        )

    def _open(self, recording: RecordingFile) -> av.container.InputContainer:
        """Open a recording, retrying brief SMB/network interruptions."""
        self._select_hardware(recording)
        path = self._resolved_path(recording)
        backend = self.active_hwdecode or "none"
        for attempt in range(3):
            try:
                return self._open_candidate(path, backend)
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

                # An automatically selected backend may support the first
                # recording's codec/profile but not a later one. Fall back once
                # to CPU before treating that recording as unreadable.
                if (
                    self.hwdecode == "auto"
                    and self.active_hwdecode not in {None, "none"}
                    and not failure.retryable
                    and not yielded_this_attempt
                    and last_successful is None
                ):
                    LOG.warning(
                        "%s hardware decoding failed for %s; retrying this and "
                        "subsequent recordings on CPU: %s",
                        self.active_hwdecode,
                        recording.relative_path,
                        failure.cause,
                    )
                    self.active_hwdecode = "none"
                    self._auto_fell_back = True
                    use_seek = resume_at > 1.0
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
