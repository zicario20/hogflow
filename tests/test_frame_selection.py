import json
from pathlib import Path

import pytest

from hogflow.annotation.models import DatasetSplit
from hogflow.core import ConfigurationError, phase4_clip_id
from hogflow.data.dataset_splitting import create_source_split_plan, write_split_plan
from hogflow.data.frame_selection import (
    ClipSamplingMetadata,
    FrameSelectionSettings,
    FrameSelectionStrategy,
    create_frame_selection_plan,
    prepare_frame_selection,
    read_frame_selection_plan,
)

CLIP_ID = "e" * 24


def _create(
    settings: FrameSelectionSettings,
    *,
    duration: float = 5.0,
) -> tuple[float, ...]:
    plan = create_frame_selection_plan(
        (ClipSamplingMetadata(CLIP_ID, duration),),
        {CLIP_ID: DatasetSplit.PREPARATION},
        settings=settings,
    )
    return tuple(frame.planned_timestamp_seconds for frame in plan.frames)


def test_fixed_interval_is_bounded_by_margins_and_maximum() -> None:
    timestamps = _create(
        FrameSelectionSettings(
            strategy=FrameSelectionStrategy.FIXED_INTERVAL,
            interval_seconds=1.0,
            maximum_frames_per_clip=3,
        )
    )
    assert timestamps == (0.25, 1.25, 2.25)


def test_target_count_and_bounded_uniform_are_supported() -> None:
    target = _create(
        FrameSelectionSettings(
            strategy=FrameSelectionStrategy.TARGET_COUNT,
            target_frame_count=3,
            maximum_frames_per_clip=10,
        )
    )
    uniform = _create(
        FrameSelectionSettings(
            strategy=FrameSelectionStrategy.BOUNDED_UNIFORM,
            interval_seconds=0.5,
            maximum_frames_per_clip=3,
        )
    )
    assert target == (0.25, 2.5, 4.75)
    assert uniform == target


def test_short_clip_uses_one_midpoint_with_warning() -> None:
    settings = FrameSelectionSettings(
        start_exclusion_seconds=1.0,
        end_exclusion_seconds=1.0,
    )
    plan = create_frame_selection_plan(
        (ClipSamplingMetadata(CLIP_ID, 1.0),),
        {CLIP_ID: DatasetSplit.PREPARATION},
        settings=settings,
    )

    assert tuple(frame.planned_timestamp_seconds for frame in plan.frames) == (0.5,)
    assert plan.warnings == (f"exclusion_margins_unavailable:{CLIP_ID}",)


def test_frame_ids_are_deterministic_and_clip_order_independent() -> None:
    clips = (
        ClipSamplingMetadata("1" * 24, 3.0),
        ClipSamplingMetadata("2" * 24, 3.0),
    )
    splits = {clip.clip_id: DatasetSplit.TRAIN for clip in clips}

    first = create_frame_selection_plan(clips, splits)
    reverse = create_frame_selection_plan(tuple(reversed(clips)), splits)

    assert first == reverse
    assert len({frame.frame_id for frame in first.frames}) == len(first.frames)


def test_invalid_frame_selection_configuration_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        FrameSelectionSettings(interval_seconds=0)
    with pytest.raises(ConfigurationError):
        FrameSelectionSettings(maximum_frames_per_clip=0)


def test_prepare_frame_selection_joins_local_metadata_without_path_leakage(
    tmp_path: Path,
) -> None:
    private_name = "WhatsApp Video user name ü clip.mp4"
    clip_id = phase4_clip_id(private_name)
    selection = tmp_path / "selection.json"
    split_path = tmp_path / "split.json"
    inventory = tmp_path / "inventory.json"
    output = tmp_path / "frame-plan.json"
    selection.write_text(
        json.dumps({"decisions": [{"clip_id": clip_id, "status": "selected"}]}),
        encoding="utf-8",
    )
    write_split_plan(create_source_split_plan((clip_id,)), split_path)
    inventory.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "relative_path": private_name,
                        "duration_seconds": 2.0,
                        "source_reference": "private review note",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    plan = prepare_frame_selection(
        selection_path=selection,
        split_plan_path=split_path,
        inventory_path=inventory,
        output_path=output,
        settings=FrameSelectionSettings(maximum_frames_per_clip=2),
    )
    content = output.read_text(encoding="utf-8")

    assert read_frame_selection_plan(output) == plan
    assert private_name not in content
    assert "private review note" not in content
    assert str(tmp_path) not in content
    assert all(frame.clip_id == clip_id for frame in plan.frames)
