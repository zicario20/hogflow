"""Immutable result models for the generic synchronous pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from hogflow.counting import CrossingEvent
from hogflow.models import Detection, Frame, Track


@dataclass(frozen=True, slots=True)
class PipelineFrameResult:
    """Framework-independent result produced after processing one frame."""

    frame: Frame
    detections: tuple[Detection, ...]
    tracks: tuple[Track, ...]
    crossing_events: tuple[CrossingEvent, ...]
    current_count: int


@dataclass(frozen=True, slots=True)
class PipelineRunSummary:
    """Small aggregate returned after one bounded or complete pipeline run."""

    processed_frames: int
    crossing_event_count: int
    positive_count: int


__all__ = ["PipelineFrameResult", "PipelineRunSummary"]
