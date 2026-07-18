"""Deterministic opaque frame-selection planning without video decoding."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from hogflow.annotation.models import DatasetSplit, validate_phase4_identifier
from hogflow.core import (
    ConfigurationError,
    HogFlowError,
    InputDataError,
    configure_logging,
    get_logger,
    phase4_clip_id,
)
from hogflow.data.dataset_splitting import load_selected_clip_ids, read_split_plan

LOGGER = get_logger(__name__)


class FrameSelectionStrategy(str, Enum):
    """Supported deterministic timestamp-selection methods."""

    FIXED_INTERVAL = "fixed_interval"
    TARGET_COUNT = "target_count"
    BOUNDED_UNIFORM = "bounded_uniform"


class ExtractionStatus(str, Enum):
    """Placeholder status used before local frame extraction runs."""

    PLANNED = "planned"


@dataclass(frozen=True, slots=True)
class FrameSelectionSettings:
    """Immutable local timestamp-sampling configuration."""

    strategy: FrameSelectionStrategy = FrameSelectionStrategy.FIXED_INTERVAL
    interval_seconds: float = 1.0
    target_frame_count: int = 30
    maximum_frames_per_clip: int = 100
    start_exclusion_seconds: float = 0.25
    end_exclusion_seconds: float = 0.25

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, FrameSelectionStrategy):
            raise ConfigurationError("strategy must be a FrameSelectionStrategy value.")
        for field_name in (
            "interval_seconds",
            "start_exclusion_seconds",
            "end_exclusion_seconds",
        ):
            value = getattr(self, field_name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ConfigurationError(f"{field_name} must be finite and non-negative.")
        if self.interval_seconds <= 0:
            raise ConfigurationError("interval_seconds must be greater than zero.")
        for field_name in ("target_frame_count", "maximum_frames_per_clip"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ConfigurationError(f"{field_name} must be a positive integer.")


@dataclass(frozen=True, slots=True)
class ClipSamplingMetadata:
    """Opaque clip ID and duration used for planning only."""

    clip_id: str
    duration_seconds: float

    def __post_init__(self) -> None:
        validate_phase4_identifier(self.clip_id, field_name="clip_id")
        if (
            not isinstance(self.duration_seconds, (int, float))
            or isinstance(self.duration_seconds, bool)
            or not math.isfinite(self.duration_seconds)
            or self.duration_seconds <= 0
        ):
            raise InputDataError("duration_seconds must be finite and greater than zero.")


@dataclass(frozen=True, slots=True)
class PlannedFrame:
    """One timestamp selected for later local extraction."""

    frame_id: str
    clip_id: str
    split: DatasetSplit
    planned_timestamp_seconds: float
    selection_strategy: FrameSelectionStrategy
    extraction_status: ExtractionStatus = ExtractionStatus.PLANNED

    def __post_init__(self) -> None:
        validate_phase4_identifier(self.frame_id, field_name="frame_id")
        validate_phase4_identifier(self.clip_id, field_name="clip_id")
        if not isinstance(self.split, DatasetSplit):
            raise InputDataError("split must be a DatasetSplit value.")
        if (
            not isinstance(self.planned_timestamp_seconds, (int, float))
            or isinstance(self.planned_timestamp_seconds, bool)
            or not math.isfinite(self.planned_timestamp_seconds)
            or self.planned_timestamp_seconds < 0
        ):
            raise InputDataError("planned_timestamp_seconds must be finite and non-negative.")
        if not isinstance(self.selection_strategy, FrameSelectionStrategy):
            raise InputDataError("selection_strategy must be FrameSelectionStrategy.")
        if self.extraction_status is not ExtractionStatus.PLANNED:
            raise InputDataError("New frame plans must use planned extraction status.")


@dataclass(frozen=True, slots=True)
class FrameSelectionPlan:
    """Sanitized deterministic frame plan with no source paths or filenames."""

    settings: FrameSelectionSettings
    frames: tuple[PlannedFrame, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.settings, FrameSelectionSettings):
            raise InputDataError("settings must be FrameSelectionSettings.")
        if not isinstance(self.frames, tuple) or not all(
            isinstance(frame, PlannedFrame) for frame in self.frames
        ):
            raise InputDataError("frames must be an immutable PlannedFrame tuple.")
        frame_ids = tuple(frame.frame_id for frame in self.frames)
        sort_keys = tuple(
            (frame.clip_id, frame.planned_timestamp_seconds, frame.frame_id)
            for frame in self.frames
        )
        if tuple(sorted(sort_keys)) != sort_keys:
            raise InputDataError("Planned frames must use deterministic clip/timestamp order.")
        if len(set(frame_ids)) != len(frame_ids):
            raise InputDataError("Planned frame IDs must be unique.")
        if (
            not isinstance(self.warnings, tuple)
            or tuple(sorted(set(self.warnings))) != self.warnings
        ):
            raise InputDataError("warnings must be a unique sorted tuple.")


def create_frame_selection_plan(
    clips: Sequence[ClipSamplingMetadata],
    split_by_clip: Mapping[str, DatasetSplit],
    *,
    settings: FrameSelectionSettings = FrameSelectionSettings(),
) -> FrameSelectionPlan:
    """Plan timestamps from duration metadata without opening any video."""

    if not isinstance(settings, FrameSelectionSettings):
        raise ConfigurationError("settings must be FrameSelectionSettings.")
    clip_tuple = tuple(clips)
    if not all(isinstance(clip, ClipSamplingMetadata) for clip in clip_tuple):
        raise InputDataError("clips must contain ClipSamplingMetadata values.")
    clip_ids = tuple(clip.clip_id for clip in clip_tuple)
    if len(set(clip_ids)) != len(clip_ids):
        raise InputDataError("Clip sampling metadata must contain unique clip IDs.")
    if set(clip_ids) != set(split_by_clip):
        raise InputDataError(
            "Split assignments and clip sampling metadata must contain the same IDs."
        )
    if not all(isinstance(split, DatasetSplit) for split in split_by_clip.values()):
        raise InputDataError("Every source assignment must use a DatasetSplit value.")

    frames: list[PlannedFrame] = []
    warnings: set[str] = set()
    for clip in sorted(clip_tuple, key=lambda item: item.clip_id):
        timestamps, margin_fallback = _timestamps_for_clip(clip.duration_seconds, settings)
        if margin_fallback:
            warnings.add(f"exclusion_margins_unavailable:{clip.clip_id}")
        for timestamp in timestamps:
            frames.append(
                PlannedFrame(
                    frame_id=_frame_id(clip.clip_id, timestamp, settings.strategy),
                    clip_id=clip.clip_id,
                    split=split_by_clip[clip.clip_id],
                    planned_timestamp_seconds=timestamp,
                    selection_strategy=settings.strategy,
                )
            )
    return FrameSelectionPlan(
        settings=settings,
        frames=tuple(frames),
        warnings=tuple(sorted(warnings)),
    )


def prepare_frame_selection(
    *,
    selection_path: str | Path,
    split_plan_path: str | Path,
    inventory_path: str | Path,
    output_path: str | Path,
    settings: FrameSelectionSettings,
) -> FrameSelectionPlan:
    """Join sanitized selections with local inventory durations and write a plan."""

    selected_ids = load_selected_clip_ids(selection_path)
    split_plan = read_split_plan(split_plan_path)
    split_by_clip = {item.clip_id: item.split for item in split_plan.assignments}
    if set(selected_ids) != set(split_by_clip):
        raise InputDataError("Selection and source split plans contain different opaque clip IDs.")
    clips = _sampling_metadata_from_inventory(inventory_path, selected_ids)
    plan = create_frame_selection_plan(clips, split_by_clip, settings=settings)
    write_frame_selection_plan(plan, output_path)
    return plan


def write_frame_selection_plan(plan: FrameSelectionPlan, path: str | Path) -> None:
    """Atomically write a sanitized frame-selection plan."""

    if not isinstance(plan, FrameSelectionPlan):
        raise InputDataError("plan must be FrameSelectionPlan.")
    settings = plan.settings
    payload = {
        "format_version": 1,
        "settings": {
            "end_exclusion_seconds": settings.end_exclusion_seconds,
            "interval_seconds": settings.interval_seconds,
            "maximum_frames_per_clip": settings.maximum_frames_per_clip,
            "start_exclusion_seconds": settings.start_exclusion_seconds,
            "strategy": settings.strategy.value,
            "target_frame_count": settings.target_frame_count,
        },
        "warnings": list(plan.warnings),
        "frames": [
            {
                "clip_id": frame.clip_id,
                "extraction_status": frame.extraction_status.value,
                "frame_id": frame.frame_id,
                "planned_timestamp_seconds": frame.planned_timestamp_seconds,
                "selection_strategy": frame.selection_strategy.value,
                "split": frame.split.value,
            }
            for frame in plan.frames
        ],
    }
    _atomic_write_json(Path(path), payload, description="frame-selection plan")


def read_frame_selection_plan(path: str | Path) -> FrameSelectionPlan:
    """Read and validate one sanitized frame-selection plan."""

    payload = _load_json_object(path, description="frame-selection plan")
    try:
        settings_payload = payload["settings"]
        frames_payload = payload["frames"]
        if not isinstance(settings_payload, dict) or not isinstance(frames_payload, list):
            raise TypeError
        settings = FrameSelectionSettings(
            strategy=FrameSelectionStrategy(settings_payload["strategy"]),
            interval_seconds=settings_payload["interval_seconds"],
            target_frame_count=settings_payload["target_frame_count"],
            maximum_frames_per_clip=settings_payload["maximum_frames_per_clip"],
            start_exclusion_seconds=settings_payload["start_exclusion_seconds"],
            end_exclusion_seconds=settings_payload["end_exclusion_seconds"],
        )
        frames = tuple(
            PlannedFrame(
                frame_id=item["frame_id"],
                clip_id=item["clip_id"],
                split=DatasetSplit(item["split"]),
                planned_timestamp_seconds=item["planned_timestamp_seconds"],
                selection_strategy=FrameSelectionStrategy(item["selection_strategy"]),
                extraction_status=ExtractionStatus(item["extraction_status"]),
            )
            for item in frames_payload
        )
        return FrameSelectionPlan(
            settings=settings,
            frames=frames,
            warnings=tuple(payload.get("warnings", [])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InputDataError("Frame-selection plan has an invalid structure.") from exc


def build_parser() -> argparse.ArgumentParser:
    """Create the metadata-only frame-selection CLI parser."""

    parser = argparse.ArgumentParser(
        description="Create an opaque deterministic frame-selection plan without decoding video."
    )
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--split-plan", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--strategy",
        choices=tuple(item.value for item in FrameSelectionStrategy),
        default=FrameSelectionStrategy.FIXED_INTERVAL.value,
    )
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--target-frame-count", type=int, default=30)
    parser.add_argument("--maximum-frames", type=int, default=100)
    parser.add_argument("--start-exclusion-seconds", type=float, default=0.25)
    parser.add_argument("--end-exclusion-seconds", type=float, default=0.25)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run metadata-only frame planning and return a process status code."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        plan = prepare_frame_selection(
            selection_path=arguments.selection,
            split_plan_path=arguments.split_plan,
            inventory_path=arguments.inventory,
            output_path=arguments.output,
            settings=FrameSelectionSettings(
                strategy=FrameSelectionStrategy(arguments.strategy),
                interval_seconds=arguments.interval_seconds,
                target_frame_count=arguments.target_frame_count,
                maximum_frames_per_clip=arguments.maximum_frames,
                start_exclusion_seconds=arguments.start_exclusion_seconds,
                end_exclusion_seconds=arguments.end_exclusion_seconds,
            ),
        )
    except HogFlowError as exc:
        parser.error(str(exc))
    LOGGER.info("Frame-selection plan complete: %d opaque frames", len(plan.frames))
    return 0


def _sampling_metadata_from_inventory(
    inventory_path: str | Path,
    selected_ids: tuple[str, ...],
) -> tuple[ClipSamplingMetadata, ...]:
    payload = _load_json_object(inventory_path, description="Phase 3 inventory")
    files = payload.get("files")
    if not isinstance(files, list):
        raise InputDataError("Phase 3 inventory must contain a files array.")
    wanted = set(selected_ids)
    found: dict[str, ClipSamplingMetadata] = {}
    for item in files:
        if not isinstance(item, dict):
            raise InputDataError("Phase 3 inventory file entries must be JSON objects.")
        source_key = item.get("relative_path")
        if not isinstance(source_key, str) or not source_key:
            raise InputDataError("Phase 3 inventory contains an invalid relative source key.")
        identifier = phase4_clip_id(source_key.replace("\\", "/"))
        if identifier not in wanted:
            continue
        if identifier in found:
            raise InputDataError("Phase 3 inventory maps more than one entry to an opaque clip ID.")
        found[identifier] = ClipSamplingMetadata(
            clip_id=identifier,
            duration_seconds=item.get("duration_seconds"),
        )
    missing = sorted(wanted - set(found))
    if missing:
        raise InputDataError(
            "Phase 3 inventory is missing selected opaque clip IDs: " + ", ".join(missing)
        )
    return tuple(found[identifier] for identifier in sorted(found))


def _timestamps_for_clip(
    duration: float,
    settings: FrameSelectionSettings,
) -> tuple[tuple[float, ...], bool]:
    start = settings.start_exclusion_seconds
    end = duration - settings.end_exclusion_seconds
    fallback = start > end
    if fallback:
        start = duration / 2
        end = start
    if settings.strategy is FrameSelectionStrategy.FIXED_INTERVAL:
        count = min(
            settings.maximum_frames_per_clip,
            max(1, math.floor((end - start) / settings.interval_seconds) + 1),
        )
        values = tuple(start + index * settings.interval_seconds for index in range(count))
    elif settings.strategy is FrameSelectionStrategy.TARGET_COUNT:
        count = min(settings.target_frame_count, settings.maximum_frames_per_clip)
        values = _uniform_values(start, end, count)
    else:
        natural_count = max(1, math.floor((end - start) / settings.interval_seconds) + 1)
        values = _uniform_values(
            start,
            end,
            min(natural_count, settings.maximum_frames_per_clip),
        )
    return tuple(round(min(value, duration), 9) for value in values), fallback


def _uniform_values(start: float, end: float, count: int) -> tuple[float, ...]:
    if count == 1 or math.isclose(start, end):
        return ((start + end) / 2,)
    step = (end - start) / (count - 1)
    return tuple(start + index * step for index in range(count))


def _frame_id(
    clip_id: str,
    timestamp_seconds: float,
    strategy: FrameSelectionStrategy,
) -> str:
    value = f"hogflow-frame:{clip_id}:{strategy.value}:{timestamp_seconds:.9f}"
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def _load_json_object(path: str | Path, *, description: str) -> dict[str, Any]:
    input_path = Path(path)
    if not input_path.is_file():
        raise InputDataError(f"The local {description} is missing or is not a file.")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError(f"The local {description} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise InputDataError(f"The local {description} must contain one JSON object.")
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, Any], *, description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise InputDataError(f"Unable to write the sanitized {description}.") from exc


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ClipSamplingMetadata",
    "ExtractionStatus",
    "FrameSelectionPlan",
    "FrameSelectionSettings",
    "FrameSelectionStrategy",
    "PlannedFrame",
    "create_frame_selection_plan",
    "prepare_frame_selection",
    "read_frame_selection_plan",
    "write_frame_selection_plan",
]
