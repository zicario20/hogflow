"""Small synchronous/threaded runner for continuous camera acquisition."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Lock, Thread
from time import monotonic
from typing import Callable

from hogflow.core import get_logger
from hogflow.streaming.buffering import BoundedFrameBuffer
from hogflow.streaming.configuration import ReconnectPolicy, StreamConfiguration
from hogflow.streaming.contracts import CameraSource
from hogflow.streaming.errors import (
    BufferClosedError,
    StreamFatalReadError,
    StreamLifecycleError,
    StreamOpenError,
)
from hogflow.streaming.health import StreamHealthMonitor
from hogflow.streaming.models import (
    FramePacket,
    FrameTimestamp,
    StreamErrorCategory,
    StreamHealth,
    StreamHealthState,
    StreamReadStatus,
    StreamStatistics,
)

LOGGER = get_logger(__name__)


class LiveStreamRunner:
    """Acquire continuously, sequence frames, buffer them, and reconnect.

    The runner performs no detection, tracking, counting, drawing, persistence,
    or remote transmission. ``run`` is synchronous and deterministic under
    injected clocks/sleep; ``start`` is a small optional thread wrapper so a
    downstream consumer can read from the bounded buffer concurrently.
    """

    def __init__(
        self,
        source: CameraSource,
        buffer: BoundedFrameBuffer,
        configuration: StreamConfiguration,
        reconnect_policy: ReconnectPolicy | None = None,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], object] | None = None,
    ) -> None:
        if source.identity != configuration.identity:
            raise StreamLifecycleError("Source identity does not match stream configuration.")
        self._source = source
        self._buffer = buffer
        self._configuration = configuration
        self._reconnect = reconnect_policy or ReconnectPolicy()
        self._monotonic = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._stop_event = Event()
        self._sleeper = sleeper or self._stop_event.wait
        self._monitor = StreamHealthMonitor(
            configuration.identity,
            monotonic_clock=monotonic_clock,
        )
        self._sequence = 0
        self._last_packet_time: float | None = None
        self._thread: Thread | None = None
        self._failure: BaseException | None = None
        self._lifecycle_lock = Lock()
        self._running = False
        self._started = False

    @property
    def buffer(self) -> BoundedFrameBuffer:
        """Return the bounded consumer boundary owned by this run."""

        return self._buffer

    def start(self) -> None:
        """Start acquisition on one background producer thread."""

        with self._lifecycle_lock:
            if self._started:
                raise StreamLifecycleError("Live stream runner supports one lifecycle only.")
            self._started = True
            self._running = True
            self._thread = Thread(
                target=self._thread_main,
                name=f"hogflow-stream-{self._configuration.stream_id}",
                daemon=True,
            )
            self._thread.start()

    def run(self) -> None:
        """Run acquisition synchronously until EOF, stop, or failure."""

        with self._lifecycle_lock:
            if self._started:
                raise StreamLifecycleError("Live stream runner supports one lifecycle only.")
            self._started = True
            self._running = True
        try:
            self._run_loop()
        finally:
            with self._lifecycle_lock:
                self._running = False

    def stop(self) -> None:
        """Request cooperative shutdown and unblock waiting consumers.

        The producer normally finishes its active read and releases the source
        from the acquisition thread. ``join`` falls back to cross-thread close
        only when a read remains blocked beyond a short grace period.
        """

        self._stop_event.set()
        self._buffer.close()

    def join(self, timeout_seconds: float | None = None, *, raise_on_failure: bool = False) -> bool:
        """Wait for a background run and optionally re-raise its failure."""

        thread = self._thread
        if thread is None:
            return True
        started_at = monotonic()
        if self._stop_event.is_set():
            cooperative_grace = 0.25
            if timeout_seconds is not None:
                cooperative_grace = min(cooperative_grace, max(0.0, timeout_seconds))
            thread.join(cooperative_grace)
            if thread.is_alive():
                self._source.close()
                remaining = (
                    None
                    if timeout_seconds is None
                    else max(0.0, timeout_seconds - (monotonic() - started_at))
                )
                thread.join(remaining)
        else:
            thread.join(timeout_seconds)
        finished = not thread.is_alive()
        if finished and raise_on_failure and self._failure is not None:
            raise self._failure
        return finished

    def is_running(self) -> bool:
        """Return whether the acquisition loop is active."""

        with self._lifecycle_lock:
            return self._running

    def health(self) -> StreamHealth:
        """Return runner health merged with current buffer depth."""

        return self._monitor.health(self._buffer.statistics())

    def statistics(self) -> StreamStatistics:
        """Return runner and buffer aggregate statistics."""

        return self._monitor.statistics(self._buffer.statistics())

    @property
    def failure(self) -> BaseException | None:
        """Return a captured background failure without logging its text."""

        return self._failure

    def _thread_main(self) -> None:
        try:
            self._run_loop()
        except BaseException as exc:
            self._failure = exc
        finally:
            with self._lifecycle_lock:
                self._running = False

    def _run_loop(self) -> None:
        reconnect_attempt = 0
        stable_since: float | None = None
        failed = False
        try:
            while not self._stop_event.is_set():
                self._monitor.record_open_attempt()
                try:
                    self._source.open()
                except StreamOpenError:
                    self._monitor.record_fatal_failure(StreamErrorCategory.OPEN)
                    if not self._schedule_reconnect(reconnect_attempt + 1):
                        failed = True
                        break
                    reconnect_attempt += 1
                    continue
                self._monitor.record_open_success()
                stable_since = float(self._monotonic())
                reconnect_required = False
                while not self._stop_event.is_set():
                    try:
                        result = self._source.read()
                    except StreamFatalReadError:
                        self._monitor.record_fatal_failure(StreamErrorCategory.READ)
                        reconnect_required = self._source.is_live
                        break
                    if result.status is StreamReadStatus.FRAME:
                        source_frame = result.frame
                        if source_frame is None:
                            raise StreamLifecycleError("Successful source read omitted its frame.")
                        now = float(self._monotonic())
                        if self._last_packet_time is not None and now < self._last_packet_time:
                            raise StreamLifecycleError("Monotonic clock moved backward.")
                        self._last_packet_time = now
                        packet = FramePacket(
                            stream=self._configuration.identity,
                            sequence_number=self._sequence,
                            timestamp=FrameTimestamp(
                                acquired_at=self._wall_clock(),
                                monotonic_seconds=now,
                                source_seconds=source_frame.source_timestamp_seconds,
                            ),
                            dimensions=source_frame.dimensions,
                            payload=source_frame.payload,
                        )
                        self._monitor.record_frame(
                            source_frame.dimensions,
                            sequence_number=self._sequence,
                            at_monotonic=now,
                        )
                        self._sequence += 1
                        try:
                            self._buffer.submit(packet)
                        except BufferClosedError:
                            if self._stop_event.is_set():
                                break
                            raise
                        if (
                            stable_since is not None
                            and now - stable_since >= self._reconnect.reset_after_stable_seconds
                        ):
                            reconnect_attempt = 0
                            stable_since = now
                        continue
                    if result.status is StreamReadStatus.TEMPORARY_UNAVAILABLE:
                        failures = self._monitor.record_temporary_failure()
                        if failures >= self._configuration.consecutive_failure_limit:
                            reconnect_required = self._source.is_live
                            break
                        delay = max(
                            result.retry_after_seconds,
                            self._configuration.temporary_retry_delay_seconds,
                        )
                        self._sleeper(delay)
                        continue
                    if result.status is StreamReadStatus.INTERRUPTED:
                        self._monitor.record_temporary_failure(StreamErrorCategory.INTERRUPTED)
                        reconnect_required = self._source.is_live
                        break
                    if result.status is StreamReadStatus.END_OF_STREAM:
                        reconnect_required = self._source.is_live
                        if reconnect_required:
                            self._monitor.record_temporary_failure(StreamErrorCategory.INTERRUPTED)
                        break
                    if result.status is StreamReadStatus.STOPPED:
                        break

                self._source.close()
                if self._stop_event.is_set():
                    break
                if reconnect_required:
                    if not self._schedule_reconnect(reconnect_attempt + 1):
                        failed = True
                        break
                    reconnect_attempt += 1
                    continue
                break
        except BaseException:
            failed = True
            self._monitor.record_fatal_failure(StreamErrorCategory.INTERNAL)
            raise
        finally:
            self._source.close()
            self._buffer.close()
            if failed:
                self._monitor.transition(
                    StreamHealthState.FAILED, self.health().last_error_category
                )
            else:
                self._monitor.transition(StreamHealthState.STOPPED)

    def _schedule_reconnect(self, attempt_number: int) -> bool:
        if not self._source.is_live or not self._reconnect.permits(attempt_number):
            return False
        self._source.close()
        self._monitor.record_reconnect()
        delay = self._reconnect.delay_for_attempt(attempt_number)
        LOGGER.debug(
            "Scheduling reconnect for %s at attempt %d after %.3f seconds",
            self._configuration.identity.display_name,
            attempt_number,
            delay,
        )
        self._sleeper(delay)
        return not self._stop_event.is_set()

    def __enter__(self) -> LiveStreamRunner:
        self.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.stop()
        self.join(5.0)


__all__ = ["LiveStreamRunner"]
