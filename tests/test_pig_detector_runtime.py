from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest
from _phase5_2_helpers import frame_packet

from hogflow.detection import (
    DetectorBackend,
    DetectorConfigurationError,
    DetectorModelFormat,
    DetectorModelProvenance,
    DetectorRuntimeSnapshot,
    DetectorRuntimeTelemetry,
    ModelArtifactMetadata,
    ModelArtifactMissingError,
    PigDetectorConfiguration,
    UnsupportedModelFormatError,
)
from hogflow.detection.inference import FrameDetections


def _artifact(tmp_path: Path, name: str = "local.pt") -> Path:
    path = tmp_path / name
    path.write_bytes(b"synthetic-local-artifact")
    return path


def test_configuration_is_immutable_validated_and_path_redacting(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    configuration = PigDetectorConfiguration.ultralytics(
        artifact,
        target_class_ids=(3,),
        confidence_threshold=0.45,
        iou_threshold=0.55,
        inference_image_size=512,
        device="cuda:0",
        maximum_detections=25,
        half_precision=True,
    )

    assert configuration.backend is DetectorBackend.ULTRALYTICS
    assert configuration.model_format is DetectorModelFormat.PYTORCH
    assert len(configuration.fingerprint) == 64
    assert str(tmp_path) not in repr(configuration)
    with pytest.raises(FrozenInstanceError):
        configuration.device = "cpu"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("setting", "value"),
    (
        ("confidence_threshold", 0),
        ("confidence_threshold", float("nan")),
        ("iou_threshold", float("inf")),
        ("inference_image_size", 0),
        ("inference_image_size", True),
        ("maximum_detections", -1),
        ("device", "gpu"),
    ),
)
def test_configuration_rejects_invalid_execution_values(
    tmp_path: Path,
    setting: str,
    value: object,
) -> None:
    with pytest.raises(DetectorConfigurationError):
        PigDetectorConfiguration.ultralytics(_artifact(tmp_path), **{setting: value})


def test_configuration_rejects_missing_and_unsupported_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ModelArtifactMissingError) as missing:
        PigDetectorConfiguration.ultralytics(tmp_path / "private" / "missing.pt")
    unsupported = _artifact(tmp_path, "local.bin")
    with pytest.raises(UnsupportedModelFormatError):
        PigDetectorConfiguration.ultralytics(unsupported)

    assert str(tmp_path) not in str(missing.value)


def test_configuration_rejects_conflicting_empty_mode_and_duplicate_classes(
    tmp_path: Path,
) -> None:
    with pytest.raises(DetectorConfigurationError, match="Empty detector"):
        PigDetectorConfiguration(model_path=_artifact(tmp_path))
    with pytest.raises(DetectorConfigurationError, match="unique and sorted"):
        PigDetectorConfiguration.ultralytics(
            _artifact(tmp_path, "second.pt"),
            target_class_ids=(1, 1),
        )


def test_configuration_fingerprint_is_stable_and_excludes_artifact_location(
    tmp_path: Path,
) -> None:
    first = PigDetectorConfiguration.ultralytics(_artifact(tmp_path, "first.pt"))
    nested = tmp_path / "private-location"
    nested.mkdir()
    second = PigDetectorConfiguration.ultralytics(_artifact(nested, "second.pt"))

    assert first.fingerprint == first.fingerprint
    assert first.fingerprint == second.fingerprint
    assert str(tmp_path) not in first.fingerprint


def test_runtime_provenance_and_snapshot_are_safe_immutable_values(tmp_path: Path) -> None:
    configuration = PigDetectorConfiguration.ultralytics(
        _artifact(tmp_path),
        target_class_ids=(0,),
    )
    loaded_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    provenance = DetectorModelProvenance(
        backend_family=DetectorBackend.ULTRALYTICS,
        model_format=DetectorModelFormat.PYTORCH,
        sanitized_model_name="ultralytics-0123456789abcdef",
        artifact_fingerprint="a" * 64,
        target_class_name="pig",
        target_class_ids=(0,),
        loaded_at=loaded_at,
        runtime_device="cpu",
        configuration_fingerprint=configuration.fingerprint,
        framework_version="8.synthetic",
        provenance_complete=False,
    )

    assert str(tmp_path) not in repr(provenance)
    assert str(tmp_path) not in repr(DetectorRuntimeSnapshot.for_configuration(configuration))
    with pytest.raises(FrozenInstanceError):
        provenance.runtime_device = "cuda:0"  # type: ignore[misc]


def test_detector_telemetry_is_bounded_scalar_state(tmp_path: Path) -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    configuration = PigDetectorConfiguration.ultralytics(
        _artifact(tmp_path),
        target_class_ids=(0,),
    )
    metadata = ModelArtifactMetadata(
        "ultralytics-0123456789abcdef",
        "ultralytics-yolo",
        ((0, "pig"),),
        artifact_fingerprint="b" * 64,
    )
    provenance = DetectorModelProvenance(
        DetectorBackend.ULTRALYTICS,
        DetectorModelFormat.PYTORCH,
        "ultralytics-0123456789abcdef",
        "b" * 64,
        "pig",
        (0,),
        now,
        "cpu",
        configuration.fingerprint,
        "8.synthetic",
        False,
    )
    telemetry = DetectorRuntimeTelemetry(configuration, clock=lambda: now)
    frame = frame_packet(0)
    result = FrameDetections(
        source_id=frame.stream.stream_id,
        frame_sequence=frame.sequence_number,
        captured_at=frame.timestamp.acquired_at,
        inference_started_at=now,
        inference_completed_at=now,
        frame_width=frame.dimensions.width,
        frame_height=frame.dimensions.height,
        detections=(),
        model_id=metadata.model_id,
        model_version=None,
        artifact_fingerprint=metadata.artifact_fingerprint,
        inference_duration_ms=4.0,
    )

    telemetry.record_loaded(metadata, provenance)
    telemetry.record_inference_attempt()
    telemetry.record_success(result)
    telemetry.record_inference_attempt()
    telemetry.record_temporary_failure()
    telemetry.record_inference_attempt()
    telemetry.record_fatal_failure(malformed_output=True)
    telemetry.record_closed()
    snapshot = telemetry.snapshot()

    assert snapshot.inference_count == 3
    assert snapshot.successful_inference_count == 1
    assert snapshot.temporary_failures == 1
    assert snapshot.fatal_failures == 1
    assert snapshot.malformed_outputs == 1
    assert snapshot.first_inference_latency_ms == 4.0
    assert snapshot.average_inference_latency_ms == 4.0
    assert snapshot.closed
    assert not hasattr(telemetry, "_history")
    assert not hasattr(telemetry, "_results")
