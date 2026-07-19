"""Expected framework-neutral failures for live detector inference."""

from hogflow.core import HogFlowError


class DetectionInferenceError(HogFlowError):
    """Base class for expected live detector failures."""


class DetectorLoadError(DetectionInferenceError):
    """Raised when a detector cannot load its configured local artifact."""


class InvalidModelArtifactError(DetectorLoadError):
    """Raised when a local model artifact is missing, invalid, or incompatible."""


class InvalidClassMappingError(DetectorLoadError):
    """Raised when model classes do not satisfy the requested detection policy."""


class DetectorLifecycleError(DetectionInferenceError):
    """Raised when load, inference, or close is requested in an invalid state."""


class TemporaryInferenceError(DetectionInferenceError):
    """Raised for one recoverable inference attempt failure."""


class FatalInferenceError(DetectionInferenceError):
    """Raised when the detector cannot continue inference safely."""


class MalformedDetectorOutputError(FatalInferenceError):
    """Raised when framework output cannot become valid HogFlow detections."""


class DetectionPreviewError(DetectionInferenceError):
    """Raised for an expected local preview failure."""


__all__ = [
    "DetectionInferenceError",
    "DetectionPreviewError",
    "DetectorLifecycleError",
    "DetectorLoadError",
    "FatalInferenceError",
    "InvalidClassMappingError",
    "InvalidModelArtifactError",
    "MalformedDetectorOutputError",
    "TemporaryInferenceError",
]
