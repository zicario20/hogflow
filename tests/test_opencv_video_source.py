from pathlib import Path

import pytest

from hogflow.adapters.opencv_video_source import OpenCVVideoSource
from hogflow.core import InputDataError

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _write_video(path: Path, colors: list[tuple[int, int, int]], *, fps: float = 10.0) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (16, 12),
    )
    assert writer.isOpened()
    try:
        for color in colors:
            frame = np.full((12, 16, 3), color, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InputDataError, match="does not exist"):
        OpenCVVideoSource(tmp_path / "missing.avi")


def test_directory_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InputDataError, match="not a file"):
        OpenCVVideoSource(tmp_path)


def test_invalid_video_is_rejected(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.avi"
    invalid_path.write_bytes(b"not a video")

    with pytest.raises(InputDataError, match="could not open"):
        OpenCVVideoSource(invalid_path)


def test_valid_video_returns_sequential_rgb_frames_and_end_of_stream(tmp_path: Path) -> None:
    video_path = tmp_path / "sample.avi"
    _write_video(video_path, [(0, 0, 255), (0, 255, 0)], fps=10.0)
    source = OpenCVVideoSource(video_path)

    first = source.read()
    second = source.read()

    assert first is not None
    assert second is not None
    assert (first.frame_index, second.frame_index) == (0, 1)
    assert (first.timestamp_seconds, second.timestamp_seconds) == pytest.approx((0.0, 0.1))
    assert len(first.pixels) == first.width * first.height * 3
    assert first.pixels[0] > first.pixels[1]
    assert first.pixels[0] > first.pixels[2]
    assert source.read() is None
    source.close()


def test_repeated_close_is_safe(tmp_path: Path) -> None:
    video_path = tmp_path / "sample.avi"
    _write_video(video_path, [(0, 0, 0)])
    source = OpenCVVideoSource(video_path)

    source.close()
    source.close()

    assert source.read() is None
