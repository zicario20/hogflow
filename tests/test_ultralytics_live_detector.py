from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from _phase5_2_helpers import frame_packet

from hogflow.adapters import ultralytics_live_detector as detector_module
from hogflow.adapters.ultralytics_live_detector import UltralyticsLiveDetector
from hogflow.core import ConfigurationError, DependencyUnavailableError
from hogflow.detection.errors import (
    DetectorLoadError,
    FatalInferenceError,
    InvalidClassMappingError,
    InvalidDetectorInputError,
    InvalidModelArtifactError,
    MalformedDetectorOutputError,
    TemporaryInferenceError,
    UnsupportedDetectorDeviceError,
)
from hogflow.detection.runtime import DetectorBackend, PigDetectorConfiguration
from hogflow.models import Detection


class FakeCV2:
    COLOR_RGB2BGR = 1

    @staticmethod
    def cvtColor(frame, _code):
        return frame[..., ::-1].copy()


class FakeTorch:
    class cuda:
        @staticmethod
        def is_available() -> bool:
            return False


class FakeArray:
    def __init__(self, values: object) -> None:
        self.values = values

    def cpu(self):
        return self

    def tolist(self):
        return self.values


class FakeBoxes:
    def __init__(self, xyxy, confidence, classes) -> None:
        self.xyxy = FakeArray(xyxy)
        self.conf = FakeArray(confidence)
        self.cls = FakeArray(classes)

    def __len__(self) -> int:
        return len(self.conf.values)


class FakeModel:
    names = {0: "pig", 1: "person"}
    boxes = FakeBoxes([[1, 1, 4, 5]], [0.9], [0])
    last_arguments: dict[str, object] | None = None
    closed = False
    load_calls = 0

    def __init__(self, _model_path: str) -> None:
        type(self).closed = False
        type(self).load_calls += 1

    def predict(self, **arguments: object):
        type(self).last_arguments = arguments
        return [SimpleNamespace(boxes=type(self).boxes)]

    def close(self) -> None:
        type(self).closed = True


@pytest.fixture(autouse=True)
def fake_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeModel.names = {0: "pig", 1: "person"}
    FakeModel.boxes = FakeBoxes([[1, 1, 4, 5]], [0.9], [0])
    FakeModel.last_arguments = None
    FakeModel.closed = False
    FakeModel.load_calls = 0
    monkeypatch.setattr(
        detector_module,
        "_load_runtime",
        lambda: (FakeCV2, np, FakeModel, "8.synthetic", FakeTorch),
    )


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "local-pig-model.pt"
    path.write_bytes(b"synthetic model artifact")
    return path


def test_adapter_requires_an_explicit_existing_local_artifact(tmp_path: Path) -> None:
    with pytest.raises(InvalidModelArtifactError) as captured:
        UltralyticsLiveDetector(tmp_path / "missing.pt")

    assert str(tmp_path) not in str(captured.value)


def test_framework_model_load_failure_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_factory(_path: str):
        raise RuntimeError("framework detail")

    monkeypatch.setattr(
        detector_module,
        "_load_runtime",
        lambda: (FakeCV2, np, fail_factory, "8.synthetic", FakeTorch),
    )
    artifact = _artifact(tmp_path)

    with pytest.raises(DetectorLoadError) as captured:
        UltralyticsLiveDetector(artifact).load()

    assert str(artifact) not in str(captured.value)


def test_adapter_loads_local_artifact_and_converts_without_framework_leakage(
    tmp_path: Path,
) -> None:
    artifact = _artifact(tmp_path)
    detector = UltralyticsLiveDetector(
        artifact,
        confidence_threshold=0.4,
        iou_threshold=0.5,
        image_size=320,
        wall_clock=lambda: datetime(2026, 7, 18, tzinfo=timezone.utc),
    )

    detector.load()
    result = detector.infer(frame_packet(9))
    detector.close()

    assert result.frame_sequence == 9
    assert len(result.detections) == 1
    assert all(isinstance(item, Detection) for item in result.detections)
    assert result.artifact_fingerprint == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert detector.metadata.artifact_filename == artifact.name
    assert not detector.metadata.pig_detection_provenance_complete
    assert FakeModel.last_arguments is not None
    assert FakeModel.last_arguments["classes"] == [0]
    assert FakeModel.last_arguments["max_det"] == 300
    assert FakeModel.last_arguments["half"] is False
    assert FakeModel.last_arguments["device"] == "cpu"
    assert FakeModel.last_arguments["save"] is False
    assert FakeModel.closed
    assert not detector.is_loaded


