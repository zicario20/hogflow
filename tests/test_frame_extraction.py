import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from hogflow.annotation.models import DatasetSplit
from hogflow.core import InputDataError
from hogflow.data.frame_extraction import (
    ExtractedFrameRecord,
    ExtractedFrameStatus,
    ImageFormat,
    extract_frames,
    load_local_source_map,
    write_extraction_report,
)
from hogflow.data.frame_selection import (
    ClipSamplingMetadata,
    FrameSelectionSettings,
    FrameSelectionStrategy,
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


def test_seek_retry_recovers_from_a_bounded_decode_hole(monkeypatch, tmp_path: Path) -> None:
    class FakeCapture:
        def __init__(self) -> None:
            self.position_ms = 0.0
            self.scan_ms = None

        def isOpened(self) -> bool:
            return True

        def set(self, property_id: int, value: float) -> bool:
            assert property_id == FakeCV2.CAP_PROP_POS_MSEC
            self.position_ms = value
            if value <= 700.0:
                self.scan_ms = 900.0
            else:
                self.scan_ms = None
            return True

        def read(self):
            if self.scan_ms is not None:
                current = self.scan_ms
                self.scan_ms += 50.0
                if current > 1100.0:
                    return False, None
                self.position_ms = current
                return True, np.full((12, 16, 3), 7, dtype=np.uint8)
            if self.position_ms >= 1000.0:
                return False, None
            return True, np.full((12, 16, 3), 7, dtype=np.uint8)

        def get(self, property_id: int) -> float:
            return {
                FakeCV2.CAP_PROP_FPS: 10.0,
                FakeCV2.CAP_PROP_POS_MSEC: self.position_ms,
            }.get(property_id, 0.0)

        def release(self) -> None:
            return None

    class FakeCV2(SimpleNamespace):
        CAP_PROP_FPS = 12
        CAP_PROP_POS_MSEC = 13

        @staticmethod
        def VideoCapture(_path: str) -> FakeCapture:
            return FakeCapture()

        @staticmethod
        def imencode(_extension: str, image):
            return True, np.frombuffer(image.tobytes(), dtype=np.uint8)

    from hogflow.data import frame_extraction as frame_extraction_module

    monkeypatch.setattr(frame_extraction_module, "_require_cv2", lambda: FakeCV2)
    source = tmp_path / "synthetic.avi"
    source.write_bytes(b"placeholder")
    plan = create_frame_selection_plan(
        (ClipSamplingMetadata(CLIP_ID, 1.5),),
        {CLIP_ID: DatasetSplit.TRAIN},
        settings=FrameSelectionSettings(
            strategy=FrameSelectionStrategy.TARGET_COUNT,
            target_frame_count=1,
            maximum_frames_per_clip=1,
            start_exclusion_seconds=1.0,
            end_exclusion_seconds=0.0,
        ),
    )

    report = extract_frames(plan, {CLIP_ID: source}, tmp_path / "annotations")

    assert len(report.records) == 1
    assert report.records[0].status is ExtractedFrameStatus.EXTRACTED
    assert report.records[0].actual_timestamp_seconds == pytest.approx(1.0)


def test_seek_retry_rejects_far_timestamp_substitution(monkeypatch, tmp_path: Path) -> None:
    class FakeCapture:
        def __init__(self) -> None:
            self.position_ms = 0.0

        def isOpened(self) -> bool:
            return True

        def set(self, property_id: int, value: float) -> bool:
            assert property_id == FakeCV2.CAP_PROP_POS_MSEC
            self.position_ms = value
            return True

        def read(self):
            self.position_ms = 1800.0
            return True, np.full((12, 16, 3), 9, dtype=np.uint8)

        def get(self, property_id: int) -> float:
            return {
                FakeCV2.CAP_PROP_FPS: 10.0,
                FakeCV2.CAP_PROP_POS_MSEC: self.position_ms,
            }.get(property_id, 0.0)

        def release(self) -> None:
            return None

    class FakeCV2(SimpleNamespace):
        CAP_PROP_FPS = 12
        CAP_PROP_POS_MSEC = 13

        @staticmethod
        def VideoCapture(_path: str) -> FakeCapture:
            return FakeCapture()

        @staticmethod
        def imencode(_extension: str, image):
            return True, np.frombuffer(image.tobytes(), dtype=np.uint8)

    from hogflow.data import frame_extraction as frame_extraction_module

    monkeypatch.setattr(frame_extraction_module, "_require_cv2", lambda: FakeCV2)
    source = tmp_path / "synthetic.avi"
    source.write_bytes(b"placeholder")
    plan = create_frame_selection_plan(
        (ClipSamplingMetadata(CLIP_ID, 1.5),),
        {CLIP_ID: DatasetSplit.TRAIN},
        settings=FrameSelectionSettings(
            strategy=FrameSelectionStrategy.TARGET_COUNT,
            target_frame_count=1,
            maximum_frames_per_clip=1,
            start_exclusion_seconds=1.0,
            end_exclusion_seconds=0.0,
        ),
    )

    with pytest.raises(InputDataError, match="bounded timestamp tolerance"):
        extract_frames(plan, {CLIP_ID: source}, tmp_path / "annotations")


def test_extracted_frame_temporal_block_id_must_be_opaque() -> None:
    record = ExtractedFrameRecord(
        frame_id="4" * 24,
        clip_id=CLIP_ID,
        split=DatasetSplit.TRAIN,
        image_relative_path=f"images/train/{'4' * 24}.png",
        planned_timestamp_seconds=1.0,
        actual_timestamp_seconds=1.05,
        temporal_block_id="block_a",
        width=64,
        height=48,
        checksum_sha256="a" * 64,
        status=ExtractedFrameStatus.EXTRACTED,
    )

    assert record.temporal_block_id == "block_a"

    with pytest.raises(InputDataError, match="temporal_block_id"):
        ExtractedFrameRecord(
            frame_id="5" * 24,
            clip_id=CLIP_ID,
            split=DatasetSplit.TRAIN,
            image_relative_path=f"images/train/{'5' * 24}.png",
            planned_timestamp_seconds=1.0,
            actual_timestamp_seconds=1.05,
            temporal_block_id="../private",
            width=64,
            height=48,
            checksum_sha256="b" * 64,
            status=ExtractedFrameStatus.EXTRACTED,
        )
