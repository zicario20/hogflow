from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hogflow.counting import (
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
    TrackAnchor,
)
from hogflow.data import CameraStabilityLabel, VideoFileMetadata
from hogflow.evaluation import EvidenceLevel, LineCandidate
from hogflow.validation import (
    AUTHORIZED_VIDEOS,
    CalibrationCandidate,
    CrossingCountingDiagnostics,
    DetectorDiagnostics,
    EvidenceValue,
    GroundTruthAssessment,
    ModelAvailability,
    PerformanceMetrics,
    TrackingDiagnostics,
    ValidationRunStatus,
    VideoValidationResult,
    exact_authorized_filenames,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class FakeMetadataInspector:
    def inspect(self, path: str | Path, *, relative_path: str | Path) -> VideoFileMetadata:
        return VideoFileMetadata(
            relative_path=Path(relative_path).as_posix(),
            file_size_bytes=1_024,
            container_extension=".mp4",
            duration_seconds=2.0,
            fps=10.0,
            frame_count=20,
            width=640,
            height=360,
            codec="mp4v",
            readable=True,
            sampled_frame_count=3,
            stability_label=CameraStabilityLabel.LIKELY_STATIC,
        )


class FakeGitPolicy:
    def __init__(self, *, ignored: bool = True, tracked: bool = False) -> None:
        self.ignored = ignored
        self.tracked = tracked

    def is_ignored(self, _path: Path) -> bool:
        return self.ignored

    def is_tracked(self, _path: Path) -> bool:
        return self.tracked


def create_authorized_media(root: Path) -> None:
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    for filename in exact_authorized_filenames():
        (raw / filename).write_bytes(b"synthetic-test-placeholder")


def calibration_candidate(video_id: str, *, x: float | None = None) -> CalibrationCandidate:
    index = int(video_id[-1])
    line_x = x if x is not None else 0.2 * index
    return CalibrationCandidate(
        candidate_id=f"{video_id}.candidate_a",
        video_id=video_id,
        line_candidate=LineCandidate(
            candidate_id=f"{video_id}.line_a",
            line=NormalizedLine(
                NormalizedPoint(line_x, 0.1),
                NormalizedPoint(line_x, 0.9),
            ),
            anchor=TrackAnchor.BOTTOM_CENTER,
        ),
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        confidence_threshold=0.5,
        iou_threshold=0.45,
        inference_image_size=640,
        tracker_frame_rate=10.0,
        lost_track_buffer=30,
        maximum_detections=100,
    )


def completed_result(
    video_id: str,
    candidate: CalibrationCandidate,
    model: ModelAvailability,
    *,
    system_count: int = 2,
    manual_total: int | None = None,
    structurally_complete: bool = True,
) -> VideoValidationResult:
    video = next(item for item in AUTHORIZED_VIDEOS if item.video_id == video_id)
    measured_zero = EvidenceValue.measured(0)
    count_applicable = video.counting_accuracy_eligible

    def crossing(value: int, unit: str) -> EvidenceValue:
        if count_applicable:
            return EvidenceValue.measured(value, unit)
        return EvidenceValue.not_applicable(unit)

    count_value = (
        EvidenceValue.measured(system_count, "count")
        if count_applicable
        else EvidenceValue.not_applicable("count")
    )
    from hogflow.validation import SanitizedVideoMetadata

    metadata = SanitizedVideoMetadata(
        container_format=EvidenceValue.measured("mp4"),
        file_size_bytes=EvidenceValue.measured(1_024, "bytes"),
        duration_seconds=EvidenceValue.measured(2.0, "seconds"),
        nominal_fps=EvidenceValue.measured(10.0, "fps"),
        frame_count=EvidenceValue.measured(20, "frames"),
        frame_width=EvidenceValue.measured(640, "pixels"),
        frame_height=EvidenceValue.measured(360, "pixels"),
        readable=EvidenceValue.measured(True),
        stability_label=EvidenceValue.measured("likely_static"),
    )
    limitations = [
        "Temporary tracker IDs are not biological identities.",
        "Synthetic backend evidence does not validate pig accuracy.",
    ]
    if not count_applicable:
        from hogflow.validation import VIDEO_3_COUNTING_WARNING

        limitations.append(VIDEO_3_COUNTING_WARNING)
    return VideoValidationResult(
        run_id=f"phase10_3.{video_id}.run",
        video=video,
        evidence_level=EvidenceLevel.REPRESENTATIVE_WITHOUT_GROUND_TRUTH,
        status=(
            ValidationRunStatus.COMPLETED
            if structurally_complete
            else ValidationRunStatus.INCOMPLETE
        ),
        metadata=metadata,
        model_availability=model,
        detector_configuration_fingerprint="1" * 64,
        tracker_configuration_fingerprint="2" * 64,
        calibration_candidate=candidate,
        runtime_device="cpu",
        performance=PerformanceMetrics(
            model_load_duration_ms=EvidenceValue.measured(1.0, "milliseconds"),
            first_inference_latency_ms=EvidenceValue.measured(2.0, "milliseconds"),
            steady_state_inference_latency_ms=EvidenceValue.measured(1.5, "milliseconds"),
            total_processing_latency_ms=EvidenceValue.measured(30.0, "milliseconds"),
            average_fps=EvidenceValue.measured(10.0, "fps"),
            minimum_fps=EvidenceValue.measured(9.0, "fps"),
            maximum_fps=EvidenceValue.measured(11.0, "fps"),
            frames_processed=EvidenceValue.measured(20, "frames"),
            video_frames_expected=EvidenceValue.measured(20, "frames"),
            frames_dropped=EvidenceValue.measured(0, "frames"),
        ),
        detector=DetectorDiagnostics(
            detections_produced=EvidenceValue.measured(system_count, "detections"),
            frames_with_detections=EvidenceValue.measured(system_count, "frames"),
            source_failures=measured_zero,
            detector_failures=measured_zero,
            temporary_inference_failures=measured_zero,
            malformed_outputs=measured_zero,
        ),
        tracking=TrackingDiagnostics(
            temporary_track_ids_observed=EvidenceValue.measured(system_count, "identities"),
            average_tracks_per_frame=EvidenceValue.measured(1.0, "tracks_per_frame"),
            maximum_tracks_per_frame=EvidenceValue.measured(2, "tracks"),
            fragmentations=EvidenceValue.unknown("events"),
            suspected_id_switches=EvidenceValue.unknown("events"),
            tracks_lost_near_line=EvidenceValue.unknown("tracks"),
            tracker_failures=measured_zero,
            tracker_resets=measured_zero,
            reconnects=measured_zero,
        ),
        crossing_counting=CrossingCountingDiagnostics(
            crossing_events=crossing(system_count, "events"),
            accepted_positive_counts=crossing(system_count, "events"),
            duplicate_positive_events=crossing(0, "events"),
            reverse_events=crossing(0, "events"),
            ignored_events=crossing(0, "events"),
            events_after_frame_gaps=crossing(0, "events"),
            stale_evidence_rejected=crossing(0, "events"),
            crossing_failures=crossing(0, "failures"),
            lifecycle_resets=crossing(0, "resets"),
            system_count=count_value,
        ),
        ground_truth=GroundTruthAssessment.build(
            system_count=count_value,
            manual_total=manual_total,
            counting_applicable=count_applicable,
        ),
        structurally_complete=structurally_complete,
        limitations=tuple(limitations),
        conclusion=("structural_run_complete" if structurally_complete else "run_incomplete"),
    )