def test_adapter_filters_wrong_classes_and_low_confidence(tmp_path: Path) -> None:
    FakeModel.boxes = FakeBoxes(
        [[1, 1, 3, 3], [2, 2, 5, 5], [3, 1, 6, 4]],
        [0.8, 0.9, 0.2],
        [0, 1, 0],
    )
    detector = UltralyticsLiveDetector(_artifact(tmp_path), confidence_threshold=0.4)
    detector.load()

    result = detector.infer(frame_packet(0))

    assert len(result.detections) == 1
    assert result.detections[0].class_name == "pig"


def test_adapter_returns_an_immutable_empty_tuple(tmp_path: Path) -> None:
    FakeModel.boxes = FakeBoxes([], [], [])
    detector = UltralyticsLiveDetector(_artifact(tmp_path))
    detector.load()

    result = detector.infer(frame_packet(0))

    assert result.detections == ()
    assert isinstance(result.detections, tuple)


def test_adapter_clips_boxes_and_rejects_invalid_or_non_finite_output(tmp_path: Path) -> None:
    detector = UltralyticsLiveDetector(_artifact(tmp_path))
    detector.load()
    FakeModel.boxes = FakeBoxes([[-1, -2, 20, 20]], [0.8], [0])

    clipped = detector.infer(frame_packet(0))

    assert clipped.detections[0].bounding_box.x_min == 0
    assert clipped.detections[0].bounding_box.y_max == 6

    FakeModel.boxes = FakeBoxes([[1, 1, float("nan"), 4]], [0.8], [0])
    with pytest.raises(MalformedDetectorOutputError, match="non-finite"):
        detector.infer(frame_packet(1))

    FakeModel.boxes = FakeBoxes([[1, 1, 4, 4]], [1.5], [0])
    with pytest.raises(MalformedDetectorOutputError, match="confidence"):
        detector.infer(frame_packet(2))

    FakeModel.boxes = FakeBoxes([[20, 20, 30, 30]], [0.8], [0])
    with pytest.raises(MalformedDetectorOutputError, match="zero-area"):
        detector.infer(frame_packet(3))


def test_adapter_rejects_incompatible_class_mapping(tmp_path: Path) -> None:
    FakeModel.names = {0: "person"}
    detector = UltralyticsLiveDetector(_artifact(tmp_path))

    with pytest.raises(InvalidClassMappingError):
        detector.load()


def test_cuda_request_fails_explicitly_when_unavailable(tmp_path: Path) -> None:
    detector = UltralyticsLiveDetector(_artifact(tmp_path), device="cuda:0")

    with pytest.raises(ConfigurationError, match="CUDA"):
        detector.load()


def test_complete_local_provenance_is_exposed_without_accuracy_claim(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "artifact_sha256": artifact_hash,
                "class_mapping": {"0": "pig", "1": "person"},
                "dataset_fingerprint": "a" * 64,
                "training_run_id": "local-run-1",
                "evaluation_reference": "local-evaluation-1",
                "purpose": "pig_detection",
                "model_version": "baseline-1",
            }
        ),
        encoding="utf-8",
    )
    detector = UltralyticsLiveDetector(artifact, provenance_path=provenance)

    detector.load()

    assert detector.metadata.pig_detection_provenance_complete
    assert detector.metadata.training_run_id == "local-run-1"


