"""Small composition helper for explicit Phase 5.1 source types."""

from __future__ import annotations

from hogflow.streaming.configuration import StreamConfiguration
from hogflow.streaming.contracts import CameraSource
from hogflow.streaming.models import FrameDimensions, SourceType
from hogflow.streaming.synthetic import SyntheticCameraSource

from .opencv_camera_source import OpenCVCameraSource
from .opencv_file_stream_source import OpenCVFileStreamSource


def create_camera_source(
    configuration: StreamConfiguration,
    *,
    synthetic_frame_count: int = 0,
    synthetic_dimensions: FrameDimensions | None = None,
) -> CameraSource:
    """Construct the one adapter explicitly selected by configuration."""

    if configuration.source_type is SourceType.SYNTHETIC:
        return SyntheticCameraSource(
            stream_id=configuration.stream_id,
            frame_count=synthetic_frame_count,
            dimensions=synthetic_dimensions or FrameDimensions(64, 48, 3),
            is_live=False,
        )
    if configuration.source_type is SourceType.FILE:
        return OpenCVFileStreamSource(configuration)
    return OpenCVCameraSource(configuration)


__all__ = ["create_camera_source"]
