"""Ultralytics-backed generic detector adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import ModuleType
from typing import Any

from hogflow.core import (
    ConfigurationError,
    DependencyUnavailableError,
    HogFlowError,
    InputDataError,
    get_logger,
)
from hogflow.models import BoundingBox, Detection, Frame

_LOGGER = get_logger(__name__)


def _load_runtime() -> tuple[ModuleType, ModuleType, type[Any]]:
    """Load concrete detector dependencies only when the adapter is used."""

    try:
        import cv2
        import numpy as np
        from ultralytics import YOLO
    except ImportError as exc:
        raise DependencyUnavailableError(
            "Ultralytics, NumPy, and OpenCV are required for detection. "
            'Install with pip install -e ".[dev]".'
        ) from exc
    return cv2, np, YOLO


def _class_names_by_id(names: Mapping[Any, Any] | Sequence[Any]) -> dict[int, str]:
    if isinstance(names, Mapping):
        return {int(class_id): str(name) for class_id, name in names.items()}
    return {class_id: str(name) for class_id, name in enumerate(names)}


def _resolve_class_id(class_name: str, names: Mapping[Any, Any] | Sequence[Any]) -> int:
    names_by_id = _class_names_by_id(names)
    matches = [class_id for class_id, name in names_by_id.items() if name == class_name]
    if matches:
        return matches[0]
    available = ", ".join(sorted(names_by_id.values()))
    raise ConfigurationError(
        f"Requested class {class_name!r} is not available in the selected model. "
        f"Available classes: {available}"
    )


def _to_rows(value: Any) -> list[Any]:
    """Convert a private tensor/array result to ordinary Python rows."""

    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


class UltralyticsDetector:
    """Run one generic Ultralytics detector and return HogFlow detections only.

    The adapter accepts packed RGB ``Frame`` bytes, reconstructs one array,
    converts it to OpenCV-style BGR input, and keeps all model result objects
    private. It performs detection exactly once per call and never tracks,
    annotates, counts, or writes output.
    """

    def __init__(
        self,
        model_name: str,
        class_name: str,
        confidence: float,
        device: str | None = None,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ConfigurationError("Detector model name must be a non-empty string.")
        if not isinstance(class_name, str) or not class_name.strip():
            raise ConfigurationError("Requested class must not be empty.")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ConfigurationError("Confidence must be a number in the range (0, 1].")
        if not 0.0 < float(confidence) <= 1.0:
            raise ConfigurationError("Confidence must be greater than 0 and at most 1.")

        self.model_name = model_name.strip()
        self.class_name = class_name.strip()
        self.confidence = float(confidence)
        self.device = device
        self._cv2, self._np, yolo_class = _load_runtime()
        try:
            self._model = yolo_class(self.model_name)
        except Exception as exc:
            raise HogFlowError(f"Could not load detector model {self.model_name!r}: {exc}") from exc
        self.class_id = _resolve_class_id(self.class_name, self._model.names)
        _LOGGER.debug(
            "Loaded generic detector model for class %r at confidence %.3f",
            self.class_name,
            self.confidence,
        )

    def predict(self, frame: Frame) -> tuple[Detection, ...]:
        """Detect the configured class in one immutable HogFlow frame."""

        if not isinstance(frame, Frame):
            raise InputDataError("Detector input must be a HogFlow Frame.")

        rgb_frame = self._np.frombuffer(frame.pixels, dtype=self._np.uint8).reshape(
            frame.height,
            frame.width,
            3,
        )
        bgr_frame = self._cv2.cvtColor(rgb_frame, self._cv2.COLOR_RGB2BGR)
        arguments: dict[str, object] = {
            "source": bgr_frame,
            "classes": [self.class_id],
            "conf": self.confidence,
            "verbose": False,
        }
        if self.device is not None:
            arguments["device"] = self.device

        try:
            results = self._model.predict(**arguments)
        except Exception as exc:
            raise HogFlowError(
                f"Detector inference failed at frame {frame.frame_index}: {exc}"
            ) from exc
        if not results:
            raise HogFlowError(
                f"Detector returned no result container at frame {frame.frame_index}."
            )

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return ()

        xyxy_rows = _to_rows(boxes.xyxy)
        confidence_values = _to_rows(boxes.conf)
        class_values = _to_rows(boxes.cls)
        detections: list[Detection] = []
        for coordinates, confidence, class_id in zip(
            xyxy_rows,
            confidence_values,
            class_values,
            strict=True,
        ):
            resolved_class_id = int(class_id)
            resolved_confidence = float(confidence)
            if resolved_class_id != self.class_id or resolved_confidence < self.confidence:
                continue
            x_min, y_min, x_max, y_max = (float(value) for value in coordinates)
            detections.append(
                Detection(
                    bounding_box=BoundingBox(x_min, y_min, x_max, y_max),
                    confidence=resolved_confidence,
                    class_id=resolved_class_id,
                    class_name=self.class_name,
                )
            )
        return tuple(detections)
