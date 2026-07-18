import inspect
from typing import get_type_hints

from hogflow.streaming.contracts import CameraSource
from hogflow.streaming.models import (
    StreamHealth,
    StreamIdentity,
    StreamReadResult,
    StreamStatistics,
)


def test_camera_source_contract_is_documented_and_small() -> None:
    assert inspect.isclass(CameraSource)
    assert CameraSource.__doc__ is not None
    public = {
        name
        for name, value in vars(CameraSource).items()
        if not name.startswith("_") and (callable(value) or isinstance(value, property))
    }

    assert public == {
        "close",
        "health",
        "identity",
        "is_live",
        "is_open",
        "open",
        "read",
        "statistics",
    }


def test_camera_source_contract_uses_only_stream_models() -> None:
    assert get_type_hints(CameraSource.identity.fget)["return"] is StreamIdentity
    assert get_type_hints(CameraSource.read)["return"] is StreamReadResult
    assert get_type_hints(CameraSource.health)["return"] is StreamHealth
    assert get_type_hints(CameraSource.statistics)["return"] is StreamStatistics
