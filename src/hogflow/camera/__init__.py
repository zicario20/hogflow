"""Shared camera acquisition and counting-pipeline orchestration."""

from hogflow.camera.controller import CountingPipelineController
from hogflow.camera.errors import (
    CameraPipelineConfigurationError,
    CameraPipelineError,
    CameraPipelineLifecycleError,
    CameraPipelineProcessingError,
    CameraPipelineShutdownError,
    StaleCameraEvidenceError,
)
from hogflow.camera.frame_processor import (
    CrossingDetectorFactory,
    DetectorTrackingCrossingProcessor,
)
from hogflow.camera.models import (
    ActiveCountingBinding,
    CameraSnapshot,
    CameraStatus,
    CountingPipelineSnapshot,
    CountingPipelineStatus,
    PipelineFailureCategory,
)
from hogflow.camera.ports import (
    CountingFrameProcessor,
    CountingFrameProcessorFactory,
    SharedCountingRuntimeAccess,
    VideoSourceFactory,
)

__all__ = [
    "ActiveCountingBinding",
    "CameraPipelineConfigurationError",
    "CameraPipelineError",
    "CameraPipelineLifecycleError",
    "CameraPipelineProcessingError",
    "CameraPipelineShutdownError",
    "CameraSnapshot",
    "CameraStatus",
    "CountingFrameProcessor",
    "CountingFrameProcessorFactory",
    "CountingPipelineController",
    "CountingPipelineSnapshot",
    "CountingPipelineStatus",
    "CrossingDetectorFactory",
    "DetectorTrackingCrossingProcessor",
    "PipelineFailureCategory",
    "SharedCountingRuntimeAccess",
    "StaleCameraEvidenceError",
    "VideoSourceFactory",
]
