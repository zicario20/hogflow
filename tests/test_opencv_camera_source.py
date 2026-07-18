from pathlib import Path
from types import SimpleNamespace

import pytest

from hogflow.adapters.camera_source_factory import create_camera_source
from hogflow.adapters.opencv_camera_source import OpenCVCameraSource
from hogflow.adapters.opencv_file_stream_source import OpenCVFileStreamSource
from hogflow.streaming.configuration import StreamConfiguration
from hogflow.streaming.errors import StreamFatalReadError, StreamOpenError
from hogflow.streaming.models import SourceType, StreamReadStatus

np = pytest.importorskip("numpy")


class FakeCapture:
    def __init__(self, frames: list[object], *, opened: bool = True) -> None:
        self.frames = list(frames)
        self.opened = opened
        self.released = False
        self.set_calls: list[tuple[int, float]] = []
        self.position_ms = 0.0

    def isOpened(self) -> bool:
        return self.opened and not self.released

    def read(self):
        if not self.frames:
            return False, None
        value = self.frames.pop(0)
        self.position_ms += 100.0
        if isinstance(value, BaseException):
            raise value
        return True, value

    def release(self) -> None:
        self.released = True

    def set(self, property_id: int, value: float) -> bool:
        self.set_calls.append((property_id, value))
        return True

    def get(self, property_id: int) -> float:
        return {
            FakeCV2.CAP_PROP_FRAME_WIDTH: 16.0,
            FakeCV2.CAP_PROP_FRAME_HEIGHT: 12.0,
            FakeCV2.CAP_PROP_FPS: 10.0,
            FakeCV2.CAP_PROP_POS_MSEC: self.position_ms,
        }.get(property_id, 0.0)


class FakeCV2(SimpleNamespace):
    CAP_ANY = 0
    CAP_DSHOW = 1
    CAP_FFMPEG = 2
    CAP_GSTREAMER = 3
    CAP_MSMF = 4
    CAP_V4L2 = 5
    CAP_PROP_FRAME_WIDTH = 10
    CAP_PROP_FRAME_HEIGHT = 11
    CAP_PROP_FPS = 12
    CAP_PROP_POS_MSEC = 13
    CAP_PROP_OPEN_TIMEOUT_MSEC = 14
    CAP_PROP_READ_TIMEOUT_MSEC = 15
    COLOR_BGR2RGB = 20

    @staticmethod
    def cvtColor(frame, _code):
        return frame[:, :, ::-1].copy()


def _frame(color: tuple[int, int, int] = (1, 2, 3)):
    return np.full((12, 16, 3), color, dtype=np.uint8)


def test_usb_adapter_converts_to_rgb_and_records_requested_and_observed_settings() -> None:
    capture = FakeCapture([_frame((1, 2, 3))])
    calls: list[tuple[object, int, tuple[int, ...]]] = []

    def factory(source, backend, parameters):
        calls.append((source, backend, parameters))
        return capture

    configuration = StreamConfiguration.usb(
        "usb-test",
        device_index=2,
        requested_width=640,
        requested_height=480,
        requested_fps=15,
        backend_preference="dshow",
    )
    source = OpenCVCameraSource(
        configuration,
        capture_factory=factory,
        cv2_module=FakeCV2,
    )

    source.open()
    result = source.read()
    source.close()

    assert calls == [(2, FakeCV2.CAP_DSHOW, ())]
    assert result.frame is not None
    assert result.frame.payload.data[:3] == bytes((3, 2, 1))
    assert result.frame.dimensions.width == 16
    assert source.health().observed_dimensions is not None
    assert source.health().observed_fps == 10.0
    assert len(capture.set_calls) == 3
    assert capture.released


def test_rtsp_timeout_parameters_are_runtime_only_and_repr_is_safe() -> None:
    account = "camera" + "-user"
    runtime_value = "temporary" + "-value"
    host = ".".join(("203", "0", "113", "9"))
    raw_url = "rt" + f"sp://{account}:{runtime_value}@{host}:8554/live"
    captured_source: list[object] = []

    def factory(source, _backend, parameters):
        captured_source.append(source)
        assert FakeCV2.CAP_PROP_OPEN_TIMEOUT_MSEC in parameters
        assert FakeCV2.CAP_PROP_READ_TIMEOUT_MSEC in parameters
        return FakeCapture([_frame()])

    configuration = StreamConfiguration.rtsp("rtsp-test", raw_url, read_timeout_seconds=2)
    source = OpenCVCameraSource(
        configuration,
        capture_factory=factory,
        cv2_module=FakeCV2,
    )
    source.open()
    source.close()

    assert captured_source == [raw_url]
    rendered = repr(configuration) + repr(source.health())
    assert account not in rendered
    assert runtime_value not in rendered
    assert host not in rendered


