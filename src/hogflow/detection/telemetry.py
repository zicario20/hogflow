"""Thread-safe bounded telemetry aggregation for live detector inference."""

from __future__ import annotations

from collections import deque
from math import ceil, isfinite
from threading import RLock
from time import monotonic
from typing import Callable

from hogflow.core import InputDataError
from hogflow.detection.inference import FrameDetections, LiveDetectionStats
from hogflow.streaming.models import StreamStatistics


class LiveDetectionTelemetry:
    """Aggregate inference telemetry without retaining frames or detections.

    Average latency covers all successful inference calls. Percentiles use a
    bounded recent sample window so an unbounded stream cannot grow memory.
    """

    def __init__(
        self,
        latency_sample_capacity: int = 512,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if (
            not isinstance(latency_sample_capacity, int)
            or isinstance(latency_sample_capacity, bool)
            or latency_sample_capacity <= 0
        ):
            raise InputDataError("Latency sample capacity must be a positive integer.")
        self._clock = monotonic_clock
        self._started_at = float(self._clock())
        self._lock = RLock()
        self._latencies: deque[float] = deque(maxlen=latency_sample_capacity)
        self._latency_sum = 0.0
        self._submitted = 0
        self._inferred = 0
        self._skipped = 0
        self._failures = 0
        self._detections = 0
        self._preview_failures = 0
        self._latest_age: float | None = None
        self._maximum_age = 0.0

    def record_submitted(self, frame_age_ms: float) -> None:
        """Record one frame crossing the detector scheduling boundary."""

        age = _non_negative(frame_age_ms, "Frame age")
        with self._lock:
            self._submitted += 1
            self._record_frame_age(age)

    def record_skipped(self, count: int = 1) -> None:
        """Record intentionally skipped source frames."""

        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise InputDataError("Skipped-frame count must be a positive integer.")
        with self._lock:
            self._skipped += count

    def record_inference(self, result: FrameDetections, frame_age_ms: float) -> None:
        """Record one successful framework-neutral detector result."""

        if not isinstance(result, FrameDetections):
            raise InputDataError("Inference telemetry requires FrameDetections.")
        age = _non_negative(frame_age_ms, "Frame age")
        with self._lock:
            self._record_frame_age(age)
            self._inferred += 1
            self._detections += len(result.detections)
            self._latency_sum += result.inference_duration_ms
            self._latencies.append(result.inference_duration_ms)

    def _record_frame_age(self, age: float) -> None:
        self._latest_age = age
        self._maximum_age = max(self._maximum_age, age)

    def record_failure(self) -> None:
        """Record one attempted inference that did not produce a result."""

        with self._lock:
            self._failures += 1

    def record_preview_failure(self) -> None:
        """Record a local preview failure without storing exception text."""

        with self._lock:
            self._preview_failures += 1

    def snapshot(self, camera: StreamStatistics) -> LiveDetectionStats:
        """Merge bounded detector telemetry with camera acquisition counters."""

        if not isinstance(camera, StreamStatistics):
            raise InputDataError("Detection telemetry requires StreamStatistics.")
        with self._lock:
            latencies = tuple(self._latencies)
            average = self._latency_sum / self._inferred if self._inferred else 0.0
            runtime = max(0.0, float(self._clock()) - self._started_at)
            effective_fps = self._inferred / runtime if runtime > 0 else 0.0
            return LiveDetectionStats(
                frames_acquired=camera.frames_acquired,
                frames_submitted=self._submitted,
                frames_inferred=self._inferred,
                frames_skipped=self._skipped,
                source_frames_dropped=camera.frames_dropped,
                inference_failures=self._failures,
                total_detections=self._detections,
                preview_failures=self._preview_failures,
                average_inference_ms=average,
                p50_inference_ms=_percentile(latencies, 0.50),
                p95_inference_ms=_percentile(latencies, 0.95),
                effective_inference_fps=effective_fps,
                camera_fps=camera.observed_fps,
                latest_frame_age_ms=self._latest_age,
                maximum_frame_age_ms=self._maximum_age,
            )


def _non_negative(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or value < 0
    ):
        raise InputDataError(f"{name} must be a non-negative number.")
    return float(value)


def _percentile(values: tuple[float, ...], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, ceil(quantile * len(ordered)) - 1)
    return ordered[index]


__all__ = ["LiveDetectionTelemetry"]
