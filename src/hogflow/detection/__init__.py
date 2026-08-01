"""Framework-independent detector contracts, models, and deterministic doubles."""

from hogflow.detection.contracts import Detector
from hogflow.detection.errors import (
    DetectionInferenceError,
    DetectionPreviewError,
    DetectorConfigurationError,
    DetectorLifecycleError,
    DetectorLoadError,
    FatalInferenceError,
    InvalidClassMappingError,
    InvalidDetectorInputError,
    InvalidModelArtifactError,
    MalformedDetectorOutputError,
    ModelArtifactMissingError,
    TemporaryInferenceError,
    UnsupportedDetectorDeviceError,
    UnsupportedModelFormatError,
)
from hogflow.detection.fakes import (
    EmptyDetector,
    FailingDetector,
    ScriptedDetector,
    SlowDetector,
    SyntheticMovingBoxDetector,
)
from hogflow.detection.inference import (
    DetectionShutdownReason,
    FrameDetections,
    LiveDetectionRunSummary,
    LiveDetectionStats,
    LiveInferenceConfiguration,
    ModelArtifactMetadata,
    PreviewAction,
)
from hogflow.detection.ports import DetectionPreview, LiveDetector
from hogflow.detection.runtime import (
    DetectorBackend,
    DetectorModelFormat,
    DetectorModelProvenance,
    DetectorRuntimeSnapshot,
    DetectorRuntimeTelemetry,
    PigDetectorConfiguration,
)
from hogflow.detection.telemetry import LiveDetectionTelemetry

__all__ = [
    "DetectionInferenceError",
    "DetectionPreview",
    "DetectionPreviewError",
    "DetectionShutdownReason",
    "DetectorBackend",
    "DetectorConfigurationError",
    "Detector",
    "DetectorLifecycleError",
    "DetectorLoadError",
    "DetectorModelFormat",
    "DetectorModelProvenance",
    "DetectorRuntimeSnapshot",
    "DetectorRuntimeTelemetry",
    "EmptyDetector",
    "FailingDetector",
    "FatalInferenceError",
    "FrameDetections",
    "InvalidClassMappingError",
    "InvalidDetectorInputError",
    "InvalidModelArtifactError",
    "LiveDetectionRunSummary",
    "LiveDetectionStats",
    "LiveDetectionTelemetry",
    "LiveDetector",
    "LiveInferenceConfiguration",
    "MalformedDetectorOutputError",
    "ModelArtifactMissingError",
    "ModelArtifactMetadata",
    "PigDetectorConfiguration",
    "PreviewAction",
    "ScriptedDetector",
    "SlowDetector",
    "SyntheticMovingBoxDetector",
    "TemporaryInferenceError",
    "UnsupportedDetectorDeviceError",
    "UnsupportedModelFormatError",
]
