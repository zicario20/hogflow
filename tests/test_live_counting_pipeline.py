from __future__ import annotations

from dataclasses import replace

import pytest
from _phase5_2_helpers import StubStreamRunner, frame_packet, scripted_reads
from _phase5_4_helpers import tracked_object

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting import (
    CountingPreviewError,
    LifecycleDirectionalCounter,
    LiveCountingConfiguration,
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
    VirtualLineCrossingDetector,
)
from hogflow.detection import EmptyDetector, PreviewAction
from hogflow.pipeline import LiveCountingPipeline, LiveCrossingPipeline
from hogflow.streaming.models import BufferReadStatus
from hogflow.tracking import FailingTracker, ScriptedTracker


def _runner_for_batches(*batches: tuple[int, ...], reconnects: int = 0) -> StubStreamRunner:
    reads: list[object] = []
    total = 0
    for batch in batches:
        reads.extend(frame_packet(sequence) for sequence in batch)
        reads.append(BufferReadStatus.TIMEOUT)
        total += len(batch)
    reads.append(BufferReadStatus.CLOSED)
    runner = StubStreamRunner(scripted_reads(*reads), frames_acquired=total)
    if reconnects:
        original = runner.statistics
        runner.statistics = lambda: replace(original(), reconnect_count=reconnects)  # type: ignore[method-assign]
    return runner


def _crossing_configuration() -> LiveCrossingConfiguration:
    return LiveCrossingConfiguration(
        enabled=True,
        line=NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5)),
        epsilon=0.01,
        absent_track_retention_updates=2,
    )


def _counter(
    crossing: LiveCrossingConfiguration,
    *,
    positive_direction: LiveCrossingDirection = (LiveCrossingDirection.NEGATIVE_TO_POSITIVE),
) -> LifecycleDirectionalCounter:
    return LifecycleDirectionalCounter(
        LiveCountingConfiguration(
            enabled=True,
            positive_direction=positive_direction,
            crossing_configuration_fingerprint=crossing.fingerprint,
        )
    )


def _below(track_id: int = 1):
    return tracked_object(track_id, 1, 0.5, 3, 2)


def _above(track_id: int = 1):
    return tracked_object(track_id, 1, 3.5, 3, 5)


class CountingPreviewDouble:
    def __init__(self, *, fail: bool = False, stop: bool = False) -> None:
        self.fail = fail
        self.stop = stop
        self.closed = False
        self.sequences: list[int] = []

    def show_counting(
        self,
        frame,
        _detections,
        _tracking,
        _crossing,
        _counting,
        _detection_statistics,
        _tracking_statistics,
        _crossing_statistics,
        _counting_statistics,
    ):
        self.sequences.append(frame.sequence_number)
        if self.fail:
            raise CountingPreviewError("synthetic counting preview failure")
        return PreviewAction.STOP if self.stop else PreviewAction.CONTINUE

    def close(self) -> None:
        self.closed = True


class FailingCounter(LifecycleDirectionalCounter):
    def update(self, crossing):
        del crossing
        raise InputDataError("synthetic counting contract failure")


def test_live_counting_pipeline_counts_positive_after_crossing() -> None:
    crossing_configuration = _crossing_configuration()
    results = []
    summary = LiveCountingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        VirtualLineCrossingDetector(crossing_configuration),
        _counter(crossing_configuration),
        result_callback=lambda _frame, _detections, _tracking, _crossing, counting, _snapshot: (
            results.append(counting)
        ),
    ).run()

    assert [item.frame_increments for item in results] == [0, 1]
    assert summary.counting_statistics.positives_counted == 1
    assert summary.counting_statistics.lifecycle_directional_count == 1
    assert summary.source_id == "camera"
    assert summary.crossing_lifecycle_id.startswith("crossing-lifecycle-")
    assert summary.counting_lifecycle_id.startswith("counting-lifecycle-")
    assert any("not session counts" in item for item in summary.limitations)
    assert summary.counting_closed
    assert summary.crossing_summary.crossing_closed
    assert summary.crossing_summary.tracking_summary.tracker_closed
    assert summary.crossing_summary.tracking_summary.detection_summary.camera_released


def test_pipeline_classifies_reverse_and_duplicate_without_decrement() -> None:
    crossing_configuration = _crossing_configuration()
    summary = LiveCountingPipeline(
        _runner_for_batches((0,), (1,), (2,), (3,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker(
            {
                0: (_below(),),
                1: (_above(),),
                2: (_below(),),
                3: (_above(),),
            }
        ),
        VirtualLineCrossingDetector(crossing_configuration),
        _counter(crossing_configuration),
    ).run()

    statistics = summary.counting_statistics
    assert statistics.positives_counted == 1
    assert statistics.reverses == 1
    assert statistics.reverses_after_count == 1
    assert statistics.duplicate_positives == 1
    assert statistics.lifecycle_directional_count == 1


def test_pipeline_applies_two_positive_events_atomically_in_one_frame() -> None:
    crossing_configuration = _crossing_configuration()
    increments = []
    summary = LiveCountingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker(
            {
                0: (_below(2), _below(1)),
                1: (_above(2), _above(1)),
            }
        ),
        VirtualLineCrossingDetector(crossing_configuration),
        _counter(crossing_configuration),
        result_callback=lambda _frame, _detections, _tracking, _crossing, counting, _snapshot: (
            increments.append(counting.frame_increments)
        ),
    ).run()

    assert increments == [0, 2]
    assert summary.counting_statistics.lifecycle_directional_count == 2


def test_zero_events_and_temporary_tracker_failure_create_no_decision() -> None:
    crossing_configuration = _crossing_configuration()
    summary = LiveCountingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        FailingTracker(temporary_sequences=(1,)),
        VirtualLineCrossingDetector(crossing_configuration),
        _counter(crossing_configuration),
    ).run()

    assert summary.crossing_summary.tracking_summary.tracking_statistics.tracking_failures == 1
    assert summary.counting_statistics.crossing_results_processed == 1
    assert summary.counting_statistics.crossing_events_processed == 0
    assert summary.counting_statistics.lifecycle_directional_count == 0


