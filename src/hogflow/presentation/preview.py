"""Pure rendering plan for the local latest-frame operator preview."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil, isfinite

from hogflow.application import PreviewFrame
from hogflow.core import InputDataError


class PreviewPrimitiveKind(str, Enum):
    """Framework-neutral canvas primitive."""

    LINE = "line"
    RECTANGLE = "rectangle"
    POINT = "point"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class PreviewPrimitive:
    """One immutable visual instruction interpreted only by the Tk adapter."""

    kind: PreviewPrimitiveKind
    coordinates: tuple[float, ...]
    text: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PreviewPrimitiveKind):
            raise InputDataError("Preview primitive kind must be explicit.")
        if not isinstance(self.coordinates, tuple) or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
            for value in self.coordinates
        ):
            raise InputDataError("Preview primitive coordinates must be finite.")
        expected = {
            PreviewPrimitiveKind.LINE: 4,
            PreviewPrimitiveKind.RECTANGLE: 4,
            PreviewPrimitiveKind.POINT: 2,
            PreviewPrimitiveKind.TEXT: 2,
        }[self.kind]
        if len(self.coordinates) != expected:
            raise InputDataError("Preview primitive has invalid coordinate arity.")
        if not isinstance(self.text, str) or len(self.text) > 256:
            raise InputDataError("Preview primitive text must be bounded.")
        if self.kind is PreviewPrimitiveKind.TEXT and not self.text:
            raise InputDataError("Preview text primitive requires text.")


@dataclass(frozen=True, slots=True)
class PreviewRenderPlan:
    """Current frame plus bounded overlay instructions for one render."""

    frame: PreviewFrame
    subsample: int
    display_width: int
    display_height: int
    primitives: tuple[PreviewPrimitive, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.frame, PreviewFrame):
            raise InputDataError("Preview render plan requires PreviewFrame.")
        for value, label in (
            (self.subsample, "subsample"),
            (self.display_width, "display width"),
            (self.display_height, "display height"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise InputDataError(f"Preview {label} must be a positive integer.")
        if not isinstance(self.primitives, tuple) or not all(
            isinstance(item, PreviewPrimitive) for item in self.primitives
        ):
            raise InputDataError("Preview primitives must be an immutable tuple.")

    @property
    def ppm_data(self) -> bytes:
        """Return one in-memory PPM payload accepted by Tk PhotoImage."""

        header = f"P6\n{self.frame.frame_width} {self.frame.frame_height}\n255\n".encode("ascii")
        return header + self.frame.rgb24


def build_preview_render_plan(
    frame: PreviewFrame,
    *,
    diagnostic_lines: tuple[str, ...] = (),
    maximum_width: int = 800,
    maximum_height: int = 450,
) -> PreviewRenderPlan:
    """Map normalized diagnostics to a deterministic bounded canvas plan."""

    if not isinstance(frame, PreviewFrame):
        raise InputDataError("Preview rendering requires PreviewFrame.")
    for value, label in (
        (maximum_width, "maximum width"),
        (maximum_height, "maximum height"),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise InputDataError(f"Preview {label} must be positive.")
    if not isinstance(diagnostic_lines, tuple) or not all(
        isinstance(item, str) and item for item in diagnostic_lines
    ):
        raise InputDataError("Preview diagnostic lines must be immutable non-empty text.")
    factor = max(
        1,
        ceil(frame.frame_width / maximum_width),
        ceil(frame.frame_height / maximum_height),
    )
    display_width = ceil(frame.frame_width / factor)
    display_height = ceil(frame.frame_height / factor)

    def point(x: float, y: float) -> tuple[float, float]:
        return (x * display_width, y * display_height)

    primitives: list[PreviewPrimitive] = []
    primitives.append(
        PreviewPrimitive(
            PreviewPrimitiveKind.LINE,
            (
                *point(frame.line.start.x, frame.line.start.y),
                *point(frame.line.end.x, frame.line.end.y),
            ),
        )
    )
    for track in frame.tracks:
        primitives.append(
            PreviewPrimitive(
                PreviewPrimitiveKind.RECTANGLE,
                (
                    track.x_min * display_width,
                    track.y_min * display_height,
                    track.x_max * display_width,
                    track.y_max * display_height,
                ),
            )
        )
        primitives.append(
            PreviewPrimitive(
                PreviewPrimitiveKind.POINT,
                point(track.anchor.x, track.anchor.y),
            )
        )
        primitives.append(
            PreviewPrimitive(
                PreviewPrimitiveKind.TEXT,
                (track.x_min * display_width, max(12.0, track.y_min * display_height - 5.0)),
                (
                    f"{track.class_name} id={track.tracker_id} "
                    f"{track.confidence:.2f} side={track.side.value}"
                ),
            )
        )
    lines = (
        f"frame={frame.frame_sequence} dimensions={frame.frame_width}x{frame.frame_height}",
        *diagnostic_lines,
        *(
            f"crossing={item.direction.value} tracker_id={item.tracker_id}"
            for item in frame.crossings
        ),
    )
    for index, value in enumerate(lines):
        primitives.append(
            PreviewPrimitive(
                PreviewPrimitiveKind.TEXT,
                (8.0, 18.0 + index * 18.0),
                value,
            )
        )
    return PreviewRenderPlan(
        frame=frame,
        subsample=factor,
        display_width=display_width,
        display_height=display_height,
        primitives=tuple(primitives),
    )


__all__ = [
    "PreviewPrimitive",
    "PreviewPrimitiveKind",
    "PreviewRenderPlan",
    "build_preview_render_plan",
]
