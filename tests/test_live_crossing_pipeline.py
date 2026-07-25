from __future__ import annotations

from dataclasses import replace

import pytest
from _phase5_2_helpers import StubStreamRunner, frame_packet, scripted_reads
from _phase5_4_helpers import tracked_object

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting import (
    CrossingPreviewError,
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
    VirtualLineCrossingDetector,
)
from hogflow.detection import EmptyDetector, PreviewAction
from hogflow.pipeline import LiveCrossingPipeline, LiveTrackingPipeline
from hogflow.streaming.models import BufferReadStatus
from hogflow.tracking import EmptyTracker, FailingTracker, ScriptedTracker


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


def _configuration() -> LiveCrossingConfiguration:
    return LiveCrossingConfiguration(
        enabled=True,
        line=NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5)),
        epsilon=0.01,
        absent_track_retention_updates=2,
    )


def _below(track_id: int = 1):
    return tracked_object(track_id, 1, 0.5, 3, 2)


def _above(track_id: int = 1):
    return tracked_object(track_id, 1, 3.5, 3, 5)


class CrossingPreviewDouble:
    def __init__(self, *, fail: bool = False, stop: bool = False) -> None:
        self.fail = fail
        self.stop = stop
        self.closed = False
        self.sequences: list[int] = []

    def show_crossing(
        self,
        frame,
        _detections,
        _tracking,
        _crossing,
        _detection_statistics,
        _tracking_statistics,
        _crossing_statistics,
    ):
        self.sequences.append(frame.sequence_number)
        if self.fail:
            raise CrossingPreviewError("synthetic crossing preview failure")
        return PreviewAction.STOP if self.stop else PreviewAction.CONTINUE

    def close(self) -> None:
        self.closed = True


class FailingCrossingDetector(VirtualLineCrossingDetector):
    def update(self, tracking):
        super().update(tracking)
        raise InputDataError("synthetic crossing contract failure")


def test_live_crossing_pipeline_emits_event_after_tracking() -> None:
    events = []
    crossing = VirtualLineCrossingDetector(_configuration())
    summary = LiveCrossingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        crossing,
        result_callback=lambda _frame, _detections, _tracking, result, _snapshot: events.extend(
            result.events
        ),
    ).run()

    assert len(events) == 1
    assert events[0].direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE
    assert summary.crossing_statistics.events_emitted == 1
    assert summary.crossing_statistics.successful_results == 2
    assert summary.crossing_closed
    assert summary.tracking_summary.tracker_closed
    assert summary.tracking_summary.detection_summary.camera_released


def test_pipeline_supports_zero_tracks_and_multiple_events() -> None:
    crossing = VirtualLineCrossingDetector(_configuration())
    summary = LiveCrossingPipeline(
        _runner_for_batches((0,), (1,), (2,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker(
            {
                1: (_below(1), _above(2)),
                2: (_above(1), _below(2)),
            }
        ),
        crossing,
    ).run()

    assert summary.crossing_statistics.requests_processed == 3
    assert summary.crossing_statistics.events_emitted == 2
    assert summary.crossing_statistics.negative_to_positive_events == 1
    assert summary.crossing_statistics.positive_to_negative_events == 1


def test_temporary_tracker_failure_cannot_create_crossing_event() -> None:
    summary = LiveCrossingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        FailingTracker(temporary_sequences=(0,)),
        VirtualLineCrossingDetector(_configuration()),
    ).run()

    assert summary.tracking_summary.tracking_statistics.tracking_failures == 1
    assert summary.crossing_statistics.requests_processed == 1
    assert summary.crossing_statistics.events_emitted == 0


def test_reconnect_resets_tracker_and_crossing_before_next_result() -> None:
    crossing = VirtualLineCrossingDetector(_configuration())
    summary = LiveCrossingPipeline(
        _runner_for_batches((0,), reconnects=1),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_above(),)}),
        crossing,
    ).run()

    assert summary.tracking_summary.tracking_statistics.tracker_restarts == 1
    assert summary.crossing_statistics.resets == 1
    assert summary.crossing_statistics.events_emitted == 0


def test_crossing_preview_failure_is_nonfatal_and_stop_is_cooperative() -> None:
    failing = CrossingPreviewDouble(fail=True)
    failure_summary = LiveCrossingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        VirtualLineCrossingDetector(_configuration()),
        preview=failing,
    ).run()
    assert failure_summary.crossing_statistics.preview_failures == 1
    assert failure_summary.crossing_statistics.successful_results == 2
    assert failing.closed

    stopping = CrossingPreviewDouble(stop=True)
    stopped_summary = LiveCrossingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        ScriptedTracker({0: (_below(),), 1: (_above(),)}),
        VirtualLineCrossingDetector(_configuration()),
        preview=stopping,
    ).run()
    assert stopped_summary.tracking_summary.detection_summary.shutdown_reason.value == (
        "preview_requested"
    )
    assert stopped_summary.crossing_statistics.successful_results == 1
    assert stopping.closed


def test_crossing_contract_failure_is_fatal_and_resources_close() -> None:
    runner = _runner_for_batches((0,))
    tracker = ScriptedTracker({0: (_below(),)})
    crossing = FailingCrossingDetector(_configuration())

    with pytest.raises(InputDataError, match="contract failure"):
        LiveCrossingPipeline(
            runner,  # type: ignore[arg-type]
            EmptyDetector(),
            tracker,
            crossing,
        ).run()

    assert runner.stopped
    assert not tracker.is_started
    assert not crossing.is_started


def test_disabled_crossing_preserves_phase_5_3_pipeline_behavior() -> None:
    summary = LiveTrackingPipeline(
        _runner_for_batches((0,)),  # type: ignore[arg-type]
        EmptyDetector(),
        EmptyTracker(),
    ).run()

    assert summary.tracking_statistics.tracking_successes == 1
    assert summary.tracker_closed


def test_live_crossing_pipeline_rejects_disabled_configuration() -> None:
    with pytest.raises(ConfigurationError, match="enabled"):
        LiveCrossingPipeline(
            _runner_for_batches((0,)),  # type: ignore[arg-type]
            EmptyDetector(),
            EmptyTracker(),
            VirtualLineCrossingDetector(LiveCrossingConfiguration()),
        )
