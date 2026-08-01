"""Framework-neutral configuration, provenance, and bounded detector telemetry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from pathlib import Path
from re import fullmatch
from threading import RLock
from typing import Callable

from hogflow.detection.errors import (
    DetectorConfigurationError,
    InvalidModelArtifactError,
    ModelArtifactMissingError,
    UnsupportedModelFormatError,
)
from hogflow.detection.inference import FrameDetections, ModelArtifactMetadata

_OPAQUE_TEXT = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
_SHA256 = r"[0-9a-f]{64}"
_DEVICE = r"(?:auto|cpu|cuda(?::[0-9]+)?|not_applicable)"
_MODEL_FORMATS = {
    ".pt": "pytorch",
    ".onnx": "onnx",
    ".engine": "tensorrt",
}


class DetectorBackend(str, Enum):
    """Supported detector composition families."""

    EMPTY = "empty"
    ULTRALYTICS = "ultralytics"


class DetectorModelFormat(str, Enum):
    """Safe model format labels without local artifact paths."""

    NONE = "none"
    PYTORCH = "pytorch"
    ONNX = "onnx"
    TENSORRT = "tensorrt"


@dataclass(frozen=True, slots=True)
class PigDetectorConfiguration:
    """Validated local-only detector configuration.

    ``model_path`` and ``provenance_path`` are intentionally excluded from the
    representation and fingerprint. The model artifact fingerprint is computed
    once by the adapter during controlled loading and supplies artifact identity.
    """

    backend: DetectorBackend = DetectorBackend.EMPTY
    model_path: str | Path | None = field(default=None, repr=False)
    provenance_path: str | Path | None = field(default=None, repr=False)
    target_class_name: str = "pig"
    target_class_ids: tuple[int, ...] | None = None
    confidence_threshold: float = 0.4
    iou_threshold: float = 0.5
    inference_image_size: int = 640
    device: str = "auto"
    maximum_detections: int = 300
    half_precision: bool = False
    schema_version: str = "1"

    def __post_init__(self) -> None:
        if not isinstance(self.backend, DetectorBackend):
            raise DetectorConfigurationError("Detector backend must be explicit.")
        if (
            not isinstance(self.target_class_name, str)
            or fullmatch(_OPAQUE_TEXT, self.target_class_name) is None
        ):
            raise DetectorConfigurationError(
                "Detector target class name must be non-sensitive opaque text."
            )
        if self.target_class_ids is not None:
            if not isinstance(self.target_class_ids, tuple) or not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in self.target_class_ids
            ):
                raise DetectorConfigurationError(
                    "Detector target class IDs must be non-negative integers."
                )
            if tuple(sorted(set(self.target_class_ids))) != self.target_class_ids:
                raise DetectorConfigurationError(
                    "Detector target class IDs must be unique and sorted."
                )
        object.__setattr__(
            self,
            "confidence_threshold",
            _probability(self.confidence_threshold, "confidence threshold"),
        )
        object.__setattr__(
            self,
            "iou_threshold",
            _probability(self.iou_threshold, "IoU threshold"),
        )
        for value, label in (
            (self.inference_image_size, "inference image size"),
            (self.maximum_detections, "maximum detections"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise DetectorConfigurationError(f"Detector {label} must be a positive integer.")
        if not isinstance(self.device, str) or fullmatch(_DEVICE, self.device.casefold()) is None:
            raise DetectorConfigurationError(
                "Detector device must be auto, cpu, cuda, or cuda:<non-negative index>."
            )
        object.__setattr__(self, "device", self.device.casefold())
        if not isinstance(self.half_precision, bool):
            raise DetectorConfigurationError("Detector half-precision setting must be boolean.")
        if self.schema_version != "1":
            raise DetectorConfigurationError("Unsupported detector configuration schema version.")

        model_path = _optional_path(self.model_path, "model artifact")
        provenance_path = _optional_path(self.provenance_path, "model provenance")
        object.__setattr__(self, "model_path", model_path)
        object.__setattr__(self, "provenance_path", provenance_path)
        if self.backend is DetectorBackend.EMPTY:
            if model_path is not None or provenance_path is not None:
                raise DetectorConfigurationError(
                    "Empty detector mode cannot receive model artifact paths."
                )
            if self.target_class_ids is not None or self.half_precision:
                raise DetectorConfigurationError(
                    "Empty detector mode cannot receive model execution settings."
                )
            return
        if model_path is None:
            raise ModelArtifactMissingError(
                "Ultralytics detector requires an explicit existing local model artifact."
            )
        _require_local_file(model_path, "Local detector model")
        if model_path.suffix.casefold() not in _MODEL_FORMATS:
            raise UnsupportedModelFormatError(
                "Detector model format must be .pt, .onnx, or .engine."
            )
        if provenance_path is not None:
            _require_local_file(provenance_path, "Local model provenance")
            if provenance_path.suffix.casefold() != ".json":
                raise InvalidModelArtifactError("Local model provenance must use JSON format.")

    @classmethod
    def empty(cls) -> PigDetectorConfiguration:
        """Return the explicit framework-free detector configuration."""

        return cls()

    @classmethod
    def ultralytics(
        cls,
        model_path: str | Path,
        **settings: object,
    ) -> PigDetectorConfiguration:
        """Build one validated local Ultralytics configuration."""

        return cls(
            backend=DetectorBackend.ULTRALYTICS,
            model_path=Path(model_path) if isinstance(model_path, str) else model_path,
            **settings,
        )

    @classmethod
    def local_model(
        cls,
        model_path: str | Path,
        **settings: object,
    ) -> PigDetectorConfiguration:
        """Build the currently supported explicit local-model configuration."""

        return cls.ultralytics(model_path, **settings)

    @property
    def model_format(self) -> DetectorModelFormat:
        if self.backend is DetectorBackend.EMPTY:
            return DetectorModelFormat.NONE
        assert isinstance(self.model_path, Path)
        return DetectorModelFormat(_MODEL_FORMATS[self.model_path.suffix.casefold()])

    @property
    def fingerprint(self) -> str:
        """Return a deterministic configuration fingerprint with no local path."""

        payload = {
            "backend": self.backend.value,
            "confidence_threshold": self.confidence_threshold,
            "device": self.device,
            "half_precision": self.half_precision,
            "inference_image_size": self.inference_image_size,
            "iou_threshold": self.iou_threshold,
            "maximum_detections": self.maximum_detections,
            "model_format": self.model_format.value,
            "schema_version": self.schema_version,
            "target_class_ids": self.target_class_ids,
            "target_class_name": self.target_class_name,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class DetectorModelProvenance:
    """Sanitized loaded-model identity without a filesystem path."""

    backend_family: DetectorBackend
    model_format: DetectorModelFormat
    sanitized_model_name: str
    artifact_fingerprint: str | None
    target_class_name: str
    target_class_ids: tuple[int, ...]
    loaded_at: datetime
    runtime_device: str
    configuration_fingerprint: str
    framework_version: str
    provenance_complete: bool

    def __post_init__(self) -> None:
        if not isinstance(self.backend_family, DetectorBackend):
            raise ValueError("Detector provenance backend must be explicit.")
        if not isinstance(self.model_format, DetectorModelFormat):
            raise ValueError("Detector provenance model format must be explicit.")
        if fullmatch(_OPAQUE_TEXT, self.sanitized_model_name) is None:
            raise ValueError("Detector provenance model name must be sanitized.")
        if (
            self.artifact_fingerprint is not None
            and fullmatch(_SHA256, self.artifact_fingerprint) is None
        ):
            raise ValueError("Detector provenance artifact fingerprint must be SHA-256 text.")
        if fullmatch(_OPAQUE_TEXT, self.target_class_name) is None:
            raise ValueError("Detector provenance target class must be sanitized.")
        if tuple(sorted(set(self.target_class_ids))) != self.target_class_ids or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in self.target_class_ids
        ):
            raise ValueError("Detector provenance target class IDs must be sorted and unique.")
        _aware(self.loaded_at, "Detector load time")
        if fullmatch(_DEVICE, self.runtime_device) is None:
            raise ValueError("Detector provenance runtime device is invalid.")
        if fullmatch(_SHA256, self.configuration_fingerprint) is None:
            raise ValueError("Detector provenance configuration fingerprint is invalid.")
        if (
            not isinstance(self.framework_version, str)
            or not self.framework_version.strip()
            or len(self.framework_version) > 64
            or "\\" in self.framework_version
            or "/" in self.framework_version
        ):
            raise ValueError("Detector framework version must be bounded safe text.")
        if not isinstance(self.provenance_complete, bool):
            raise ValueError("Detector provenance completion state must be boolean.")


@dataclass(frozen=True, slots=True)
class DetectorRuntimeSnapshot:
    """Constant-memory detector lifecycle and inference projection."""

    configured: bool
    backend: DetectorBackend
    model_format: DetectorModelFormat
    model_loaded: bool
    model_identity: str
    runtime_device: str
    target_class_name: str
    target_class_ids: tuple[int, ...]
    configuration_fingerprint: str
    inference_count: int
    successful_inference_count: int
    temporary_failures: int
    fatal_failures: int
    malformed_outputs: int
    detections_produced: int
    frames_with_detections: int
    average_inference_latency_ms: float
    maximum_inference_latency_ms: float
    first_inference_latency_ms: float | None
    last_successful_inference_at: datetime | None
    model_loaded_at: datetime | None
    closed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.configured, bool) or not isinstance(self.model_loaded, bool):
            raise ValueError("Detector configuration and load states must be boolean.")
        if not isinstance(self.backend, DetectorBackend) or not isinstance(
            self.model_format, DetectorModelFormat
        ):
            raise ValueError("Detector snapshot backend and format must be explicit.")
        if fullmatch(_OPAQUE_TEXT, self.model_identity) is None:
            raise ValueError("Detector snapshot model identity must be sanitized.")
        if fullmatch(_DEVICE, self.runtime_device) is None:
            raise ValueError("Detector snapshot runtime device is invalid.")
        if fullmatch(_OPAQUE_TEXT, self.target_class_name) is None:
            raise ValueError("Detector snapshot target class must be sanitized.")
        if not isinstance(self.target_class_ids, tuple) or not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in self.target_class_ids
        ):
            raise ValueError("Detector snapshot target IDs must be non-negative integers.")
        if tuple(sorted(set(self.target_class_ids))) != self.target_class_ids:
            raise ValueError("Detector snapshot target IDs must be sorted and unique.")
        if fullmatch(_SHA256, self.configuration_fingerprint) is None:
            raise ValueError("Detector snapshot configuration fingerprint is invalid.")
        for name in (
            "inference_count",
            "successful_inference_count",
            "temporary_failures",
            "fatal_failures",
            "malformed_outputs",
            "detections_produced",
            "frames_with_detections",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"Detector snapshot {name} must be non-negative.")
        if self.successful_inference_count > self.inference_count:
            raise ValueError("Successful detector inferences cannot exceed attempts.")
        if self.frames_with_detections > self.successful_inference_count:
            raise ValueError("Frames with detections cannot exceed successful inferences.")
        for name in ("average_inference_latency_ms", "maximum_inference_latency_ms"):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
                or float(value) < 0
            ):
                raise ValueError("Detector snapshot latency must be finite and non-negative.")
            object.__setattr__(self, name, float(value))
        if self.maximum_inference_latency_ms < self.average_inference_latency_ms:
            raise ValueError("Maximum detector latency cannot be below its average.")
        if self.first_inference_latency_ms is not None:
            if (
                not isinstance(self.first_inference_latency_ms, (int, float))
                or isinstance(self.first_inference_latency_ms, bool)
                or not isfinite(self.first_inference_latency_ms)
                or float(self.first_inference_latency_ms) < 0
            ):
                raise ValueError("First detector latency must be finite and non-negative.")
            object.__setattr__(
                self, "first_inference_latency_ms", float(self.first_inference_latency_ms)
            )
        if self.successful_inference_count == 0 and any(
            value is not None and value != 0.0
            for value in (
                self.average_inference_latency_ms,
                self.maximum_inference_latency_ms,
                self.first_inference_latency_ms,
                self.last_successful_inference_at,
            )
        ):
            raise ValueError("Detector inference timing requires a successful inference.")
        for value, label in (
            (self.last_successful_inference_at, "last inference time"),
            (self.model_loaded_at, "model load time"),
        ):
            if value is not None:
                _aware(value, label)
        if not isinstance(self.closed, bool):
            raise ValueError("Detector closed state must be boolean.")

    @classmethod
    def for_configuration(
        cls,
        configuration: PigDetectorConfiguration,
    ) -> DetectorRuntimeSnapshot:
        """Create the initial safe projection before backend loading."""

        if not isinstance(configuration, PigDetectorConfiguration):
            raise TypeError("Detector snapshot requires detector configuration.")
        return cls(
            configured=configuration.backend is not DetectorBackend.EMPTY,
            backend=configuration.backend,
            model_format=configuration.model_format,
            model_loaded=False,
            model_identity=(
                "empty-detector"
                if configuration.backend is DetectorBackend.EMPTY
                else f"configured-{configuration.model_format.value}"
            ),
            runtime_device=(
                "not_applicable"
                if configuration.backend is DetectorBackend.EMPTY
                else configuration.device
            ),
            target_class_name=configuration.target_class_name,
            target_class_ids=configuration.target_class_ids or (),
            configuration_fingerprint=configuration.fingerprint,
            inference_count=0,
            successful_inference_count=0,
            temporary_failures=0,
            fatal_failures=0,
            malformed_outputs=0,
            detections_produced=0,
            frames_with_detections=0,
            average_inference_latency_ms=0.0,
            maximum_inference_latency_ms=0.0,
            first_inference_latency_ms=None,
            last_successful_inference_at=None,
            model_loaded_at=None,
            closed=False,
        )

    @classmethod
    def empty(cls) -> DetectorRuntimeSnapshot:
        return cls.for_configuration(PigDetectorConfiguration.empty())


class DetectorRuntimeTelemetry:
    """Thread-safe scalar telemetry; no per-frame or error history is retained."""

    def __init__(
        self,
        configuration: PigDetectorConfiguration,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(configuration, PigDetectorConfiguration):
            raise TypeError("Detector telemetry requires detector configuration.")
        self._configuration = configuration
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        initial = DetectorRuntimeSnapshot.for_configuration(configuration)
        self._model_loaded = initial.model_loaded
        self._model_identity = initial.model_identity
        self._runtime_device = initial.runtime_device
        self._target_class_ids = initial.target_class_ids
        self._inference_count = 0
        self._successful_inference_count = 0
        self._temporary_failures = 0
        self._fatal_failures = 0
        self._malformed_outputs = 0
        self._detections_produced = 0
        self._frames_with_detections = 0
        self._total_latency_ms = 0.0
        self._maximum_latency_ms = 0.0
        self._first_latency_ms: float | None = None
        self._last_success_at: datetime | None = None
        self._model_loaded_at: datetime | None = None
        self._closed = False

    def record_loaded(
        self,
        metadata: ModelArtifactMetadata,
        provenance: DetectorModelProvenance | None = None,
    ) -> None:
        if not isinstance(metadata, ModelArtifactMetadata):
            raise TypeError("Detector telemetry load requires model metadata.")
        if provenance is not None and not isinstance(provenance, DetectorModelProvenance):
            raise TypeError("Detector telemetry provenance is invalid.")
        with self._lock:
            self._model_loaded = True
            self._closed = False
            self._model_loaded_at = self._clock()
            if provenance is not None:
                self._model_identity = provenance.sanitized_model_name
                self._runtime_device = provenance.runtime_device
                self._target_class_ids = provenance.target_class_ids
                self._model_loaded_at = provenance.loaded_at
            else:
                self._model_identity = metadata.model_id
                self._target_class_ids = tuple(
                    class_id
                    for class_id, name in metadata.class_mapping
                    if name.casefold() == self._configuration.target_class_name.casefold()
                )

    def record_load_failure(self) -> None:
        with self._lock:
            self._fatal_failures += 1
            self._model_loaded = False

    def record_inference_attempt(self) -> None:
        with self._lock:
            self._inference_count += 1

    def record_success(self, result: FrameDetections) -> None:
        if not isinstance(result, FrameDetections):
            raise TypeError("Detector telemetry success requires FrameDetections.")
        with self._lock:
            self._successful_inference_count += 1
            self._detections_produced += len(result.detections)
            self._frames_with_detections += int(bool(result.detections))
            latency = result.inference_duration_ms
            self._total_latency_ms += latency
            self._maximum_latency_ms = max(self._maximum_latency_ms, latency)
            if self._first_latency_ms is None:
                self._first_latency_ms = latency
            self._last_success_at = result.inference_completed_at

    def record_temporary_failure(self) -> None:
        with self._lock:
            self._temporary_failures += 1

    def record_fatal_failure(self, *, malformed_output: bool = False) -> None:
        with self._lock:
            self._fatal_failures += 1
            self._malformed_outputs += int(malformed_output)

    def record_closed(self) -> None:
        with self._lock:
            self._model_loaded = False
            self._closed = True

    def snapshot(self) -> DetectorRuntimeSnapshot:
        with self._lock:
            return DetectorRuntimeSnapshot(
                configured=self._configuration.backend is not DetectorBackend.EMPTY,
                backend=self._configuration.backend,
                model_format=self._configuration.model_format,
                model_loaded=self._model_loaded,
                model_identity=self._model_identity,
                runtime_device=self._runtime_device,
                target_class_name=self._configuration.target_class_name,
                target_class_ids=self._target_class_ids,
                configuration_fingerprint=self._configuration.fingerprint,
                inference_count=self._inference_count,
                successful_inference_count=self._successful_inference_count,
                temporary_failures=self._temporary_failures,
                fatal_failures=self._fatal_failures,
                malformed_outputs=self._malformed_outputs,
                detections_produced=self._detections_produced,
                frames_with_detections=self._frames_with_detections,
                average_inference_latency_ms=(
                    self._total_latency_ms / self._successful_inference_count
                    if self._successful_inference_count
                    else 0.0
                ),
                maximum_inference_latency_ms=self._maximum_latency_ms,
                first_inference_latency_ms=self._first_latency_ms,
                last_successful_inference_at=self._last_success_at,
                model_loaded_at=self._model_loaded_at,
                closed=self._closed,
            )


def _probability(value: object, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0 < float(value) <= 1
    ):
        raise DetectorConfigurationError(f"Detector {label} must be greater than 0 and at most 1.")
    return float(value)


def _optional_path(value: object, label: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, (str, Path)):
        raise DetectorConfigurationError(f"Detector {label} must be a local file path.")
    return Path(value)


def _require_local_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        raise ModelArtifactMissingError(f"{label} is missing or is not a file.")


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")


__all__ = [
    "DetectorBackend",
    "DetectorModelFormat",
    "DetectorModelProvenance",
    "DetectorRuntimeSnapshot",
    "DetectorRuntimeTelemetry",
    "PigDetectorConfiguration",
]
