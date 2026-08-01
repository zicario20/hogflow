"""Serial hard-gated orchestration for controlled Phase 10.3 evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from hogflow.evaluation import EvidenceLevel
from hogflow.validation.errors import ValidationConfigurationError, ValidationExecutionError
from hogflow.validation.models import (
    BLOCKED_EMPIRICAL_VERDICT,
    DETECTOR_AND_COUNTING_EMPIRICAL_VERDICT,
    DETECTOR_ONLY_EMPIRICAL_VERDICT,
    VIDEO_3_COUNTING_WARNING,
    CalibrationCandidate,
    CrossingCountingDiagnostics,
    DetectorDiagnostics,
    EvidenceState,
    EvidenceValue,
    GroundTruthAssessment,
    ModelAvailability,
    ModelGateState,
    PerformanceMetrics,
    RealWorldValidationReport,
    TrackingDiagnostics,
    ValidationRunStatus,
    VideoValidationResult,
)
from hogflow.validation.ports import ModelPresentValidationBackend
from hogflow.validation.workspace import InspectedAuthorizedVideo, LocalValidationWorkspace


class RealWorldValidationWorkflow:
    """Process authorized videos in fixed order without fabricating evidence."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        workspace: LocalValidationWorkspace,
        inspected_videos: tuple[InspectedAuthorizedVideo, ...],
        model_availability: ModelAvailability,
        selected_candidates: Mapping[str, CalibrationCandidate] | None = None,
        manual_totals: Mapping[str, int] | None = None,
        backend: ModelPresentValidationBackend | None = None,
    ) -> RealWorldValidationReport:
        """Return three separate results and honor the missing-model hard gate."""

        if tuple(item.video.video_id for item in inspected_videos) != (
            "video_1",
            "video_2",
            "video_3",
        ):
            raise ValidationConfigurationError(
                "Inspected videos must contain the exact authorized processing order."
            )
        if not isinstance(model_availability, ModelAvailability):
            raise ValidationConfigurationError("Model availability must be validated.")
        if model_availability.state is not ModelGateState.AVAILABLE:
            results = tuple(_blocked_result(item, model_availability) for item in inspected_videos)
            return RealWorldValidationReport(
                report_id="phase10_3.local_validation",
                generated_at=self._clock(),
                model_availability=model_availability,
                results=results,
                empirical_verdict=BLOCKED_EMPIRICAL_VERDICT,
            )

        if backend is None or selected_candidates is None:
            raise ValidationConfigurationError(
                "Model-present validation requires an explicit public-pipeline backend and candidates."
            )
        manual_totals = manual_totals or {}
        results: list[VideoValidationResult] = []
        previous_structurally_complete = True
        for inspected in inspected_videos:
            video_id = inspected.video.video_id
            if video_id == "video_2" and not previous_structurally_complete:
                results.append(
                    _blocked_result(
                        inspected,
                        model_availability,
                        reason="video_1_structural_validation_incomplete",
                    )
                )
                previous_structurally_complete = False
                continue
            if video_id == "video_3" and not previous_structurally_complete:
                results.append(
                    _blocked_result(
                        inspected,
                        model_availability,
                        reason="prior_counting_candidate_incomplete",
                    )
                )
                continue
            candidate = selected_candidates.get(video_id)
            if candidate is None or candidate.video_id != video_id:
                raise ValidationConfigurationError(
                    f"An explicit calibration candidate is required for {video_id}."
                )
            try:
                result = backend.run(
                    video_path=workspace.video_path(video_id),
                    model_path=workspace.model_path(),
                    candidate=candidate,
                    manual_total=manual_totals.get(video_id),
                )
            except Exception as exc:
                raise ValidationExecutionError(
                    f"Controlled validation backend failed for {video_id}."
                ) from exc
            if (
                not isinstance(result, VideoValidationResult)
                or result.video.video_id != video_id
                or result.calibration_candidate != candidate
                or result.model_availability != model_availability
            ):
                raise ValidationExecutionError(
                    "Validation backend returned mismatched or unsanitized provenance."
                )
            results.append(result)
            previous_structurally_complete = result.structurally_complete

        all_completed = all(item.status is ValidationRunStatus.COMPLETED for item in results)
        counting_truth_available = all(
            item.ground_truth.manual_total.state is EvidenceState.PROVIDED_MANUAL_GROUND_TRUTH
            for item in results[:2]
        )
        if not all_completed:
            verdict = BLOCKED_EMPIRICAL_VERDICT
        elif counting_truth_available:
            verdict = DETECTOR_AND_COUNTING_EMPIRICAL_VERDICT
        else:
            verdict = DETECTOR_ONLY_EMPIRICAL_VERDICT
        return RealWorldValidationReport(
            report_id="phase10_3.local_validation",
            generated_at=self._clock(),
            model_availability=model_availability,
            results=tuple(results),
            empirical_verdict=verdict,
        )


