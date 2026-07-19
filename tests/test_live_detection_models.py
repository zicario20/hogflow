from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from hogflow.core import ConfigurationError, InputDataError
from hogflow.detection.inference import (
    DetectionShutdownReason,
    FrameDetections,
    LiveDetectionRunSummary,
    LiveDetectionStats,
    LiveInferenceConfiguration,
    ModelArtifactMetadata,
)
from hogflow.models import BoundingBox, Detection
from hogflow.streaming.models import SourceType, StreamHealthState


def test_live_inference_configuration_is_immutable_and_validated() -> None:
    configuration = LiveInferenceConfiguration(
        inference_every_n_frames=2,
        target_inference_fps=10,
        maximum_frame_age_ms=200,
    )

    with pytest.raises(FrozenInstanceError):
        configuration.inference_every_n_frames = 3  # type: ignore[misc]
    with pytest.raises(ConfigurationError):
        LiveInferenceConfiguration(inference_every_n_frames=0)
    with pytest.raises(ConfigurationError):
        LiveInferenceConfiguration(target_inference_fps=float("nan"))


def test_model_metadata_rejects_paths_and_unsorted_class_maps() -> None:
    with pytest.raises(InputDataError, match="local path"):
        ModelArtifactMetadata("model", "framework", ((0, "pig"),), artifact_filename="C:\\x.pt")
    with pytest.raises(InputDataError, match="sorted"):
        ModelArtifactMetadata("model", "framework", ((1, "pig"), (0, "pig")))


def test_frame_detections_preserve_source_and_reject_out_of_bounds_boxes() -> None:
    timestamp = datetime(2026, 7, 18, tzinfo=timezone.utc)
    detection = Detection(BoundingBox(1, 1, 4, 4), 0.9, 0, "pig")
    result = FrameDetections(
        source_id="camera",
        frame_sequence=7,
        captured_at=timestamp,
        inference_started_at=timestamp,
        inference_completed_at=timestamp,
        frame_width=8,
        frame_height=6,
        detections=(detection,),
        model_id="model",
        model_version=None,
        artifact_fingerprint=None,
        inference_duration_ms=2.5,
    )

    assert result.frame_sequence == 7
    assert result.detections == (detection,)
    with pytest.raises(FrozenInstanceError):
        result.frame_sequence = 8  # type: ignore[misc]
    with pytest.raises(InputDataError, match="source frame"):
        FrameDetections(
            source_id="camera",
            frame_sequence=7,
            captured_at=timestamp,
            inference_started_at=timestamp,
            inference_completed_at=timestamp,
            frame_width=3,
            frame_height=3,
            detections=(detection,),
            model_id="model",
            model_version=None,
            artifact_fingerprint=None,
            inference_duration_ms=2.5,
        )


def test_live_statistics_enforce_stage_accounting() -> None:
    with pytest.raises(InputDataError, match="submitted"):
        LiveDetectionStats(
            frames_acquired=3,
            frames_submitted=2,
            frames_inferred=1,
            frames_skipped=0,
            source_frames_dropped=1,
            inference_failures=0,
            total_detections=0,
            preview_failures=0,
            average_inference_ms=1,
            p50_inference_ms=1,
            p95_inference_ms=1,
            effective_inference_fps=1,
            camera_fps=30,
            latest_frame_age_ms=1,
            maximum_frame_age_ms=1,
        )


def test_run_summary_rejects_an_unsanitized_source_identity() -> None:
    statistics = LiveDetectionStats(
        frames_acquired=0,
        frames_submitted=0,
        frames_inferred=0,
        frames_skipped=0,
        source_frames_dropped=0,
        inference_failures=0,
        total_detections=0,
        preview_failures=0,
        average_inference_ms=0,
        p50_inference_ms=0,
        p95_inference_ms=0,
        effective_inference_fps=0,
        camera_fps=None,
        latest_frame_age_ms=None,
        maximum_frame_age_ms=0,
    )

    with pytest.raises(InputDataError, match="unsafe"):
        LiveDetectionRunSummary(
            source_id="camera",
            source_type=SourceType.USB,
            source_display_name="C:\\private\\camera",
            detector=ModelArtifactMetadata("model", "synthetic", ((0, "pig"),)),
            statistics=statistics,
            shutdown_reason=DetectionShutdownReason.SOURCE_CLOSED,
            final_camera_health=StreamHealthState.STOPPED,
            detector_closed=True,
            camera_released=True,
        )
