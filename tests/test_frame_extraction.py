import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from hogflow.annotation.models import DatasetSplit
from hogflow.core import InputDataError
from hogflow.data.frame_extraction import (
    ExtractedFrameStatus,
    ImageFormat,
    extract_frames,
    load_local_source_map,
    write_extraction_report,
)
from hogflow.data.frame_selection import (
    ClipSamplingMetadata,
    FrameSelectionSettings,
    create_frame_selection_plan,
)

CLIP_ID = "3" * 24


def _synthetic_video(path: Path, *, frame_count: int = 8, fps: float = 4.0) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (64, 48),
    )
    assert writer.isOpened()
    for index in range(frame_count):
        image = np.zeros((48, 64, 3), dtype=np.uint8)
        image[:, :, 1] = index * 20
        cv2.rectangle(image, (index * 2, 10), (index * 2 + 12, 30), (255, 0, 0), -1)
        writer.write(image)
    writer.release()


def _plan():
    return create_frame_selection_plan(
        (ClipSamplingMetadata(CLIP_ID, 2.0),),
        {CLIP_ID: DatasetSplit.PREPARATION},
        settings=FrameSelectionSettings(
            interval_seconds=1.0,
            maximum_frames_per_clip=2,
            start_exclusion_seconds=0,
            end_exclusion_seconds=0,
        ),
    )


def test_extracts_synthetic_frames_with_opaque_names_and_no_labels(tmp_path: Path) -> None:
    source = tmp_path / "synthetic source ü with spaces.avi"
    _synthetic_video(source)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "annotations"

    report = extract_frames(
        _plan(),
        {CLIP_ID: source},
        output,
        image_format=ImageFormat.PNG,
    )

    assert len(report.records) == 2
    assert all(record.status is ExtractedFrameStatus.EXTRACTED for record in report.records)
    assert all(record.width == 64 and record.height == 48 for record in report.records)
    assert all(record.actual_timestamp_seconds is not None for record in report.records)
    assert all(
        Path(record.image_relative_path).stem == record.frame_id for record in report.records
    )
    assert all(
        (output / Path(*record.image_relative_path.split("/"))).is_file()
        for record in report.records
    )
    assert list((output / "labels").rglob("*.txt")) == []
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash


def test_extraction_rerun_is_idempotent_and_mismatch_is_not_overwritten(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.avi"
    _synthetic_video(source)
    output = tmp_path / "annotations"
    first = extract_frames(_plan(), {CLIP_ID: source}, output)

    second = extract_frames(_plan(), {CLIP_ID: source}, output)
    assert all(record.status is ExtractedFrameStatus.EXISTING_VERIFIED for record in second.records)

    target = output / Path(*first.records[0].image_relative_path.split("/"))
    target.write_bytes(b"mismatched existing content")
    with pytest.raises(InputDataError, match="refusing to overwrite"):
        extract_frames(_plan(), {CLIP_ID: source}, output)
    assert target.read_bytes() == b"mismatched existing content"


def test_unreadable_video_uses_only_opaque_id_in_error(tmp_path: Path) -> None:
    private_name = "WhatsApp-style private filename ü.avi"
    source = tmp_path / private_name
    source.write_bytes(b"not a video")

    with pytest.raises(InputDataError) as error:
        extract_frames(_plan(), {CLIP_ID: source}, tmp_path / "output")

    assert CLIP_ID in str(error.value)
    assert private_name not in str(error.value)
    assert str(tmp_path) not in str(error.value)


@pytest.mark.parametrize(
    "local_path",
    [
        "C:/Users/synthetic user/Vídeos/WhatsApp-style name.mp4",
        "/home/synthetic user/videos/WhatsApp-style name.mp4",
        "relative folder/non-ASCII ü/WhatsApp-style name.mp4",
    ],
)
def test_source_map_accepts_private_paths_but_returns_no_serialized_output(
    tmp_path: Path,
    local_path: str,
) -> None:
    source_map_path = tmp_path / "local_source_map.json"
    source_map_path.write_text(
        json.dumps({"format_version": 1, "sources": {CLIP_ID: local_path}}),
        encoding="utf-8",
    )

    source_map = load_local_source_map(source_map_path)

    assert source_map[CLIP_ID] == Path(local_path)


def test_extraction_report_is_sanitized_and_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source.avi"
    _synthetic_video(source)
    report = extract_frames(_plan(), {CLIP_ID: source}, tmp_path / "annotations")
    output = tmp_path / "report.json"

    write_extraction_report(report, output)
    first = output.read_text(encoding="utf-8")
    write_extraction_report(report, output)

    assert output.read_text(encoding="utf-8") == first
    assert str(source) not in first
    assert source.name not in first