def _blocked_result(
    inspected: InspectedAuthorizedVideo,
    model: ModelAvailability,
    *,
    reason: str = "compatible_local_pig_detector_missing",
) -> VideoValidationResult:
    unknown = EvidenceValue.unknown
    not_applicable = EvidenceValue.not_applicable
    stress_only = not inspected.video.counting_accuracy_eligible
    expected_frames = inspected.metadata.frame_count
    crossing_metric = not_applicable if stress_only else unknown
    system_count = crossing_metric("count")
    limitations = [
        "No compatible local pig detector passed the artifact gate.",
        "No detector, tracker, crossing, or counting inference was executed.",
        "Manual ground truth is absent from local review records.",
        "Detector precision, recall, and F1 require frame-level annotations.",
    ]
    if stress_only:
        limitations.append(VIDEO_3_COUNTING_WARNING)
    return VideoValidationResult(
        run_id=f"phase10_3.{inspected.video.video_id}.blocked",
        video=inspected.video,
        evidence_level=EvidenceLevel.REPRESENTATIVE_WITHOUT_GROUND_TRUTH,
        status=ValidationRunStatus.BLOCKED,
        metadata=inspected.metadata,
        model_availability=model,
        detector_configuration_fingerprint=None,
        tracker_configuration_fingerprint=None,
        calibration_candidate=None,
        runtime_device=None,
        performance=PerformanceMetrics(
            model_load_duration_ms=unknown("milliseconds"),
            first_inference_latency_ms=unknown("milliseconds"),
            steady_state_inference_latency_ms=unknown("milliseconds"),
            total_processing_latency_ms=unknown("milliseconds"),
            average_fps=unknown("fps"),
            minimum_fps=unknown("fps"),
            maximum_fps=unknown("fps"),
            frames_processed=unknown("frames"),
            video_frames_expected=expected_frames,
            frames_dropped=unknown("frames"),
        ),
        detector=DetectorDiagnostics(
            detections_produced=unknown("detections"),
            frames_with_detections=unknown("frames"),
            source_failures=unknown("failures"),
            detector_failures=unknown("failures"),
            temporary_inference_failures=unknown("failures"),
            malformed_outputs=unknown("failures"),
        ),
        tracking=TrackingDiagnostics(
            temporary_track_ids_observed=unknown("identities"),
            average_tracks_per_frame=unknown("tracks_per_frame"),
            maximum_tracks_per_frame=unknown("tracks"),
            fragmentations=unknown("events"),
            suspected_id_switches=unknown("events"),
            tracks_lost_near_line=unknown("tracks"),
            tracker_failures=unknown("failures"),
            tracker_resets=unknown("resets"),
            reconnects=unknown("reconnects"),
        ),
        crossing_counting=CrossingCountingDiagnostics(
            crossing_events=crossing_metric("events"),
            accepted_positive_counts=crossing_metric("events"),
            duplicate_positive_events=crossing_metric("events"),
            reverse_events=crossing_metric("events"),
            ignored_events=crossing_metric("events"),
            events_after_frame_gaps=crossing_metric("events"),
            stale_evidence_rejected=crossing_metric("events"),
            crossing_failures=crossing_metric("failures"),
            lifecycle_resets=crossing_metric("resets"),
            system_count=system_count,
        ),
        ground_truth=GroundTruthAssessment.build(
            system_count=system_count,
            manual_total=None,
            counting_applicable=not stress_only,
        ),
        structurally_complete=False,
        limitations=tuple(limitations),
        conclusion=reason,
    )


__all__ = ["RealWorldValidationWorkflow"]
