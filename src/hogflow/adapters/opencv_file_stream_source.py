"""OpenCV local-file stream adapter for deterministic development only."""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from types import ModuleType
from typing import Any, Callable

from hogflow.streaming.configuration import StreamConfiguration
from hogflow.streaming.errors import StreamOpenError
from hogflow.streaming.models import SourceType

from .opencv_camera_source import OpenCVCameraSource, _CaptureFactory


class OpenCVFileStreamSource(OpenCVCameraSource):
    """Read a local file once with explicit non-live EOF semantics."""

    def __init__(
        self,
        configuration: StreamConfiguration,
        *,
        capture_factory: _CaptureFactory | None = None,
        cv2_module: ModuleType | Any | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if configuration.source_type is not SourceType.FILE:
            raise StreamOpenError("OpenCV file adapter requires an explicit file source.")
        protected = configuration.protected_source
        if protected is None:
            raise StreamOpenError("Local development source is missing.")
        local_path = Path(protected.reveal_for_adapter())
        if not local_path.exists() or not local_path.is_file():
            raise StreamOpenError("Local development video is missing or is not a file.")
        super().__init__(
            configuration,
            capture_factory=capture_factory,
            cv2_module=cv2_module,
            monotonic_clock=monotonic_clock,
        )


__all__ = ["OpenCVFileStreamSource"]
