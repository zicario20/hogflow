"""Phase 4.2 pig-box geometry policy without image-framework dependencies."""

from __future__ import annotations

from math import isfinite

from hogflow.annotation.models import PigAnnotation
from hogflow.core import InputDataError
from hogflow.evaluation.detection_models import CoordinateSpace, EvaluationBoundingBox
from hogflow.models import BoundingBox


def normalized_pig_box_from_pixels(
    *,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    image_width: int,
    image_height: int,
) -> PigAnnotation:
    """Clip a clearly identified visible pig box to frame bounds and normalize it.

    This helper implements boundary clipping only. It never decides whether an
    ambiguous or occluded shape is a pig; that remains a human policy decision.
    A box with no positive visible extent after clipping is rejected.
    """

    if (
        not isinstance(image_width, int)
        or isinstance(image_width, bool)
        or image_width <= 0
        or not isinstance(image_height, int)
        or isinstance(image_height, bool)
        or image_height <= 0
    ):
        raise InputDataError("Image width and height must be positive integers.")
    coordinates = (x_min, y_min, x_max, y_max)
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
        for value in coordinates
    ):
        raise InputDataError("Pixel annotation coordinates must be finite numbers.")
    clipped_x_min = min(max(float(x_min), 0.0), float(image_width))
    clipped_y_min = min(max(float(y_min), 0.0), float(image_height))
    clipped_x_max = min(max(float(x_max), 0.0), float(image_width))
    clipped_y_max = min(max(float(y_max), 0.0), float(image_height))
    box = BoundingBox(
        x_min=clipped_x_min / image_width,
        y_min=clipped_y_min / image_height,
        x_max=clipped_x_max / image_width,
        y_max=clipped_y_max / image_height,
    )
    return PigAnnotation(EvaluationBoundingBox(box, CoordinateSpace.NORMALIZED))


__all__ = ["normalized_pig_box_from_pixels"]
