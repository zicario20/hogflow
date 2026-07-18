"""Concrete framework adapters used by the generic HogFlow pipeline."""

from hogflow.adapters.opencv_camera_source import OpenCVCameraSource
from hogflow.adapters.opencv_file_stream_source import OpenCVFileStreamSource
from hogflow.adapters.opencv_video_source import OpenCVVideoSource
from hogflow.adapters.ultralytics_detector import UltralyticsDetector
from hogflow.adapters.ultralytics_tracker import UltralyticsTracker
from hogflow.adapters.yolo_baseline_trainer import YOLOBaselineTrainer

__all__ = [
    "OpenCVVideoSource",
    "OpenCVCameraSource",
    "OpenCVFileStreamSource",
    "UltralyticsDetector",
    "UltralyticsTracker",
    "YOLOBaselineTrainer",
]
