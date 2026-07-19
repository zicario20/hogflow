"""Framework-independent orchestration for the generic HogFlow pipeline."""

from hogflow.pipeline.generic_counting_pipeline import GenericCountingPipeline
from hogflow.pipeline.live_detection_pipeline import LiveDetectionPipeline
from hogflow.pipeline.live_tracking_pipeline import LiveTrackingPipeline
from hogflow.pipeline.models import PipelineFrameResult, PipelineRunSummary

__all__ = [
    "GenericCountingPipeline",
    "LiveDetectionPipeline",
    "LiveTrackingPipeline",
    "PipelineFrameResult",
    "PipelineRunSummary",
]
