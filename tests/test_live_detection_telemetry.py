from datetime import datetime, timezone

import pytest

from hogflow.core import InputDataError
from hogflow.detection.inference import FrameDetections
from hogflow.detection.telemetry import LiveDetectionTelemetry
from hogflow.streaming.models import StreamStatistics


def _result(duration_ms: float) -> FrameDetections:
    timestamp = datetime(2026, 7, 18, tzinfo=timezone.utc)
    return FrameDetections(
        source_id="camera",
        frame_sequence=0,
        captured_at=timestamp,
        inference_started_at=timestamp,
        inference_completed_at=timestamp,
        frame_width=8,
        frame_height=6,
        detections=(),
        model_id="model",
        model_version=None,
        artifact_fingerprint=None,
        inference_duration_ms=duration_ms,
    )


def test_telemetry_uses_bounded_latency_samples_and_all_time_average() -> None:
    times = iter((0.0, 2.0))
    telemetry = LiveDetectionTelemetry(2, monotonic_clock=lambda: next(times))
    for duration in (10.0, 20.0, 30.0):
        telemetry.record_submitted(5.0)
        telemetry.record_inference(_result(duration), frame_age_ms=7.0)

    stats = telemetry.snapshot(StreamStatistics(frames_acquired=4, frames_dropped=1))

    assert stats.average_inference_ms == pytest.approx(20.0)
    assert stats.p50_inference_ms == 20.0
    assert stats.p95_inference_ms == 30.0
    assert stats.effective_inference_fps == pytest.approx(1.5)
    assert stats.source_frames_dropped == 1


def test_telemetry_rejects_non_finite_frame_age() -> None:
    telemetry = LiveDetectionTelemetry()

    with pytest.raises(InputDataError):
        telemetry.record_submitted(float("inf"))
