from __future__ import annotations

import json
from pathlib import Path

import pytest

from hogflow.annotation.models import DatasetSplit
from hogflow.core import InputDataError
from hogflow.data.frame_selection import FrameSelectionSettings, FrameSelectionStrategy
from hogflow.provisional.frame_plan import (
    CALIBRATION_BLOCK_ID,
    CALIBRATION_FRAME_TARGET,
    DEMO_A_CLIP_ID,
    DEMO_B_CLIP_ID,
    HOLDOUT_BLOCK_ID,
    HOLDOUT_FRAME_TARGET,
    TRAIN_BLOCK_ID,
    TRAIN_FRAME_TARGET,
    build_phase10_3a_sampling_metadata,
    create_phase10_3a_frame_selection_plan,
    summarize_phase10_3a_frame_selection_plan,
    write_phase10_3a_frame_selection_plan,
    write_phase10_3a_plan_summary,
)


def _metadata():
    return build_phase10_3a_sampling_metadata(
        {
            "demo_video_a": 11.173333,
            "demo_video_b": 18.098333,
        }
    )


def _settings() -> FrameSelectionSettings:
    return FrameSelectionSettings(
        interval_seconds=0.5,
        start_exclusion_seconds=0.25,
        end_exclusion_seconds=0.25,
    )


def test_plan_is_deterministic_and_contains_no_duplicate_timestamps() -> None:
    first = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())
    second = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())

    assert first == second
    assert len({frame.frame_id for frame in first.frames}) == len(first.frames)
    assert len({(frame.clip_id, frame.planned_timestamp_seconds) for frame in first.frames}) == len(
        first.frames
    )
    assert first.settings.strategy is FrameSelectionStrategy.TARGET_COUNT


def test_plan_uses_expected_split_counts_and_target_count_metadata() -> None:
    plan = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())

    assert sum(frame.split is DatasetSplit.TRAIN for frame in plan.frames) == TRAIN_FRAME_TARGET
    assert (
        sum(frame.split is DatasetSplit.VALIDATION for frame in plan.frames)
        == CALIBRATION_FRAME_TARGET
    )
    assert sum(frame.split is DatasetSplit.TEST for frame in plan.frames) == HOLDOUT_FRAME_TARGET
    assert plan.settings.target_frame_count == TRAIN_FRAME_TARGET
    assert plan.settings.maximum_frames_per_clip == TRAIN_FRAME_TARGET


def test_video_b_frames_are_holdout_only() -> None:
    plan = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())

    assert all(
        frame.clip_id == DEMO_A_CLIP_ID
        for frame in plan.frames
        if frame.split in {DatasetSplit.TRAIN, DatasetSplit.VALIDATION}
    )
    assert all(
        frame.split is DatasetSplit.TEST for frame in plan.frames if frame.clip_id == DEMO_B_CLIP_ID
    )
    assert {
        frame.temporal_block_id for frame in plan.frames if frame.clip_id == DEMO_A_CLIP_ID
    } == {
        TRAIN_BLOCK_ID,
        CALIBRATION_BLOCK_ID,
    }
    assert {
        frame.temporal_block_id for frame in plan.frames if frame.clip_id == DEMO_B_CLIP_ID
    } == {HOLDOUT_BLOCK_ID}


def test_summary_contains_temporal_boundaries_without_private_paths(tmp_path: Path) -> None:
    plan = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())
    summary = summarize_phase10_3a_frame_selection_plan(plan, _metadata(), settings=_settings())
    output = tmp_path / "phase10_3a_summary.json"

    write_phase10_3a_plan_summary(summary, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    blocks = {block["block_id"]: block for block in payload["blocks"]}
    assert payload["total_frame_count"] == len(plan.frames)
    assert blocks[TRAIN_BLOCK_ID]["end_seconds"] < blocks[CALIBRATION_BLOCK_ID]["start_seconds"]
    assert blocks[HOLDOUT_BLOCK_ID]["split"] == DatasetSplit.TEST.value
    assert "video A.mp4" not in output.read_text(encoding="utf-8")
    assert "video B.mp4" not in output.read_text(encoding="utf-8")
    assert str(tmp_path).replace("\\", "/") not in output.read_text(encoding="utf-8")


def test_plan_writer_keeps_explicit_per_block_targets(tmp_path: Path) -> None:
    plan = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())
    summary = summarize_phase10_3a_frame_selection_plan(plan, _metadata(), settings=_settings())
    output = tmp_path / "phase10_3a_plan.json"

    write_phase10_3a_frame_selection_plan(plan, summary, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["settings"]["strategy"] == FrameSelectionStrategy.TARGET_COUNT.value
    assert payload["phase10_3a_block_plan"]["settings_scope"] == (
        "composite_defaults_plus_explicit_block_targets"
    )
    assert {
        block["block_id"]: block["target_frame_count"]
        for block in payload["phase10_3a_block_plan"]["blocks"]
    } == {
        TRAIN_BLOCK_ID: TRAIN_FRAME_TARGET,
        CALIBRATION_BLOCK_ID: CALIBRATION_FRAME_TARGET,
        HOLDOUT_BLOCK_ID: HOLDOUT_FRAME_TARGET,
    }


def test_metadata_requires_exact_authorized_video_ids() -> None:
    with pytest.raises(InputDataError, match="exactly demo_video_a and demo_video_b"):
        build_phase10_3a_sampling_metadata({"demo_video_a": 10.0})
