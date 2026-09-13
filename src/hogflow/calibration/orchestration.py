"""Two-pass local orchestration for the autonomous counting demo."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from re import fullmatch
from time import monotonic, perf_counter
from typing import Callable, Iterable

from hogflow.adapters.camera_source_factory import create_camera_source
from hogflow.calibration.engine import (
    AutonomousCalibrationEngine,
    AutonomousCalibrationSettings,
    consistency_confidence,
    estimate_corridor,
    estimate_dominant_direction,
    evaluate_candidate_tracks,
    generate_line_candidates,
    select_eligible_trajectories,
)
from hogflow.calibration.models import (
    AutonomousCalibrationResult,
    CalibrationConfidence,
    CalibrationStatus,
    CountingGeometryConfiguration,
    LineCandidate,
    LineCandidateMetrics,
    TrajectoryObservation,
    TrajectorySummary,
)
from hogflow.counting import (
    LifecycleDirectionalCounter,
    LiveCountingConfiguration,
    LiveCrossingConfiguration,
    NormalizedLine,
    NormalizedPoint,
    TrackAnchor,
    VirtualLineCrossingDetector,
)
from hogflow.detection import LiveDetector, PigDetectorConfiguration
from hogflow.detection.inference import FrameDetections
from hogflow.models import BoundingBox
from hogflow.streaming import (
    CameraSource,
    FramePacket,
    FrameTimestamp,
    StreamConfiguration,
    StreamReadStatus,
)
from hogflow.tracking import (
    ByteTrackConfiguration,
    LiveTracker,
    TrackingRequest,
    byte_track_configuration_fingerprint,
)

_IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_SHA256_ZERO = "0" * 64
_ALGORITHM_VERSION = "phase_10_3c_a_v1"


@dataclass(frozen=True, slots=True)
class AutonomousDemoConfiguration:
    """Frozen local settings for one bounded autonomous demo run."""

    demo_id: str
    detector_configuration: PigDetectorConfiguration
    tracker_configuration: ByteTrackConfiguration = ByteTrackConfiguration()
    calibration_settings: AutonomousCalibrationSettings = AutonomousCalibrationSettings()
    crossing_epsilon: float = 0.005
    absent_track_retention_updates: int = 30
    algorithm_version: str = _ALGORITHM_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.demo_id, str) or fullmatch(_IDENTIFIER, self.demo_id) is None:
            raise ValueError("demo_id must be a sanitized identifier.")
        if not isinstance(self.detector_configuration, PigDetectorConfiguration):
            raise TypeError("detector_configuration must be PigDetectorConfiguration.")
        if not isinstance(self.tracker_configuration, ByteTrackConfiguration):
            raise TypeError("tracker_configuration must be ByteTrackConfiguration.")
        if not isinstance(self.calibration_settings, AutonomousCalibrationSettings):
            raise TypeError("calibration_settings must be AutonomousCalibrationSettings.")
        if (
            not isinstance(self.crossing_epsilon, (int, float))
            or not 0.0 <= float(self.crossing_epsilon) <= 1.0
        ):
            raise ValueError("crossing_epsilon must be between zero and one.")
        if (
            not isinstance(self.absent_track_retention_updates, int)
            or isinstance(self.absent_track_retention_updates, bool)
            or self.absent_track_retention_updates < 0
        ):
            raise ValueError("absent_track_retention_updates must be non-negative.")
        if (
            not isinstance(self.algorithm_version, str)
            or fullmatch(_IDENTIFIER, self.algorithm_version) is None
        ):
            raise ValueError("algorithm_version must be a sanitized identifier.")


@dataclass(frozen=True, slots=True)
class AutonomousDemoResult:
    """Bounded, path-free output of calibration and the official count pass."""

    demo_id: str
    calibration: AutonomousCalibrationResult
    primary_count: int | None
    primary_count_direction: str | None
    calibration_crossing_events: int
    counting_crossing_events: int
    pass_two_first_frame_sequence: int | None
    calibration_frames: int
    counting_frames: int
    calibration_fps: float
    counting_fps: float
    average_detector_latency_ms: float
    hmi_state: str
    failures: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.demo_id, str) or fullmatch(_IDENTIFIER, self.demo_id) is None:
            raise ValueError("demo_id must be a sanitized identifier.")
        if not isinstance(self.calibration, AutonomousCalibrationResult):
            raise TypeError("calibration must be AutonomousCalibrationResult.")
        for name in (
            "calibration_crossing_events",
            "counting_crossing_events",
            "calibration_frames",
            "counting_frames",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")
        for name in ("calibration_fps", "counting_fps", "average_detector_latency_ms"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or float(value) < 0:
                raise ValueError(f"{name} must be non-negative.")
        if self.primary_count is not None and (
            not isinstance(self.primary_count, int)
            or isinstance(self.primary_count, bool)
            or self.primary_count < 0
        ):
            raise ValueError("primary_count must be a non-negative integer when present.")
        if self.pass_two_first_frame_sequence is not None and (
            not isinstance(self.pass_two_first_frame_sequence, int)
            or isinstance(self.pass_two_first_frame_sequence, bool)
            or self.pass_two_first_frame_sequence < 0
        ):
            raise ValueError("pass_two_first_frame_sequence must be non-negative when present.")
        if not isinstance(self.hmi_state, str) or not self.hmi_state.strip():
            raise ValueError("hmi_state must be non-empty text.")
        for name in ("failures", "limitations"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ValueError(f"{name} must be non-empty text tuples.")


@dataclass(frozen=True, slots=True)
class _PassEvidence:
    summaries: tuple[TrajectorySummary, ...]
    frames: int
    first_frame_sequence: int | None
    elapsed_seconds: float
    detector_latencies_ms: tuple[float, ...]
    artifact_fingerprint: str
    tracker_fingerprint: str


def _clock_now(clock: Callable[[], datetime] | None) -> datetime:
    value = clock() if clock is not None else datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("Autonomous demo clock must return a timezone-aware datetime.")
    return value


def _make_packet(
    source: CameraSource,
    sequence: int,
    source_frame,
    clock: Callable[[], datetime] | None,
) -> FramePacket:
    return FramePacket(
        stream=source.identity,
        sequence_number=sequence,
        timestamp=FrameTimestamp(
            acquired_at=_clock_now(clock),
            monotonic_seconds=monotonic(),
            source_seconds=source_frame.source_timestamp_seconds,
        ),
        dimensions=source_frame.dimensions,
        payload=source_frame.payload,
    )


def _tracking_request(detections: FrameDetections) -> TrackingRequest:
    return TrackingRequest(
        source_id=detections.source_id,
        frame_sequence=detections.frame_sequence,
        captured_at=detections.captured_at,
        frame_width=detections.frame_width,
        frame_height=detections.frame_height,
        detections=detections.detections,
    )


def _artifact_fingerprint(detector: LiveDetector) -> str:
    value = getattr(detector.metadata, "artifact_fingerprint", None)
    return value if isinstance(value, str) and len(value) == 64 else _SHA256_ZERO


def _tracker_fingerprint(tracker: LiveTracker, configuration: ByteTrackConfiguration) -> str:
    value = getattr(getattr(tracker, "metadata", None), "configuration_fingerprint", None)
    return (
        value
        if isinstance(value, str) and len(value) == 64
        else byte_track_configuration_fingerprint(configuration)
    )


def _close_pass_components(
    source: CameraSource, detector: LiveDetector, tracker: LiveTracker
) -> None:
    try:
        if tracker.is_started:
            tracker.reset()
    finally:
        try:
            tracker.close()
        finally:
            try:
                if detector.is_loaded:
                    detector.close()
            finally:
                source.close()


def _collect_trajectories(
    configuration: AutonomousDemoConfiguration,
    *,
    source_factory: Callable[[StreamConfiguration], CameraSource],
    detector_factory: Callable[[PigDetectorConfiguration], LiveDetector],
    tracker_factory: Callable[[ByteTrackConfiguration], LiveTracker],
    detector_configuration: PigDetectorConfiguration,
    clock: Callable[[], datetime] | None,
) -> _PassEvidence:
    source = source_factory(StreamConfiguration.synthetic(configuration.demo_id))
    detector = detector_factory(detector_configuration)
    tracker = tracker_factory(configuration.tracker_configuration)
    engine = AutonomousCalibrationEngine(configuration.calibration_settings)
    frames = 0
    first_sequence: int | None = None
    latencies: list[float] = []
    started = perf_counter()
    artifact_fingerprint = _SHA256_ZERO
    tracker_fingerprint = byte_track_configuration_fingerprint(configuration.tracker_configuration)
    source.open()
    try:
        detector.load()
        tracker.start(source.identity.stream_id)
        artifact_fingerprint = _artifact_fingerprint(detector)
        tracker_fingerprint = _tracker_fingerprint(tracker, configuration.tracker_configuration)
        while True:
            result = source.read()
            if result.status is StreamReadStatus.TEMPORARY_UNAVAILABLE:
                continue
            if result.status in {
                StreamReadStatus.END_OF_STREAM,
                StreamReadStatus.STOPPED,
                StreamReadStatus.INTERRUPTED,
            }:
                break
            if result.status is not StreamReadStatus.FRAME or result.frame is None:
                continue
            packet = _make_packet(source, frames, result.frame, clock)
            detections = detector.infer(packet)
            latencies.append(float(detections.inference_duration_ms))
            tracking = tracker.update(_tracking_request(detections))
            if first_sequence is None:
                first_sequence = packet.sequence_number
            frames += 1
            for tracked_object in tracking.tracked_objects:
                box: BoundingBox = tracked_object.track.detection.bounding_box
                center = (
                    ((box.x_min + box.x_max) / 2.0) / tracking.frame_width,
                    box.y_max / tracking.frame_height,
                )
                engine.observe(
                    TrajectoryObservation(
                        tracker_id=tracked_object.track.tracker_id,
                        frame_sequence=tracking.frame_sequence,
                        center=center,
                        confidence=tracked_object.track.detection.confidence,
                    )
                )
    finally:
        _close_pass_components(source, detector, tracker)
    elapsed = max(0.0, perf_counter() - started)
    return _PassEvidence(
        summaries=engine.summaries(),
        frames=frames,
        first_frame_sequence=first_sequence,
        elapsed_seconds=elapsed,
        detector_latencies_ms=tuple(latencies),
        artifact_fingerprint=artifact_fingerprint,
        tracker_fingerprint=tracker_fingerprint,
    )


def _shift_candidate(
    candidate: LineCandidate,
    direction,
    offset: float,
    identifier: str,
) -> LineCandidate | None:
    raw_start = (
        candidate.line.start.x + direction.dx * offset,
        candidate.line.start.y + direction.dy * offset,
    )
    raw_end = (
        candidate.line.end.x + direction.dx * offset,
        candidate.line.end.y + direction.dy * offset,
    )
    if not all(0.0 <= value <= 1.0 for value in (*raw_start, *raw_end)):
        return None
    start = NormalizedPoint(
        *raw_start,
    )
    end = NormalizedPoint(
        *raw_end,
    )
    return LineCandidate(
        candidate_id=identifier,
        line=NormalizedLine(start, end),
        along_position=candidate.along_position + offset,
        positive_direction=candidate.positive_direction,
        edge_penalty=candidate.edge_penalty,
    )


def _settings_fingerprint(settings: AutonomousCalibrationSettings) -> str:
    payload = {
        "candidate_positions": settings.candidate_positions,
        "corridor_low_percentile": settings.corridor_low_percentile,
        "corridor_high_percentile": settings.corridor_high_percentile,
        "diagnostic_confidences": settings.diagnostic_confidences,
        "edge_margin": settings.edge_margin,
        "maximum_jitter_ratio": settings.maximum_jitter_ratio,
        "maximum_sampled_centers": settings.maximum_sampled_centers,
        "minimum_continuity_ratio": settings.minimum_continuity_ratio,
        "minimum_direction_resultant": settings.minimum_direction_resultant,
        "minimum_displacement": settings.minimum_displacement,
        "minimum_lifetime_frames": settings.minimum_lifetime_frames,
        "minimum_mean_confidence": settings.minimum_mean_confidence,
        "neighbor_offsets": settings.neighbor_offsets,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _forward_count(
    candidate: LineCandidate,
    summaries: Iterable[TrajectorySummary],
    settings: AutonomousCalibrationSettings,
) -> int:
    return evaluate_candidate_tracks(candidate, summaries, settings).forward_crossings


def _build_calibration_result(
    configuration: AutonomousDemoConfiguration,
    primary: _PassEvidence,
    diagnostics: tuple[tuple[float, _PassEvidence], ...],
) -> AutonomousCalibrationResult:
    settings = configuration.calibration_settings
    eligible = select_eligible_trajectories(primary.summaries, settings)
    direction, purity = estimate_dominant_direction(eligible, settings)
    base_limitations = (
        "autonomous_consistency_only",
        "human_ground_truth_not_measured",
        "demo_model_not_production_validated",
    )
    if direction is None or len(eligible) < 3:
        return AutonomousCalibrationResult(
            status=CalibrationStatus.INCONCLUSIVE,
            confidence=CalibrationConfidence.INCONCLUSIVE,
            dominant_direction=direction,
            direction_purity=purity,
            eligible_track_count=len(eligible),
            selected_line=None,
            selected_positive_direction=None,
            selected_score=0.0,
            corridor=None,
            candidate_metrics=(),
            line_band_counts=(),
            detector_perturbation_counts=(),
            counting_configuration=None,
            limitations=base_limitations + ("insufficient_directional_evidence",),
        )
    try:
        corridor = estimate_corridor(eligible, direction, settings)
        candidates = generate_line_candidates(corridor, direction, settings)
    except ValueError:
        candidates = ()
        corridor = None
    if not candidates or corridor is None:
        return AutonomousCalibrationResult(
            status=CalibrationStatus.INCONCLUSIVE,
            confidence=CalibrationConfidence.INCONCLUSIVE,
            dominant_direction=direction,
            direction_purity=purity,
            eligible_track_count=len(eligible),
            selected_line=None,
            selected_positive_direction=None,
            selected_score=0.0,
            corridor=corridor,
            candidate_metrics=(),
            line_band_counts=(),
            detector_perturbation_counts=(),
            counting_configuration=None,
            limitations=base_limitations + ("no_safe_line_candidate",),
        )

    metrics: list[LineCandidateMetrics] = []
    for candidate in candidates:
        neighbor_counts = tuple(
            0
            if (
                shifted := _shift_candidate(
                    candidate, direction, offset, f"{candidate.candidate_id}_n{index}"
                )
            )
            is None
            else _forward_count(shifted, primary.summaries, settings)
            for index, offset in enumerate(settings.neighbor_offsets, start=1)
        )
        perturbation_counts = tuple(
            (
                confidence,
                _forward_count(candidate, evidence.summaries, settings),
            )
            for confidence, evidence in diagnostics
        )
        metrics.append(
            evaluate_candidate_tracks(
                candidate,
                primary.summaries,
                settings,
                neighbor_counts=neighbor_counts,
                detector_perturbation_counts=perturbation_counts,
            )
        )
    ordered = sorted(
        metrics,
        key=lambda item: (
            -item.score,
            -item.neighbor_agreement,
            -item.continuity_score,
            item.candidate.candidate_id,
        ),
    )
    selected = ordered[0]
    confidence = consistency_confidence(
        eligible_tracks=len(eligible),
        direction_purity=purity,
        neighbor_agreement=selected.neighbor_agreement,
        continuity_score=selected.continuity_score,
        score=selected.score,
    )
    geometry = CountingGeometryConfiguration(
        detector_artifact_fingerprint=primary.artifact_fingerprint,
        detector_configuration_fingerprint=configuration.detector_configuration.fingerprint,
        tracker_configuration_fingerprint=primary.tracker_fingerprint,
        line=selected.candidate.line,
        positive_direction=selected.candidate.positive_direction,
        crossing_epsilon=configuration.crossing_epsilon,
        absent_track_retention_updates=configuration.absent_track_retention_updates,
        algorithm_version=configuration.algorithm_version,
        settings_fingerprint=_settings_fingerprint(settings),
    )
    primary_neighbor_counts = selected.neighbor_counts
    return AutonomousCalibrationResult(
        status=CalibrationStatus.READY,
        confidence=confidence,
        dominant_direction=direction,
        direction_purity=purity,
        eligible_track_count=len(eligible),
        selected_line=selected.candidate.line,
        selected_positive_direction=selected.candidate.positive_direction,
        selected_score=selected.score,
        corridor=corridor,
        candidate_metrics=tuple(ordered),
        line_band_counts=primary_neighbor_counts,
        detector_perturbation_counts=selected.detector_perturbation_counts,
        counting_configuration=geometry,
        limitations=base_limitations,
    )


def _run_count_pass(
    configuration: AutonomousDemoConfiguration,
    calibration: AutonomousCalibrationResult,
    *,
    source_factory: Callable[[StreamConfiguration], CameraSource],
    detector_factory: Callable[[PigDetectorConfiguration], LiveDetector],
    tracker_factory: Callable[[ByteTrackConfiguration], LiveTracker],
    clock: Callable[[], datetime] | None,
) -> tuple[int, int, int | None, float, float, float]:
    geometry = calibration.counting_configuration
    if geometry is None or calibration.selected_line is None:
        raise ValueError("Counting pass requires ready calibration geometry.")
    source = source_factory(StreamConfiguration.synthetic(configuration.demo_id))
    detector = detector_factory(configuration.detector_configuration)
    tracker = tracker_factory(configuration.tracker_configuration)
    crossing_configuration = LiveCrossingConfiguration(
        enabled=True,
        line=geometry.line,
        anchor=TrackAnchor.BOTTOM_CENTER,
        epsilon=geometry.crossing_epsilon,
        absent_track_retention_updates=geometry.absent_track_retention_updates,
    )
    crossing = VirtualLineCrossingDetector(crossing_configuration)
    counter = LifecycleDirectionalCounter(
        LiveCountingConfiguration(
            enabled=True,
            positive_direction=geometry.positive_direction,
            crossing_configuration_fingerprint=crossing_configuration.fingerprint,
        )
    )
    frames = 0
    first_sequence: int | None = None
    crossing_events = 0
    count: int | None = None
    latencies: list[float] = []
    started = perf_counter()
    source.open()
    try:
        detector.load()
        tracker.start(source.identity.stream_id)
        crossing.start(source.identity.stream_id)
        counter.start(source.identity.stream_id, crossing.lifecycle_id)
        while True:
            result = source.read()
            if result.status is StreamReadStatus.TEMPORARY_UNAVAILABLE:
                continue
            if result.status in {
                StreamReadStatus.END_OF_STREAM,
                StreamReadStatus.STOPPED,
                StreamReadStatus.INTERRUPTED,
            }:
                break
            if result.status is not StreamReadStatus.FRAME or result.frame is None:
                continue
            packet = _make_packet(source, frames, result.frame, clock)
            detections = detector.infer(packet)
            latencies.append(float(detections.inference_duration_ms))
            tracking = tracker.update(_tracking_request(detections))
            if first_sequence is None:
                first_sequence = packet.sequence_number
            crossing_result = crossing.update(tracking)
            crossing_events += len(crossing_result.events)
            counting_result = counter.update(crossing_result)
            count = counting_result.lifecycle_directional_count
            frames += 1
    finally:
        counter.close()
        crossing.close()
        _close_pass_components(source, detector, tracker)
    elapsed = max(0.0, perf_counter() - started)
    fps = frames / elapsed if elapsed else 0.0
    average_latency = sum(latencies) / len(latencies) if latencies else 0.0
    return frames, crossing_events, count, first_sequence, fps, average_latency


def run_autonomous_demo(
    configuration: AutonomousDemoConfiguration,
    *,
    source_factory: Callable[[StreamConfiguration], CameraSource] = create_camera_source,
    detector_factory: Callable[[PigDetectorConfiguration], LiveDetector] | None = None,
    tracker_factory: Callable[[ByteTrackConfiguration], LiveTracker] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> AutonomousDemoResult:
    """Run bounded calibration and, only when ready, one clean count pass."""

    if not isinstance(configuration, AutonomousDemoConfiguration):
        raise TypeError("run_autonomous_demo requires AutonomousDemoConfiguration.")
    if detector_factory is None or tracker_factory is None:
        from hogflow.adapters.live_detector_factory import create_live_detector_and_tracker

        pairs: list[tuple[LiveDetector, LiveTracker]] = []

        def _combined_detector(config: PigDetectorConfiguration) -> LiveDetector:
            pair = create_live_detector_and_tracker(config)
            pairs.append(pair)
            return pair[0]

        def _combined_tracker(config: ByteTrackConfiguration) -> LiveTracker:
            if not pairs:
                raise RuntimeError("Default detector/tracker factories must be paired.")
            return pairs.pop(0)[1]

        detector_factory = detector_factory or _combined_detector
        tracker_factory = tracker_factory or _combined_tracker

    failures: list[str] = []
    try:
        primary = _collect_trajectories(
            configuration,
            source_factory=source_factory,
            detector_factory=detector_factory,
            tracker_factory=tracker_factory,
            detector_configuration=configuration.detector_configuration,
            clock=clock,
        )
        diagnostics = tuple(
            (
                confidence,
                _collect_trajectories(
                    configuration,
                    source_factory=source_factory,
                    detector_factory=detector_factory,
                    tracker_factory=tracker_factory,
                    detector_configuration=replace(
                        configuration.detector_configuration,
                        confidence_threshold=confidence,
                    ),
                    clock=clock,
                ),
            )
            for confidence in configuration.calibration_settings.diagnostic_confidences
        )
        calibration = _build_calibration_result(configuration, primary, diagnostics)
        if calibration.status is not CalibrationStatus.READY:
            return AutonomousDemoResult(
                demo_id=configuration.demo_id,
                calibration=calibration,
                primary_count=None,
                primary_count_direction=None,
                calibration_crossing_events=0,
                counting_crossing_events=0,
                pass_two_first_frame_sequence=None,
                calibration_frames=primary.frames,
                counting_frames=0,
                calibration_fps=primary.frames / primary.elapsed_seconds
                if primary.elapsed_seconds
                else 0.0,
                counting_fps=0.0,
                average_detector_latency_ms=(
                    sum(primary.detector_latencies_ms) / len(primary.detector_latencies_ms)
                    if primary.detector_latencies_ms
                    else 0.0
                ),
                hmi_state="AUTOCALIBRATION INCONCLUSIVE",
                failures=tuple(failures),
                limitations=calibration.limitations,
            )
        (
            count_frames,
            crossing_events,
            primary_count,
            first_sequence,
            count_fps,
            count_latency,
        ) = _run_count_pass(
            configuration,
            calibration,
            source_factory=source_factory,
            detector_factory=detector_factory,
            tracker_factory=tracker_factory,
            clock=clock,
        )
        return AutonomousDemoResult(
            demo_id=configuration.demo_id,
            calibration=calibration,
            primary_count=primary_count,
            primary_count_direction=(
                calibration.selected_positive_direction.value
                if calibration.selected_positive_direction is not None
                else None
            ),
            calibration_crossing_events=0,
            counting_crossing_events=crossing_events,
            pass_two_first_frame_sequence=first_sequence,
            calibration_frames=primary.frames,
            counting_frames=count_frames,
            calibration_fps=primary.frames / primary.elapsed_seconds
            if primary.elapsed_seconds
            else 0.0,
            counting_fps=count_fps,
            average_detector_latency_ms=count_latency,
            hmi_state="LIVE COUNT",
            failures=tuple(failures),
            limitations=calibration.limitations,
        )
    except Exception as exc:
        failure_type = type(exc).__name__
        if not fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", failure_type):
            failure_type = "unknown_runtime_failure"
        return AutonomousDemoResult(
            demo_id=configuration.demo_id,
            calibration=AutonomousCalibrationResult(
                status=CalibrationStatus.FAILED,
                confidence=CalibrationConfidence.INCONCLUSIVE,
                dominant_direction=None,
                direction_purity=0.0,
                eligible_track_count=0,
                selected_line=None,
                selected_positive_direction=None,
                selected_score=0.0,
                corridor=None,
                candidate_metrics=(),
                line_band_counts=(),
                detector_perturbation_counts=(),
                counting_configuration=None,
                limitations=(
                    "autonomous_consistency_only",
                    "human_ground_truth_not_measured",
                    "demo_model_not_production_validated",
                    "bounded_runtime_failure",
                ),
            ),
            primary_count=None,
            primary_count_direction=None,
            calibration_crossing_events=0,
            counting_crossing_events=0,
            pass_two_first_frame_sequence=None,
            calibration_frames=0,
            counting_frames=0,
            calibration_fps=0.0,
            counting_fps=0.0,
            average_detector_latency_ms=0.0,
            hmi_state="AUTOCALIBRATION FAILED",
            failures=("bounded_runtime_failure", f"runtime_exception_{failure_type}"),
            limitations=(
                "autonomous_consistency_only",
                "human_ground_truth_not_measured",
                "demo_model_not_production_validated",
            ),
        )


__all__ = [
    "AutonomousDemoConfiguration",
    "AutonomousDemoResult",
    "run_autonomous_demo",
]
