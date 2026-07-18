from pathlib import Path

import cv2
import numpy as np
import pytest

from hogflow.data.models import CameraStabilityLabel, VideoInspectionSettings
from hogflow.video import metadata as metadata_module
from hogflow.video.metadata import OpenCVVideoMetadataReader


def _textured_frame(width: int = 160, height: int = 120) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(10, height, 20):
        for x in range(10, width, 20):
            color = ((x * 3) % 255, (y * 5) % 255, ((x + y) * 2) % 255)
            cv2.circle(frame, (x, y), 3, color, -1)
    cv2.rectangle(frame, (20, 20), (140, 100), (220, 220, 220), 2)
    return frame


def _write_video(path: Path, frames: list[np.ndarray], *, fps: float = 10.0) -> None:
    height, width = frames[0].shape[:2]
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height),
    )
    assert writer.isOpened(), "Synthetic MJPG writer is unavailable"
    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()


def test_valid_synthetic_video_metadata_uses_bounded_sampling(tmp_path: Path) -> None:
    video = tmp_path / "valid.avi"
    base = _textured_frame()
    _write_video(video, [base.copy() for _ in range(20)])
    reader = OpenCVVideoMetadataReader(
        VideoInspectionSettings(sample_frame_count=5, minimum_motion_pairs=2)
    )

    metadata = reader.inspect(video, relative_path="valid.avi")

    assert metadata.readable is True
    assert metadata.width == 160
    assert metadata.height == 120
    assert metadata.fps == pytest.approx(10.0)
    assert metadata.frame_count == 20
    assert metadata.duration_seconds == pytest.approx(2.0)
    assert metadata.codec
    assert metadata.sampled_frame_count == 5
    assert metadata.validation_errors == ()
    assert metadata.stability_label is CameraStabilityLabel.LIKELY_STATIC


def test_global_camera_translation_is_labeled_moving(tmp_path: Path) -> None:
    video = tmp_path / "translated.avi"
    base = _textured_frame()
    height, width = base.shape[:2]
    frames = [
        cv2.warpAffine(
            base,
            np.float32([[1, 0, index * 3], [0, 1, 0]]),
            (width, height),
        )
        for index in range(12)
    ]
    _write_video(video, frames)
    reader = OpenCVVideoMetadataReader(
        VideoInspectionSettings(
            sample_frame_count=6,
            static_threshold_percent=0.1,
            moving_threshold_percent=0.5,
            minimum_motion_pairs=2,
        )
    )

    metadata = reader.inspect(video, relative_path="translated.avi")

    assert metadata.stability_label is CameraStabilityLabel.MOVING_CAMERA
    assert metadata.stability_score_percent is not None
    assert metadata.stability_score_percent >= 0.5


def test_insufficient_visual_features_return_unknown(tmp_path: Path) -> None:
    video = tmp_path / "blank.avi"
    blank = np.zeros((80, 100, 3), dtype=np.uint8)
    _write_video(video, [blank.copy() for _ in range(8)])

    metadata = OpenCVVideoMetadataReader().inspect(video, relative_path="blank.avi")

    assert metadata.readable is True
    assert metadata.stability_score_percent is None
    assert metadata.stability_label is CameraStabilityLabel.UNKNOWN


def test_corrupt_video_is_unreadable(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.avi"
    corrupt.write_bytes(b"not a video")

    metadata = OpenCVVideoMetadataReader().inspect(corrupt, relative_path="corrupt.avi")

    assert metadata.readable is False
    assert metadata.validation_errors == ("file_cannot_be_opened",)


def test_unsupported_extension_is_flagged_without_opening_video(tmp_path: Path) -> None:
    unsupported = tmp_path / "clip.xyz"
    unsupported.write_bytes(b"content")

    metadata = OpenCVVideoMetadataReader().inspect(
        unsupported,
        relative_path="clip.xyz",
    )

    assert metadata.readable is False
    assert metadata.validation_errors == ("unsupported_extension",)


def test_invalid_backend_properties_and_decode_failure_are_flagged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "invalid.avi"
    video.write_bytes(b"placeholder")

    class FakeCapture:
        def isOpened(self) -> bool:
            return True

        def get(self, _property: int) -> float:
            return 0.0

        def read(self) -> tuple[bool, None]:
            return False, None

        def release(self) -> None:
            return None

    class FakeCV2:
        CAP_PROP_FRAME_WIDTH = 1
        CAP_PROP_FRAME_HEIGHT = 2
        CAP_PROP_FPS = 3
        CAP_PROP_FRAME_COUNT = 4
        CAP_PROP_FOURCC = 5

        @staticmethod
        def VideoCapture(_path: str) -> FakeCapture:
            return FakeCapture()

    monkeypatch.setattr(metadata_module, "_load_runtime", lambda: (FakeCV2, object()))

    metadata = OpenCVVideoMetadataReader().inspect(video, relative_path="invalid.avi")

    assert metadata.readable is False
    assert set(metadata.validation_errors) == {
        "invalid_dimensions",
        "invalid_fps",
        "invalid_frame_count",
        "zero_duration",
        "bounded_decode_failure",
    }


def test_partial_bounded_decode_failure_is_readable_but_flagged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "partial.avi"
    base = _textured_frame()
    _write_video(video, [base.copy() for _ in range(4)])
    reader = OpenCVVideoMetadataReader()
    monkeypatch.setattr(
        reader,
        "_sample_frames",
        lambda *args, **kwargs: ([base], True),
    )

    metadata = reader.inspect(video, relative_path="partial.avi")

    assert metadata.readable is True
    assert "bounded_decode_failure" in metadata.validation_errors


def test_dimension_change_helper_detects_inconsistent_frames() -> None:
    frames = [
        np.zeros((20, 30, 3), dtype=np.uint8),
        np.zeros((21, 30, 3), dtype=np.uint8),
    ]

    assert metadata_module._dimensions_change(frames) is True


def test_dimension_change_during_sample_is_flagged_without_motion_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "dimensions.avi"
    base = _textured_frame()
    _write_video(video, [base.copy() for _ in range(4)])
    reader = OpenCVVideoMetadataReader()
    changed = np.zeros((base.shape[0] + 1, base.shape[1], 3), dtype=np.uint8)
    monkeypatch.setattr(
        reader,
        "_sample_frames",
        lambda *args, **kwargs: ([base, changed], False),
    )

    metadata = reader.inspect(video, relative_path="dimensions.avi")

    assert "dimensions_changed_during_decoding" in metadata.validation_errors
    assert metadata.stability_label is CameraStabilityLabel.UNKNOWN


def test_sample_indices_are_deterministic_and_bounded() -> None:
    assert metadata_module._sample_indices(1000, 5) == (0, 250, 500, 749, 999)
    assert metadata_module._sample_indices(2, 12) == (0, 1)
