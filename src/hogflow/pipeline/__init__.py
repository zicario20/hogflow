"""Framework-independent orchestration for the generic HogFlow pipeline."""

from hogflow.pipeline.generic_counting_pipeline import GenericCountingPipeline
from hogflow.pipeline.models import PipelineFrameResult, PipelineRunSummary

__all__ = ["GenericCountingPipeline", "PipelineFrameResult", "PipelineRunSummary"]