def test_open_failure_releases_capture_and_omits_locator_from_error() -> None:
    capture = FakeCapture([], opened=False)
    raw_url = "rt" + "sp://" + "synthetic:runtime" + "@203.0.113.1/live"
    source = OpenCVCameraSource(
        StreamConfiguration.rtsp("camera", raw_url),
        capture_factory=lambda *_args: capture,
        cv2_module=FakeCV2,
    )

    with pytest.raises(StreamOpenError) as captured:
        source.open()

    assert raw_url not in str(captured.value)
    assert capture.released
    assert not source.is_open()


def test_fatal_frame_error_releases_resource() -> None:
    capture = FakeCapture([np.zeros((4, 4), dtype=np.uint8)])
    source = OpenCVCameraSource(
        StreamConfiguration.usb("camera"),
        capture_factory=lambda *_args: capture,
        cv2_module=FakeCV2,
    )
    source.open()

    with pytest.raises(StreamFatalReadError):
        source.read()

    assert capture.released
    assert not source.is_open()


def test_live_read_failure_is_temporary_and_file_failure_is_normal_eof(tmp_path: Path) -> None:
    live_capture = FakeCapture([])
    live = OpenCVCameraSource(
        StreamConfiguration.usb("live"),
        capture_factory=lambda *_args: live_capture,
        cv2_module=FakeCV2,
    )
    live.open()

    file_path = tmp_path / "synthetic.avi"
    file_path.write_bytes(b"synthetic container placeholder")
    file_capture = FakeCapture([])
    file_source = OpenCVFileStreamSource(
        StreamConfiguration.file("file", file_path),
        capture_factory=lambda *_args: file_capture,
        cv2_module=FakeCV2,
    )
    file_source.open()

    assert live.read().status is StreamReadStatus.TEMPORARY_UNAVAILABLE
    assert file_source.read().status is StreamReadStatus.END_OF_STREAM
    assert live.is_live
    assert not file_source.is_live


def test_file_source_timestamp_and_factory_type(tmp_path: Path) -> None:
    file_path = tmp_path / "synthetic.avi"
    file_path.write_bytes(b"placeholder")
    capture = FakeCapture([_frame()])
    configuration = StreamConfiguration.file("file", file_path)
    source = OpenCVFileStreamSource(
        configuration,
        capture_factory=lambda *_args: capture,
        cv2_module=FakeCV2,
    )
    source.open()
    result = source.read()

    assert result.frame is not None
    assert result.frame.source_timestamp_seconds == pytest.approx(0.1)
    assert isinstance(create_camera_source(configuration), OpenCVFileStreamSource)
    assert configuration.source_type is SourceType.FILE


def test_missing_file_error_never_contains_local_path(tmp_path: Path) -> None:
    missing = tmp_path / "private local camera file.avi"

    with pytest.raises(StreamOpenError) as captured:
        OpenCVFileStreamSource(StreamConfiguration.file("file", missing))

    assert str(missing) not in str(captured.value)


def test_warmup_frames_are_consumed_before_delivery() -> None:
    capture = FakeCapture([_frame((1, 1, 1)), _frame((5, 6, 7))])
    source = OpenCVCameraSource(
        StreamConfiguration.usb("camera", warmup_frames=1),
        capture_factory=lambda *_args: capture,
        cv2_module=FakeCV2,
    )

    source.open()
    result = source.read()

    assert result.frame is not None
    assert result.frame.payload.data[:3] == bytes((7, 6, 5))


def test_warmup_failure_releases_resource() -> None:
    capture = FakeCapture([])
    source = OpenCVCameraSource(
        StreamConfiguration.usb("camera", warmup_frames=1),
        capture_factory=lambda *_args: capture,
        cv2_module=FakeCV2,
    )

    with pytest.raises(StreamOpenError, match="warm-up"):
        source.open()

    assert capture.released
    assert not source.is_open()
