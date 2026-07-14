import inspect
from typing import get_type_hints

from hogflow.models import Frame
from hogflow.video import VideoSource
from hogflow.video import contracts as video_contracts


def test_exactly_one_video_source_protocol_is_public() -> None:
    public_classes = [
        value
        for name, value in vars(video_contracts).items()
        if inspect.isclass(value) and value.__module__ == video_contracts.__name__
    ]

    assert public_classes == [VideoSource]
    assert getattr(VideoSource, "_is_protocol", False) is True
    assert video_contracts.__all__ == ["VideoSource"]


def test_video_source_protocol_uses_shared_frame_model() -> None:
    assert get_type_hints(VideoSource.read) == {"return": Frame | None}
    assert get_type_hints(VideoSource.close) == {"return": type(None)}


def test_video_source_public_api_is_documented_and_typed() -> None:
    assert inspect.getdoc(VideoSource)
    assert inspect.getdoc(VideoSource.read)
    assert inspect.getdoc(VideoSource.close)