def test_mismatched_provenance_is_rejected(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    provenance = tmp_path / "provenance.json"
    provenance.write_text("{}", encoding="utf-8")

    with pytest.raises(InvalidModelArtifactError, match="fingerprint"):
        detector = UltralyticsLiveDetector(artifact, provenance_path=provenance)
        detector.load()


def test_provenance_rejects_path_like_identifiers(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "class_mapping": {"0": "pig", "1": "person"},
                "dataset_fingerprint": "a" * 64,
                "training_run_id": "C:\\private\\run",
                "evaluation_reference": "local-evaluation-1",
                "purpose": "pig_detection",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(InvalidModelArtifactError):
        detector = UltralyticsLiveDetector(artifact, provenance_path=provenance)
        detector.load()


def test_configuration_factory_exposes_only_sanitized_runtime_provenance(
    tmp_path: Path,
) -> None:
    artifact = _artifact(tmp_path)
    configuration = PigDetectorConfiguration.ultralytics(
        artifact,
        target_class_ids=(0,),
        maximum_detections=17,
    )
    detector = UltralyticsLiveDetector.from_configuration(configuration)

    detector.load()
    provenance = detector.runtime_provenance

    assert detector.configuration is configuration
    assert provenance.backend_family is DetectorBackend.ULTRALYTICS
    assert provenance.sanitized_model_name.startswith("ultralytics-")
    assert provenance.runtime_device == "cpu"
    assert str(tmp_path) not in repr(provenance)
    assert FakeModel.load_calls == 1
    detector.load()
    assert FakeModel.load_calls == 1


def test_adapter_converts_multiple_target_detections_and_enforces_maximum(
    tmp_path: Path,
) -> None:
    FakeModel.boxes = FakeBoxes(
        [[1, 1, 3, 3], [3, 2, 6, 5]],
        [0.8, 0.7],
        [0, 0],
    )
    detector = UltralyticsLiveDetector(_artifact(tmp_path), maximum_detections=2)
    detector.load()

    assert len(detector.infer(frame_packet(0)).detections) == 2

    detector = UltralyticsLiveDetector(
        _artifact(tmp_path),
        maximum_detections=1,
    )
    detector.load()
    with pytest.raises(MalformedDetectorOutputError, match="maximum"):
        detector.infer(frame_packet(1))


def test_adapter_rejects_conflicting_normalized_class_mapping(tmp_path: Path) -> None:
    FakeModel.names = {0: "pig", "0": "swine"}

    with pytest.raises(InvalidClassMappingError, match="conflicting"):
        UltralyticsLiveDetector(_artifact(tmp_path)).load()


def test_adapter_distinguishes_temporary_and_fatal_backend_failures(tmp_path: Path) -> None:
    detector = UltralyticsLiveDetector(_artifact(tmp_path))
    detector.load()

    def timeout(**_arguments: object):
        raise TimeoutError("private timeout detail")

    detector._model.predict = timeout  # type: ignore[union-attr]
    with pytest.raises(TemporaryInferenceError) as temporary:
        detector.infer(frame_packet(0))
    assert "private" not in str(temporary.value)

    def fatal(**_arguments: object):
        raise RuntimeError("private backend detail")

    detector._model.predict = fatal  # type: ignore[union-attr]
    with pytest.raises(FatalInferenceError) as fatal_error:
        detector.infer(frame_packet(1))
    assert "private" not in str(fatal_error.value)


def test_adapter_rejects_invalid_input_and_malformed_result_container(tmp_path: Path) -> None:
    detector = UltralyticsLiveDetector(_artifact(tmp_path))
    detector.load()

    with pytest.raises(InvalidDetectorInputError):
        detector.infer(object())  # type: ignore[arg-type]

    detector._model.predict = lambda **_arguments: []  # type: ignore[union-attr]
    with pytest.raises(MalformedDetectorOutputError, match="exactly one"):
        detector.infer(frame_packet(0))

    detector._model.predict = lambda **_arguments: [object(), object()]  # type: ignore[union-attr]
    with pytest.raises(MalformedDetectorOutputError, match="exactly one"):
        detector.infer(frame_packet(1))


def test_device_policy_resolves_auto_and_rejects_unsupported_half_precision(
    tmp_path: Path,
) -> None:
    automatic = UltralyticsLiveDetector(_artifact(tmp_path), device="auto")
    automatic.load()
    automatic.infer(frame_packet(0))
    assert FakeModel.last_arguments is not None
    assert FakeModel.last_arguments["device"] == "cpu"

    half = UltralyticsLiveDetector(
        _artifact(tmp_path),
        device="cpu",
        half_precision=True,
    )
    with pytest.raises(UnsupportedDetectorDeviceError, match="Half precision"):
        half.load()


def test_explicit_unavailable_cuda_index_fails_before_model_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CudaTorch:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return True

            @staticmethod
            def device_count() -> int:
                return 1

    monkeypatch.setattr(
        detector_module,
        "_load_runtime",
        lambda: (FakeCV2, np, FakeModel, "8.synthetic", CudaTorch),
    )
    detector = UltralyticsLiveDetector(_artifact(tmp_path), device="cuda:2")

    with pytest.raises(UnsupportedDetectorDeviceError, match="index"):
        detector.load()
    assert FakeModel.load_calls == 0


def test_missing_runtime_dependency_is_a_sanitized_detector_load_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_runtime():
        raise DependencyUnavailableError("private dependency detail")

    monkeypatch.setattr(detector_module, "_load_runtime", missing_runtime)
    detector = UltralyticsLiveDetector(_artifact(tmp_path))

    with pytest.raises(DetectorLoadError) as failure:
        detector.load()

    assert "private" not in str(failure.value)
    assert not detector.is_loaded