def test_reconnect_resets_crossing_and_counting_before_next_result() -> None:
    crossing_configuration = _crossing_configuration()
    summary = LiveCountingPipeline(
        _runner_for_batches((0,), (1,), reconnects=1),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        VirtualLineCrossingDetector(crossing_configuration),
        _counter(crossing_configuration),
    ).run()

    assert summary.crossing_summary.tracking_summary.tracking_statistics.tracker_restarts == 1
    assert summary.crossing_summary.crossing_statistics.resets == 1
    assert summary.counting_statistics.resets == 1
    assert summary.counting_statistics.lifecycle_directional_count == 1


def test_counting_preview_failure_is_nonfatal_and_stop_is_cooperative() -> None:
    crossing_configuration = _crossing_configuration()
    failing = CountingPreviewDouble(fail=True)
    failure_summary = LiveCountingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        VirtualLineCrossingDetector(crossing_configuration),
        _counter(crossing_configuration),
        preview=failing,
    ).run()
    assert failure_summary.counting_statistics.preview_failures == 1
    assert failure_summary.counting_statistics.crossing_results_processed == 2
    assert failing.closed

    stopping = CountingPreviewDouble(stop=True)
    stopped_summary = LiveCountingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        VirtualLineCrossingDetector(crossing_configuration),
        _counter(crossing_configuration),
        preview=stopping,
    ).run()
    assert (
        stopped_summary.crossing_summary.tracking_summary.detection_summary.shutdown_reason.value
        == "preview_requested"
    )
    assert stopped_summary.counting_statistics.crossing_results_processed == 1
    assert stopping.closed


def test_result_callback_can_request_cooperative_stop() -> None:
    crossing_configuration = _crossing_configuration()
    summary = LiveCountingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        VirtualLineCrossingDetector(crossing_configuration),
        _counter(crossing_configuration),
        result_callback=lambda *_arguments: PreviewAction.STOP,
    ).run()

    assert (
        summary.crossing_summary.tracking_summary.detection_summary.shutdown_reason.value
        == "preview_requested"
    )
    assert summary.counting_statistics.crossing_results_processed == 1


def test_counting_failure_is_fatal_and_all_resources_close() -> None:
    crossing_configuration = _crossing_configuration()
    runner = _runner_for_batches((0,))
    tracker = ScriptedTracker({0: (_below(),)})
    crossing = VirtualLineCrossingDetector(crossing_configuration)
    counter = FailingCounter(
        LiveCountingConfiguration(
            enabled=True,
            positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
            crossing_configuration_fingerprint=crossing_configuration.fingerprint,
        )
    )

    with pytest.raises(InputDataError, match="contract failure"):
        LiveCountingPipeline(
            runner,  # type: ignore[arg-type]
            EmptyDetector(),
            tracker,
            crossing,
            counter,
        ).run()

    assert runner.stopped
    assert not tracker.is_started
    assert not crossing.is_started
    assert not counter.is_started


def test_counting_disabled_preserves_phase_5_4_pipeline_behavior() -> None:
    crossing_configuration = _crossing_configuration()
    summary = LiveCrossingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        VirtualLineCrossingDetector(crossing_configuration),
    ).run()

    assert summary.crossing_statistics.events_emitted == 1
    assert summary.crossing_closed


def test_pipeline_rejects_disabled_or_mismatched_counting_before_run() -> None:
    crossing_configuration = _crossing_configuration()
    crossing = VirtualLineCrossingDetector(crossing_configuration)

    with pytest.raises(ConfigurationError, match="enabled counting"):
        LiveCountingPipeline(
            _runner_for_batches((0,)),  # type: ignore[arg-type]
            EmptyDetector(),
            ScriptedTracker({}),
            crossing,
            LifecycleDirectionalCounter(LiveCountingConfiguration()),
        )

    with pytest.raises(ConfigurationError, match="fingerprint"):
        LiveCountingPipeline(
            _runner_for_batches((0,)),  # type: ignore[arg-type]
            EmptyDetector(),
            ScriptedTracker({}),
            crossing,
            LifecycleDirectionalCounter(
                LiveCountingConfiguration(
                    enabled=True,
                    positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
                    crossing_configuration_fingerprint="b" * 64,
                )
            ),
        )
