"""Expected framework-neutral failures for live detector inference."""

from hogflow.core import ConfigurationError, HogFlowError, InputDataError


class DetectionInferenceError(HogFlowError):
    """Base class for expected live detector failures."""


class DetectorLoadError(DetectionInferenceError):
    """Raised when a detector cannot load its configured local artifact."""


class DetectorConfigurationError(ConfigurationError, DetectionInferenceError):
    """Raised when explicit detector runtime configuration is invalid."""


class InvalidModelArtifactError(DetectorLoadError):
    """Raised when a local model artifact is missing, invalid, or incompatible."""


class ModelArtifactMissingError(InvalidModelArtifactError):
    """Raised when an explicitly configured local model artifact is absent."""


class UnsupportedModelFormatError(InvalidModelArtifactError):
    """Raised when the configured artifact format is not supported for inference."""


class InvalidClassMappingError(DetectorLoadError):
    """Raised when model classes do not satisfy the requested detection policy."""


class UnsupportedDetectorDeviceError(DetectorConfigurationError):
    """Raised when the requested inference device cannot be used safely."""


class DetectorLifecycleError(DetectionInferenceError):
    """Raised when load, inference, or close is requested in an invalid state."""


class InvalidDetectorInputError(InputDataError, DetectionInferenceError):
    """Raised when one detector request cannot become a valid backend input."""


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
    "DetectorConfigurationError",
    "DetectorLifecycleError",
    "DetectorLoadError",
    "FatalInferenceError",
    "InvalidClassMappingError",
    "InvalidDetectorInputError",
    "InvalidModelArtifactError",
    "MalformedDetectorOutputError",
    "ModelArtifactMissingError",
    "TemporaryInferenceError",
    "UnsupportedDetectorDeviceError",
    "UnsupportedModelFormatError",
]
