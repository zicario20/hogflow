"""Deterministic framework-free live detectors for tests and diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from math import isfinite
from time import monotonic, sleep
from typing import Callable

from hogflow.core import InputDataError
from hogflow.detection.errors import (
    DetectorLifecycleError,
    FatalInferenceError,
    TemporaryInferenceError,
)
from hogflow.detection.inference import FrameDetections, ModelArtifactMetadata
from hogflow.models import BoundingBox, Detection
from hogflow.streaming.models import FramePacket


class EmptyDetector:
    """Return no detections while exercising the complete detector lifecycle."""

    def __init__(
        self,
        *,
        model_id: str = "empty-detector",
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._metadata = ModelArtifactMetadata(
            model_id=model_id,
            framework="synthetic",
            class_mapping=((0, "pig"),),
            model_version="1",
            pig_detection_provenance_complete=False,
        )
        self._monotonic = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._loaded = False
        self.inferred_sequences: list[int] = []

    @property
    def metadata(self) -> ModelArtifactMetadata:
        return self._metadata

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self._loaded = True

    def infer(self, frame: FramePacket) -> FrameDetections:
        self._require_loaded(frame)
        started_monotonic = float(self._monotonic())
        started_at = self._wall_clock()
        detections = self._detections_for(frame)
        completed_monotonic = float(self._monotonic())
        completed_at = self._wall_clock()
        self.inferred_sequences.append(frame.sequence_number)
        return FrameDetections(
            source_id=frame.stream.stream_id,
            frame_sequence=frame.sequence_number,
            captured_at=frame.timestamp.acquired_at,
            inference_started_at=started_at,
            inference_completed_at=completed_at,
            frame_width=frame.dimensions.width,
            frame_height=frame.dimensions.height,
            detections=detections,
            model_id=self.metadata.model_id,
            model_version=self.metadata.model_version,
            artifact_fingerprint=self.metadata.artifact_fingerprint,
            inference_duration_ms=max(0.0, completed_monotonic - started_monotonic) * 1000,
        )

    def close(self) -> None:
        self._loaded = False

    def _detections_for(self, _frame: FramePacket) -> tuple[Detection, ...]:
        return ()

    def _require_loaded(self, frame: FramePacket) -> None:
        if not self._loaded:
            raise DetectorLifecycleError("Detector must be loaded before live inference.")
        if not isinstance(frame, FramePacket):
            raise InputDataError("Live detector input must be a FramePacket.")


class ScriptedDetector(EmptyDetector):
    """Return predefined immutable detections for selected frame sequences."""

    def __init__(
        self,
        detections_by_sequence: Mapping[int, tuple[Detection, ...]],
        **settings: object,
    ) -> None:
        if not isinstance(detections_by_sequence, Mapping):
            raise InputDataError("Scripted detections must be a sequence mapping.")
        values: dict[int, tuple[Detection, ...]] = {}
        for sequence, detections in detections_by_sequence.items():
            if (
                not isinstance(sequence, int)
                or isinstance(sequence, bool)
                or sequence < 0
                or not isinstance(detections, tuple)
                or not all(isinstance(item, Detection) for item in detections)
            ):
                raise InputDataError("Scripted detector entries must map sequences to tuples.")
            values[sequence] = detections
        super().__init__(model_id="scripted-detector", **settings)
        self._script = values

    def _detections_for(self, frame: FramePacket) -> tuple[Detection, ...]:
        return self._script.get(frame.sequence_number, ())


class SlowDetector(ScriptedDetector):
    """Simulate bounded slow inference without a CV or ML dependency."""

    def __init__(
        self,
        detections_by_sequence: Mapping[int, tuple[Detection, ...]] | None = None,
        *,
        delay_seconds: float = 0.05,
        sleeper: Callable[[float], object] = sleep,
        **settings: object,
    ) -> None:
        if (
            not isinstance(delay_seconds, (int, float))
            or isinstance(delay_seconds, bool)
            or not isfinite(delay_seconds)
            or delay_seconds < 0
        ):
            raise InputDataError("Slow-detector delay must be non-negative.")
        super().__init__(detections_by_sequence or {}, **settings)
        self._delay = float(delay_seconds)
        self._sleeper = sleeper

    def _detections_for(self, frame: FramePacket) -> tuple[Detection, ...]:
        self._sleeper(self._delay)
        return super()._detections_for(frame)


class FailingDetector(ScriptedDetector):
    """Raise configured temporary or fatal failures by source sequence."""

    def __init__(
        self,
        *,
        temporary_sequences: tuple[int, ...] = (),
        fatal_sequences: tuple[int, ...] = (),
        detections_by_sequence: Mapping[int, tuple[Detection, ...]] | None = None,
        **settings: object,
    ) -> None:
        for values in (temporary_sequences, fatal_sequences):
            if not isinstance(values, tuple) or not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in values
            ):
                raise InputDataError("Failure sequences must be immutable non-negative integers.")
        if set(temporary_sequences) & set(fatal_sequences):
            raise InputDataError("A sequence cannot be both temporarily and fatally failing.")
        super().__init__(detections_by_sequence or {}, **settings)
        self._temporary = frozenset(temporary_sequences)
        self._fatal = frozenset(fatal_sequences)

    def infer(self, frame: FramePacket) -> FrameDetections:
        self._require_loaded(frame)
        if frame.sequence_number in self._temporary:
            raise TemporaryInferenceError("Synthetic temporary detector failure.")
        if frame.sequence_number in self._fatal:
            raise FatalInferenceError("Synthetic fatal detector failure.")
        return super().infer(frame)


class SyntheticMovingBoxDetector(EmptyDetector):
    """Emit one deterministic synthetic box for integration diagnostics.

    The box is generated from frame sequence only. It is not an inferred pig
    detection and provides no detector-quality evidence.
    """

    def __init__(self, **settings: object) -> None:
        super().__init__(model_id="synthetic-moving-box-detector", **settings)

    def _detections_for(self, frame: FramePacket) -> tuple[Detection, ...]:
        box_width = max(1.0, frame.dimensions.width / 4.0)
        box_height = max(1.0, frame.dimensions.height / 3.0)
        travel = max(0.0, frame.dimensions.width - box_width)
        x_min = min(travel, float(frame.sequence_number % 20) / 19.0 * travel)
        y_min = max(0.0, (frame.dimensions.height - box_height) / 2.0)
        return (
            Detection(
                BoundingBox(
                    x_min,
                    y_min,
                    min(float(frame.dimensions.width), x_min + box_width),
                    min(float(frame.dimensions.height), y_min + box_height),
                ),
                0.9,
                0,
                "pig",
            ),
        )


__all__ = [
    "EmptyDetector",
    "FailingDetector",
    "ScriptedDetector",
    "SlowDetector",
    "SyntheticMovingBoxDetector",
]
