"""Concrete framework adapters used by the generic HogFlow pipeline."""

from hogflow.adapters.opencv_video_source import OpenCVVideoSource
from hogflow.adapters.ultralytics_detector import UltralyticsDetector
from hogflow.adapters.ultralytics_tracker import UltralyticsTracker
from hogflow.adapters.yolo_baseline_trainer import YOLOBaselineTrainer

__all__ = [
    "OpenCVVideoSource",
    "UltralyticsDetector",
    "UltralyticsTracker",
    "YOLOBaselineTrainer",
]
