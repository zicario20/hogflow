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
    CameraRecoveryConfiguration,
    CameraSnapshot,
    CameraStatus,
    CountingPipelineSnapshot,
    CountingPipelineStatus,
    PipelineFailureCategory,
)
from hogflow.camera.ports import (
    CountingFrameProcessor,
    CountingFrameProcessorFactory,
    PreviewFramePublisher,
    SharedCountingRuntimeAccess,
    VideoSourceFactory,
)
from hogflow.camera.preview_channel import LatestPreviewFrameChannel
from hogflow.camera.preview_models import (
    PreviewConfiguration,
    PreviewCrossing,
    PreviewFailureCategory,
    PreviewFrame,
    PreviewHealthState,
    PreviewSnapshot,
    PreviewTrack,
)

__all__ = [
    "ActiveCountingBinding",
    "CameraRecoveryConfiguration",
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
    "LatestPreviewFrameChannel",
    "PreviewConfiguration",
    "PreviewCrossing",
    "PreviewFailureCategory",
    "PreviewFrame",
    "PreviewFramePublisher",
    "PreviewHealthState",
    "PreviewSnapshot",
    "PreviewTrack",
    "SharedCountingRuntimeAccess",
    "StaleCameraEvidenceError",
    "VideoSourceFactory",
]
