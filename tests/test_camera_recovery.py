from __future__ import annotations

from collections import deque
from time import monotonic, sleep

from _phase9_3_helpers import ScriptedCrossingProcessor, wait_for_status

from hogflow.bootstrap import OPERATOR_LANE_SOURCE_ID, build_operator_runtime
from hogflow.camera import (
    CameraRecoveryConfiguration,
    CameraStatus,
    CountingPipelineStatus,
    PipelineFailureCategory,
)
from hogflow.streaming import (
    FrameDimensions,
    FramePayload,
    SourceFrame,
    SourceType,
    StreamConfiguration,
    StreamIdentity,
    StreamReadResult,
    StreamReadStatus,
)
from hogflow.streaming.errors import StreamOpenError


class RecoverableSource:
    def __init__(
        self,
        *,
        open_failures: int = 0,
        results: tuple[StreamReadResult, ...] = (),
        is_live: bool = True,
    ) -> None:
        self._identity = StreamIdentity(
            OPERATOR_LANE_SOURCE_ID,
            SourceType.USB if is_live else SourceType.FILE,
            "Synthetic recovery source",
        )
        self._open = False
        self._open_failures = open_failures
        self._results = deque(results)
        self._is_live = is_live
        self.open_calls = 0
        self.close_calls = 0

    @property
    def identity(self) -> StreamIdentity:
        return self._identity

    @property
    def is_live(self) -> bool:
        return self._is_live

    def open(self) -> None:
        self.open_calls += 1
        if self.open_calls <= self._open_failures:
            raise StreamOpenError("synthetic unavailable source")
        self._open = True

    def read(self) -> StreamReadResult:
        if not self._open:
            return StreamReadResult(StreamReadStatus.STOPPED)
        if self._results:
            return self._results.popleft()
        return StreamReadResult(StreamReadStatus.TEMPORARY_UNAVAILABLE, retry_after_seconds=1)

    def close(self) -> None:
        if self._open:
            self.close_calls += 1
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def health(self):
        raise NotImplementedError

    def statistics(self):
        raise NotImplementedError


def frame_result() -> StreamReadResult:
    dimensions = FrameDimensions(4, 2, 3)
    return StreamReadResult(
        StreamReadStatus.FRAME,
        SourceFrame(dimensions, FramePayload(bytes(24))),
    )


def recovery_runtime(source: RecoverableSource, processor: ScriptedCrossingProcessor):
    return build_operator_runtime(
        source_factory=lambda _configuration: source,
        processor_factory=lambda: processor,
        recovery_configuration=CameraRecoveryConfiguration(
            max_reopen_attempts=2,
            temporary_failures_before_reopen=2,
            retry_delay_seconds=0,
        ),
    )


def test_camera_open_recovery_is_bounded_and_pipeline_resumes() -> None:
    source = RecoverableSource(
        open_failures=1,
        results=(frame_result(), StreamReadResult(StreamReadStatus.END_OF_STREAM)),
    )
    processor = ScriptedCrossingProcessor()
    runtime = recovery_runtime(source, processor)
    runtime.counting_pipeline.configure(StreamConfiguration.usb(OPERATOR_LANE_SOURCE_ID, 0))

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert source.open_calls == 2
    assert snapshot.recovery_attempts == 1
    assert snapshot.recovery_successes == 1
    assert snapshot.frames_processed == 1
    assert snapshot.camera.status is CameraStatus.ENDED


def test_temporary_camera_loss_reopens_resets_processor_and_continues() -> None:
    unavailable = StreamReadResult(
        StreamReadStatus.TEMPORARY_UNAVAILABLE,
        retry_after_seconds=0,
    )
    source = RecoverableSource(
        results=(
            unavailable,
            unavailable,
            frame_result(),
            StreamReadResult(StreamReadStatus.END_OF_STREAM),
        )
    )
    processor = ScriptedCrossingProcessor()
    runtime = recovery_runtime(source, processor)
    runtime.counting_pipeline.configure(StreamConfiguration.usb(OPERATOR_LANE_SOURCE_ID, 0))

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert source.open_calls == 2
    assert source.close_calls == 2
    assert processor.resets == 1
    assert snapshot.recovery_attempts == 1
    assert snapshot.recovery_successes == 1
    assert snapshot.frames_processed == 1


def test_camera_disconnected_state_is_observable_before_recovery_threshold() -> None:
    source = RecoverableSource()
    processor = ScriptedCrossingProcessor()
    runtime = build_operator_runtime(
        source_factory=lambda _configuration: source,
        processor_factory=lambda: processor,
        recovery_configuration=CameraRecoveryConfiguration(
            max_reopen_attempts=1,
            temporary_failures_before_reopen=100,
            retry_delay_seconds=0,
        ),
    )
    runtime.counting_pipeline.configure(StreamConfiguration.usb(OPERATOR_LANE_SOURCE_ID, 0))
    runtime.counting_pipeline.start()
    deadline = monotonic() + 1
    while (
        runtime.counting_pipeline.snapshot().camera.status is not CameraStatus.DISCONNECTED
        and monotonic() < deadline
    ):
        sleep(0.005)

    assert runtime.counting_pipeline.snapshot().camera.status is CameraStatus.DISCONNECTED
    runtime.counting_pipeline.stop()


def test_exhausted_open_recovery_fails_without_endless_loop() -> None:
    source = RecoverableSource(open_failures=99)
    runtime = recovery_runtime(source, ScriptedCrossingProcessor())
    runtime.counting_pipeline.configure(StreamConfiguration.usb(OPERATOR_LANE_SOURCE_ID, 0))

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.FAILED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert source.open_calls == 3
    assert snapshot.recovery_attempts == 2
    assert snapshot.recovery_successes == 0
    assert snapshot.failure_category is PipelineFailureCategory.SOURCE_OPEN


def test_local_file_failure_is_not_reopened(tmp_path) -> None:
    path = tmp_path / "synthetic.mp4"
    path.write_bytes(b"synthetic")
    source = RecoverableSource(
        results=(StreamReadResult(StreamReadStatus.STOPPED),),
        is_live=False,
    )
    runtime = recovery_runtime(source, ScriptedCrossingProcessor())
    runtime.counting_pipeline.configure(StreamConfiguration.file(OPERATOR_LANE_SOURCE_ID, path))

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.FAILED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert source.open_calls == 1
    assert snapshot.recovery_attempts == 0
    assert snapshot.failure_category is PipelineFailureCategory.SOURCE_READ
