"""Ultralytics implementation of the Phase 5.2 live detector contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from math import isfinite
from pathlib import Path
from re import fullmatch
from time import monotonic
from types import ModuleType
from typing import Any, Callable

from hogflow.core import ConfigurationError, DependencyUnavailableError, InputDataError
from hogflow.detection.errors import (
    DetectorLifecycleError,
    DetectorLoadError,
    FatalInferenceError,
    InvalidClassMappingError,
    InvalidModelArtifactError,
    MalformedDetectorOutputError,
)
from hogflow.detection.inference import FrameDetections, ModelArtifactMetadata
from hogflow.models import BoundingBox, Detection
from hogflow.streaming.models import FramePacket

_YoloFactory = Callable[[str], Any]


def _load_runtime() -> tuple[ModuleType, ModuleType, _YoloFactory, str, ModuleType]:
    try:
        import cv2
        import numpy as np
        import torch
        from ultralytics import YOLO
    except ImportError as exc:
        raise DependencyUnavailableError(
            "Ultralytics, Torch, NumPy, and OpenCV are required for local YOLO inference."
        ) from exc
    except Exception as exc:
        raise DependencyUnavailableError(
            "The local Ultralytics inference runtime could not initialize safely."
        ) from exc
    try:
        framework_version = version("ultralytics")
    except PackageNotFoundError:
        framework_version = "unknown"
    return cv2, np, YOLO, framework_version, torch


class UltralyticsLiveDetector:
    """Load one explicit local YOLO artifact and return HogFlow detections.

    Construction and loading never accept a model nickname that Ultralytics
    could download. The artifact must already be a local file. Inference is
    serial and this adapter makes no thread-safety guarantee. Framework arrays,
    tensors, results, and model objects remain private.
    """

    def __init__(
        self,
        model_path: str | Path,
        *,
        provenance_path: str | Path | None = None,
        confidence_threshold: float = 0.4,
        iou_threshold: float = 0.5,
        image_size: int = 640,
        device: str = "cpu",
        permitted_class_ids: tuple[int, ...] | None = None,
        required_class_name: str = "pig",
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._model_path = _local_file(model_path, "Local detector model")
        self._provenance_path = (
            None
            if provenance_path is None
            else _local_file(provenance_path, "Local model provenance")
        )
        self._confidence = _probability(confidence_threshold, "confidence_threshold")
        self._iou = _probability(iou_threshold, "iou_threshold")
        if not isinstance(image_size, int) or isinstance(image_size, bool) or image_size <= 0:
            raise ConfigurationError("image_size must be a positive integer.")
        if not isinstance(device, str) or not device.strip():
            raise ConfigurationError("device must be non-empty text.")
        if not isinstance(required_class_name, str) or not required_class_name.strip():
            raise ConfigurationError("required_class_name must be non-empty text.")
        if permitted_class_ids is not None:
            if not isinstance(permitted_class_ids, tuple) or not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in permitted_class_ids
            ):
                raise ConfigurationError("permitted_class_ids must be non-negative integers.")
            if tuple(sorted(set(permitted_class_ids))) != permitted_class_ids:
                raise ConfigurationError("permitted_class_ids must be unique and sorted.")
        self._image_size = image_size
        self._device = device.strip()
        self._requested_class_ids = permitted_class_ids
        self._required_class_name = required_class_name.strip()
        self._monotonic = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._model: Any | None = None
        self._metadata: ModelArtifactMetadata | None = None
        self._permitted_class_ids: tuple[int, ...] = ()
        self._cv2: ModuleType | Any | None = None
        self._np: ModuleType | Any | None = None
        self._framework_version = "unknown"

    @property
    def metadata(self) -> ModelArtifactMetadata:
        if self._metadata is None:
            raise DetectorLifecycleError("Detector metadata is available only after loading.")
        return self._metadata

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Load and validate the explicit local model and its class mapping."""

        if self.is_loaded:
            return
        cv2, np, yolo_factory, framework_version, torch = _load_runtime()
        _validate_requested_device(self._device, torch)
        fingerprint = _sha256(self._model_path)
        try:
            model = yolo_factory(str(self._model_path))
        except Exception as exc:
            raise DetectorLoadError(
                "Ultralytics could not load the local detector artifact."
            ) from exc
        try:
            class_mapping = _class_mapping(getattr(model, "names", None))
            permitted = _permitted_classes(
                class_mapping,
                self._required_class_name,
                self._requested_class_ids,
            )
            provenance = _load_provenance(
                self._provenance_path,
                artifact_fingerprint=fingerprint,
                class_mapping=class_mapping,
            )
        except Exception:
            close_method = getattr(model, "close", None)
            if callable(close_method):
                close_method()
            raise
        self._cv2 = cv2
        self._np = np
        self._framework_version = framework_version
        self._permitted_class_ids = permitted
        self._metadata = ModelArtifactMetadata(
            model_id=f"ultralytics-yolo-{fingerprint[:16]}",
            framework="ultralytics-yolo",
            class_mapping=class_mapping,
            artifact_filename=self._model_path.name,
            artifact_fingerprint=fingerprint,
            model_version=provenance.get("model_version"),
            expected_input_size=(self._image_size, self._image_size),
            training_run_id=provenance.get("training_run_id"),
            dataset_fingerprint=provenance.get("dataset_fingerprint"),
            evaluation_reference=provenance.get("evaluation_reference"),
            pig_detection_provenance_complete=bool(provenance.get("complete", False)),
        )
        self._model = model

    def infer(self, frame: FramePacket) -> FrameDetections:
        """Infer one stream packet and keep all framework values private."""

        if not self.is_loaded or self._model is None or self._cv2 is None or self._np is None:
            raise DetectorLifecycleError("Detector must be loaded before live inference.")
        if not isinstance(frame, FramePacket):
            raise InputDataError("Live detector input must be a FramePacket.")
        started_monotonic = float(self._monotonic())
        started_at = self._wall_clock()
        try:
            rgb_frame = self._np.frombuffer(frame.payload.data, dtype=self._np.uint8).reshape(
                frame.dimensions.height,
                frame.dimensions.width,
                frame.dimensions.channels,
            )
            bgr_frame = self._cv2.cvtColor(rgb_frame, self._cv2.COLOR_RGB2BGR)
            results = self._model.predict(
                source=bgr_frame,
                classes=list(self._permitted_class_ids),
                conf=self._confidence,
                iou=self._iou,
                imgsz=self._image_size,
                device=self._device,
                save=False,
                verbose=False,
            )
        except (DetectorLifecycleError, MalformedDetectorOutputError):
            raise
        except Exception as exc:
            raise FatalInferenceError("Ultralytics live detector inference failed.") from exc
        completed_monotonic = float(self._monotonic())
        completed_at = self._wall_clock()
        if not results:
            raise MalformedDetectorOutputError("Detector returned no result container.")
        detections = _convert_detections(
            getattr(results[0], "boxes", None),
            width=frame.dimensions.width,
            height=frame.dimensions.height,
            confidence_threshold=self._confidence,
            permitted_class_ids=self._permitted_class_ids,
            class_mapping=dict(self.metadata.class_mapping),
        )
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
        """Release framework resources where supported; repeated calls are safe."""

        model = self._model
        self._model = None
        if model is not None:
            close_method = getattr(model, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception as exc:
                    raise DetectorLifecycleError("Detector resource cleanup failed.") from exc


def _local_file(value: str | Path, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise InvalidModelArtifactError(f"{name} must be a local file path.")
    path = Path(value)
    if not path.exists() or not path.is_file():
        raise InvalidModelArtifactError(f"{name} is missing or is not a file.")
    return path


def _probability(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0 < float(value) <= 1
    ):
        raise ConfigurationError(f"{name} must be greater than 0 and at most 1.")
    return float(value)


def _validate_requested_device(device: str, torch: Any) -> None:
    normalized = device.lower()
    requests_cuda = normalized.startswith("cuda") or normalized.isdigit()
    if requests_cuda and not bool(torch.cuda.is_available()):
        raise ConfigurationError("CUDA was requested explicitly but is unavailable.")


def _class_mapping(names: Mapping[Any, Any] | Sequence[Any] | None) -> tuple[tuple[int, str], ...]:
    if isinstance(names, Mapping):
        values = tuple(sorted((int(key), str(value)) for key, value in names.items()))
    elif isinstance(names, Sequence) and not isinstance(names, (str, bytes)):
        values = tuple((index, str(value)) for index, value in enumerate(names))
    else:
        raise InvalidClassMappingError("Detector artifact does not expose a class mapping.")
    if not values or any(class_id < 0 or not name.strip() for class_id, name in values):
        raise InvalidClassMappingError("Detector artifact class mapping is invalid.")
    return values


def _permitted_classes(
    class_mapping: tuple[tuple[int, str], ...],
    required_name: str,
    requested: tuple[int, ...] | None,
) -> tuple[int, ...]:
    names = dict(class_mapping)
    if requested is None:
        permitted = tuple(
            class_id
            for class_id, name in class_mapping
            if name.casefold() == required_name.casefold()
        )
    else:
        permitted = requested
    if not permitted or any(
        class_id not in names or names[class_id].casefold() != required_name.casefold()
        for class_id in permitted
    ):
        raise InvalidClassMappingError(
            "The local detector class mapping does not contain the required pig class policy."
        )
    return permitted


def _load_provenance(
    path: Path | None,
    *,
    artifact_fingerprint: str,
    class_mapping: tuple[tuple[int, str], ...],
) -> dict[str, Any]:
    if path is None:
        return {"complete": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidModelArtifactError(
            "Local model provenance is unreadable or invalid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise InvalidModelArtifactError("Local model provenance must be a JSON object.")
    if payload.get("artifact_sha256") != artifact_fingerprint:
        raise InvalidModelArtifactError("Model provenance fingerprint does not match the artifact.")
    supplied_mapping = payload.get("class_mapping")
    expected_mapping = {str(class_id): name for class_id, name in class_mapping}
    if supplied_mapping != expected_mapping:
        raise InvalidModelArtifactError(
            "Model provenance class mapping does not match the artifact."
        )
    dataset_fingerprint = payload.get("dataset_fingerprint")
    if (
        not isinstance(dataset_fingerprint, str)
        or len(dataset_fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in dataset_fingerprint)
    ):
        raise InvalidModelArtifactError("Model provenance dataset fingerprint is invalid.")
    for field_name in ("training_run_id", "evaluation_reference"):
        if (
            not isinstance(payload.get(field_name), str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", payload[field_name]) is None
        ):
            raise InvalidModelArtifactError(
                f"Model provenance {field_name} must be a non-sensitive opaque identifier."
            )
    model_version = payload.get("model_version")
    if model_version is not None and (
        not isinstance(model_version, str)
        or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", model_version) is None
    ):
        raise InvalidModelArtifactError("Model provenance version must be an opaque identifier.")
    if payload.get("purpose") != "pig_detection":
        raise InvalidModelArtifactError("Model provenance purpose must be pig_detection.")
    return {
        "complete": True,
        "model_version": model_version,
        "training_run_id": payload["training_run_id"],
        "dataset_fingerprint": dataset_fingerprint,
        "evaluation_reference": payload["evaluation_reference"],
    }


def _convert_detections(
    boxes: Any,
    *,
    width: int,
    height: int,
    confidence_threshold: float,
    permitted_class_ids: tuple[int, ...],
    class_mapping: dict[int, str],
) -> tuple[Detection, ...]:
    if boxes is None or len(boxes) == 0:
        return ()
    coordinates = _to_rows(boxes.xyxy)
    confidence_values = _to_rows(boxes.conf)
    class_values = _to_rows(boxes.cls)
    if not (len(coordinates) == len(confidence_values) == len(class_values)):
        raise MalformedDetectorOutputError("Detector output arrays have inconsistent lengths.")
    detections: list[Detection] = []
    for row, confidence, class_id in zip(
        coordinates,
        confidence_values,
        class_values,
        strict=True,
    ):
        if len(row) != 4:
            raise MalformedDetectorOutputError("Detector returned an invalid box coordinate row.")
        try:
            raw_class_id = float(class_id)
            resolved_confidence = float(confidence)
            values = tuple(float(value) for value in row)
        except (TypeError, ValueError, OverflowError) as exc:
            raise MalformedDetectorOutputError(
                "Detector output contains malformed numeric values."
            ) from exc
        if (
            not isfinite(raw_class_id)
            or not raw_class_id.is_integer()
            or not isfinite(resolved_confidence)
            or not all(isfinite(value) for value in values)
        ):
            raise MalformedDetectorOutputError("Detector output contains non-finite values.")
        if not 0.0 <= resolved_confidence <= 1.0:
            raise MalformedDetectorOutputError(
                "Detector confidence must remain between zero and one."
            )
        resolved_class_id = int(raw_class_id)
        if (
            resolved_class_id not in permitted_class_ids
            or resolved_confidence < confidence_threshold
        ):
            continue
        x_min, y_min, x_max, y_max = values
        x_min = min(max(x_min, 0.0), float(width))
        y_min = min(max(y_min, 0.0), float(height))
        x_max = min(max(x_max, 0.0), float(width))
        y_max = min(max(y_max, 0.0), float(height))
        if x_min >= x_max or y_min >= y_max:
            raise MalformedDetectorOutputError(
                "Detector output becomes zero-area after frame-boundary clipping."
            )
        detections.append(
            Detection(
                bounding_box=BoundingBox(x_min, y_min, x_max, y_max),
                confidence=resolved_confidence,
                class_id=resolved_class_id,
                class_name=class_mapping[resolved_class_id],
            )
        )
    return tuple(detections)


def _to_rows(value: Any) -> list[Any]:
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as input_file:
            for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise InvalidModelArtifactError("Local model artifact could not be fingerprinted.") from exc
    return digest.hexdigest()


__all__ = ["UltralyticsLiveDetector"]
