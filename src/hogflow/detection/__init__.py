"""Framework-independent detector contracts, models, and deterministic doubles."""

from hogflow.detection.contracts import Detector
from hogflow.detection.errors import (
    DetectionInferenceError,
    DetectionPreviewError,
    DetectorLifecycleError,
    DetectorLoadError,
    FatalInferenceError,
    InvalidClassMappingError,
    InvalidModelArtifactError,
    MalformedDetectorOutputError,
    TemporaryInferenceError,
)
from hogflow.detection.fakes import EmptyDetector, FailingDetector, ScriptedDetector, SlowDetector
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
from hogflow.detection.telemetry import LiveDetectionTelemetry

__all__ = [
    "DetectionInferenceError",
    "DetectionPreview",
    "DetectionPreviewError",
    "DetectionShutdownReason",
    "Detector",
    "DetectorLifecycleError",
    "DetectorLoadError",
    "EmptyDetector",
    "FailingDetector",
    "FatalInferenceError",
    "FrameDetections",
    "InvalidClassMappingError",
    "InvalidModelArtifactError",
    "LiveDetectionRunSummary",
    "LiveDetectionStats",
    "LiveDetectionTelemetry",
    "LiveDetector",
    "LiveInferenceConfiguration",
    "MalformedDetectorOutputError",
    "ModelArtifactMetadata",
    "PreviewAction",
    "ScriptedDetector",
    "SlowDetector",
    "TemporaryInferenceError",
]
