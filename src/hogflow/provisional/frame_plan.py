"""Deterministic Phase 10.3A frame planning over the existing Phase 4 contracts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from hogflow.annotation.models import DatasetSplit, validate_opaque_identifier
from hogflow.core import InputDataError, phase4_clip_id
from hogflow.data.frame_selection import (
    ClipSamplingMetadata,
    FrameSelectionPlan,
    FrameSelectionSettings,
    FrameSelectionStrategy,
    PlannedFrame,
    create_frame_selection_plan,
)

DEMO_VIDEO_A_ID = "demo_video_a"
DEMO_VIDEO_B_ID = "demo_video_b"
EXPECTED_VIDEO_IDS = (DEMO_VIDEO_A_ID, DEMO_VIDEO_B_ID)
TRAIN_BLOCK_ID = "train_block_a"
CALIBRATION_BLOCK_ID = "validation_block_a"
HOLDOUT_BLOCK_ID = "holdout_block_b"
TRAIN_FRAME_TARGET = 48
CALIBRATION_FRAME_TARGET = 16
HOLDOUT_FRAME_TARGET = 36
DEVELOPMENT_SPLIT_RATIO = 0.75
TEMPORAL_BUFFER_SECONDS = 0.75


def phase10_3a_clip_id(video_id: str) -> str:
    """Return the stable opaque clip ID for one explicit provisional video ID."""

    if video_id not in EXPECTED_VIDEO_IDS:
        raise InputDataError("Phase 10.3A clip IDs require one authorized provisional video ID.")
    return phase4_clip_id(f"phase10_3a:{video_id}")


DEMO_A_CLIP_ID = phase10_3a_clip_id(DEMO_VIDEO_A_ID)
DEMO_B_CLIP_ID = phase10_3a_clip_id(DEMO_VIDEO_B_ID)


@dataclass(frozen=True, slots=True)
class Phase10_3aFrameBlock:
    """One deterministic time range used to sample one Phase 10.3A split."""

    block_id: str
    video_id: str
    clip_id: str
    split: DatasetSplit
    start_seconds: float
    end_seconds: float
    target_frame_count: int

    def __post_init__(self) -> None:
        validate_opaque_identifier(self.block_id, field_name="block_id")
        if self.video_id not in EXPECTED_VIDEO_IDS:
            raise InputDataError("block video_id must be one authorized provisional ID.")
        if self.clip_id != phase10_3a_clip_id(self.video_id):
            raise InputDataError("block clip_id must match the deterministic provisional clip ID.")
        if not isinstance(self.split, DatasetSplit):
            raise InputDataError("block split must be a DatasetSplit value.")
        for field_name in ("start_seconds", "end_seconds"):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise InputDataError(f"{field_name} must be finite non-negative seconds.")
        if self.end_seconds <= self.start_seconds:
            raise InputDataError("block end_seconds must be greater than start_seconds.")
        if (
            not isinstance(self.target_frame_count, int)
            or isinstance(self.target_frame_count, bool)
            or self.target_frame_count <= 0
        ):
            raise InputDataError("block target_frame_count must be a positive integer.")


@dataclass(frozen=True, slots=True)
class Phase10_3aPlanSummary:
    """Sanitized summary of the provisional A/B frame plan."""

    total_frame_count: int
    warnings: tuple[str, ...]
    blocks: tuple[Phase10_3aFrameBlock, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.total_frame_count, int)
            or isinstance(self.total_frame_count, bool)
            or self.total_frame_count < 0
        ):
            raise InputDataError("total_frame_count must be a non-negative integer.")
        if (
            not isinstance(self.warnings, tuple)
            or tuple(sorted(set(self.warnings))) != self.warnings
        ):
            raise InputDataError("warnings must be a unique sorted tuple.")
        if not isinstance(self.blocks, tuple) or not all(
            isinstance(block, Phase10_3aFrameBlock) for block in self.blocks
        ):
            raise InputDataError("blocks must be an immutable Phase10_3aFrameBlock tuple.")
        ordered = tuple(sorted(self.blocks, key=_block_sort_key))
        if ordered != self.blocks:
            raise InputDataError("blocks must be stored in deterministic order.")


def build_phase10_3a_sampling_metadata(
    durations_by_video_id: Mapping[str, float],
) -> dict[str, ClipSamplingMetadata]:
    """Build deterministic sampling metadata for the exact two provisional videos."""

    if set(durations_by_video_id) != set(EXPECTED_VIDEO_IDS):
        raise InputDataError(
            "Phase 10.3A metadata must define exactly demo_video_a and demo_video_b."
        )
    return {
        video_id: ClipSamplingMetadata(
            clip_id=phase10_3a_clip_id(video_id),
            duration_seconds=durations_by_video_id[video_id],
        )
        for video_id in EXPECTED_VIDEO_IDS
    }


def create_phase10_3a_frame_selection_plan(
    metadata_by_video_id: Mapping[str, ClipSamplingMetadata],
    *,
    settings: FrameSelectionSettings = FrameSelectionSettings(
        strategy=FrameSelectionStrategy.TARGET_COUNT
    ),
) -> FrameSelectionPlan:
    """Create the deterministic A-train/A-validation/B-holdout frame plan."""

    if not isinstance(settings, FrameSelectionSettings):
        raise InputDataError("settings must be FrameSelectionSettings.")
    metadata = _validated_metadata(metadata_by_video_id)
    blocks = declared_phase10_3a_blocks(metadata, settings=settings)
    frames: list[PlannedFrame] = []
    warnings: set[str] = set()
    for block in blocks:
        block_plan = _plan_block(block, settings=settings)
        warnings.update(block_plan.warnings)
        frames.extend(block_plan.frames)
    return FrameSelectionPlan(
        settings=_effective_plan_settings(settings, blocks),
        frames=tuple(sorted(frames, key=_frame_sort_key)),
        warnings=tuple(sorted(warnings)),
    )


def declared_phase10_3a_blocks(
    metadata_by_video_id: Mapping[str, ClipSamplingMetadata],
    *,
    settings: FrameSelectionSettings,
) -> tuple[Phase10_3aFrameBlock, ...]:
    """Return the explicit train/calibration/holdout block boundaries."""

    if not isinstance(settings, FrameSelectionSettings):
        raise InputDataError("settings must be FrameSelectionSettings.")
    metadata = _validated_metadata(metadata_by_video_id)
    development = metadata[DEMO_VIDEO_A_ID]
    holdout = metadata[DEMO_VIDEO_B_ID]
    train_end, calibration_start = _development_boundaries(
        development.duration_seconds,
        settings=settings,
    )
    return (
        Phase10_3aFrameBlock(
            block_id=TRAIN_BLOCK_ID,
            video_id=DEMO_VIDEO_A_ID,
            clip_id=development.clip_id,
            split=DatasetSplit.TRAIN,
            start_seconds=0.0,
            end_seconds=train_end,
            target_frame_count=TRAIN_FRAME_TARGET,
        ),
        Phase10_3aFrameBlock(
            block_id=CALIBRATION_BLOCK_ID,
            video_id=DEMO_VIDEO_A_ID,
            clip_id=development.clip_id,
            split=DatasetSplit.VALIDATION,
            start_seconds=calibration_start,
            end_seconds=development.duration_seconds,
            target_frame_count=CALIBRATION_FRAME_TARGET,
        ),
        Phase10_3aFrameBlock(
            block_id=HOLDOUT_BLOCK_ID,
            video_id=DEMO_VIDEO_B_ID,
            clip_id=holdout.clip_id,
            split=DatasetSplit.TEST,
            start_seconds=0.0,
            end_seconds=holdout.duration_seconds,
            target_frame_count=HOLDOUT_FRAME_TARGET,
        ),
    )


def summarize_phase10_3a_frame_selection_plan(
    plan: FrameSelectionPlan,
    metadata_by_video_id: Mapping[str, ClipSamplingMetadata],
    *,
    settings: FrameSelectionSettings,
) -> Phase10_3aPlanSummary:
    """Return the sanitized block summary for one deterministic Phase 10.3A plan."""

    if not isinstance(plan, FrameSelectionPlan):
        raise InputDataError("plan must be FrameSelectionPlan.")
    blocks = declared_phase10_3a_blocks(metadata_by_video_id, settings=settings)
    return Phase10_3aPlanSummary(
        total_frame_count=len(plan.frames),
        warnings=plan.warnings,
        blocks=blocks,
    )


def write_phase10_3a_plan_summary(summary: Phase10_3aPlanSummary, path: str | Path) -> None:
    """Atomically write one sanitized JSON summary for the provisional frame plan."""

    if not isinstance(summary, Phase10_3aPlanSummary):
        raise InputDataError("summary must be Phase10_3aPlanSummary.")
    payload = {
        "format_version": 1,
        "total_frame_count": summary.total_frame_count,
        "warnings": list(summary.warnings),
        "blocks": [
            {
                "block_id": block.block_id,
                "clip_id": block.clip_id,
                "end_seconds": block.end_seconds,
                "split": block.split.value,
                "start_seconds": block.start_seconds,
                "target_frame_count": block.target_frame_count,
                "video_id": block.video_id,
            }
            for block in summary.blocks
        ],
    }
    _atomic_write_json(Path(path), payload)


def _validated_metadata(
    metadata_by_video_id: Mapping[str, ClipSamplingMetadata],
) -> dict[str, ClipSamplingMetadata]:
    if set(metadata_by_video_id) != set(EXPECTED_VIDEO_IDS):
        raise InputDataError(
            "Phase 10.3A metadata must define exactly demo_video_a and demo_video_b."
        )
    metadata = dict(metadata_by_video_id)
    for video_id in EXPECTED_VIDEO_IDS:
        clip = metadata.get(video_id)
        if not isinstance(clip, ClipSamplingMetadata):
            raise InputDataError("Phase 10.3A metadata values must be ClipSamplingMetadata.")
        if clip.clip_id != phase10_3a_clip_id(video_id):
            raise InputDataError(
                "Phase 10.3A clip metadata must use deterministic provisional clip IDs."
            )
    if metadata[DEMO_VIDEO_A_ID].duration_seconds <= TEMPORAL_BUFFER_SECONDS:
        raise InputDataError("demo_video_a is too short for a positive temporal split buffer.")
    return metadata


def _effective_plan_settings(
    settings: FrameSelectionSettings,
    blocks: Sequence[Phase10_3aFrameBlock],
) -> FrameSelectionSettings:
    target_frame_count = max(block.target_frame_count for block in blocks)
    return FrameSelectionSettings(
        strategy=FrameSelectionStrategy.TARGET_COUNT,
        interval_seconds=settings.interval_seconds,
        target_frame_count=target_frame_count,
        maximum_frames_per_clip=target_frame_count,
        start_exclusion_seconds=settings.start_exclusion_seconds,
        end_exclusion_seconds=settings.end_exclusion_seconds,
    )


def _development_boundaries(
    duration_seconds: float,
    *,
    settings: FrameSelectionSettings,
) -> tuple[float, float]:
    split_center = duration_seconds * DEVELOPMENT_SPLIT_RATIO
    half_gap = TEMPORAL_BUFFER_SECONDS / 2
    train_end = round(split_center - half_gap, 9)
    calibration_start = round(split_center + half_gap, 9)
    minimum_window = max(1.0, settings.start_exclusion_seconds + settings.end_exclusion_seconds)
    if train_end <= minimum_window or (duration_seconds - calibration_start) <= minimum_window:
        raise InputDataError(
            "demo_video_a is too short for the deterministic train/calibration split."
        )
    if calibration_start <= train_end:
        raise InputDataError("demo_video_a split requires a positive buffer between blocks.")
    return train_end, calibration_start


def _plan_block(
    block: Phase10_3aFrameBlock,
    *,
    settings: FrameSelectionSettings,
) -> FrameSelectionPlan:
    local_settings = FrameSelectionSettings(
        strategy=FrameSelectionStrategy.TARGET_COUNT,
        interval_seconds=settings.interval_seconds,
        target_frame_count=block.target_frame_count,
        maximum_frames_per_clip=block.target_frame_count,
        start_exclusion_seconds=settings.start_exclusion_seconds,
        end_exclusion_seconds=settings.end_exclusion_seconds,
    )
    relative_plan = create_frame_selection_plan(
        (ClipSamplingMetadata(block.clip_id, block.end_seconds - block.start_seconds),),
        {block.clip_id: block.split},
        settings=local_settings,
    )
    frames = tuple(
        PlannedFrame(
            frame_id=_phase10_3a_frame_id(
                block.clip_id,
                round(block.start_seconds + frame.planned_timestamp_seconds, 9),
            ),
            clip_id=frame.clip_id,
            split=frame.split,
            planned_timestamp_seconds=round(
                block.start_seconds + frame.planned_timestamp_seconds, 9
            ),
            selection_strategy=frame.selection_strategy,
            temporal_block_id=block.block_id,
        )
        for frame in relative_plan.frames
    )
    return FrameSelectionPlan(
        settings=local_settings,
        frames=frames,
        warnings=relative_plan.warnings,
    )


def _frame_sort_key(frame: PlannedFrame) -> tuple[str, float, str]:
    return (frame.clip_id, frame.planned_timestamp_seconds, frame.frame_id)


def _block_sort_key(block: Phase10_3aFrameBlock) -> tuple[str, float, str]:
    return (block.clip_id, block.start_seconds, block.block_id)


def _phase10_3a_frame_id(clip_id: str, timestamp_seconds: float) -> str:
    value = f"hogflow-phase10-3a-frame:{clip_id}:{timestamp_seconds:.9f}"
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
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
        raise InputDataError("Unable to write the sanitized Phase 10.3A frame summary.") from exc


__all__ = [
    "CALIBRATION_BLOCK_ID",
    "CALIBRATION_FRAME_TARGET",
    "DEMO_A_CLIP_ID",
    "DEMO_B_CLIP_ID",
    "DEMO_VIDEO_A_ID",
    "DEMO_VIDEO_B_ID",
    "EXPECTED_VIDEO_IDS",
    "HOLDOUT_BLOCK_ID",
    "HOLDOUT_FRAME_TARGET",
    "Phase10_3aFrameBlock",
    "Phase10_3aPlanSummary",
    "TRAIN_BLOCK_ID",
    "TRAIN_FRAME_TARGET",
    "build_phase10_3a_sampling_metadata",
    "create_phase10_3a_frame_selection_plan",
    "declared_phase10_3a_blocks",
    "phase10_3a_clip_id",
    "summarize_phase10_3a_frame_selection_plan",
    "write_phase10_3a_plan_summary",
]
