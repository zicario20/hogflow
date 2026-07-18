from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from hogflow.core import ConfigurationError, InputDataError
from hogflow.streaming.configuration import (
    BufferConfiguration,
    ReconnectPolicy,
    StreamConfiguration,
)
from hogflow.streaming.models import (
    FrameDimensions,
    FramePacket,
    FramePayload,
    FrameTimestamp,
    OverflowPolicy,
    SourceType,
)


def test_stream_configuration_is_immutable_and_source_type_is_explicit() -> None:
    configuration = StreamConfiguration.usb("loading-bay", device_index=2)

    assert configuration.source_type is SourceType.USB
    assert configuration.device_index == 2
    with pytest.raises(FrozenInstanceError):
        configuration.device_index = 3  # type: ignore[misc]


def test_stream_configuration_validates_requested_settings() -> None:
    with pytest.raises(ConfigurationError, match="Requested width"):
        StreamConfiguration.usb("camera", requested_width=0)
    with pytest.raises(ConfigurationError, match="Requested FPS"):
        StreamConfiguration.usb("camera", requested_fps=float("nan"))
    with pytest.raises(ConfigurationError, match="backend"):
        StreamConfiguration.usb("camera", backend_preference="unknown")


def test_reconnect_policy_is_deterministic_and_capped() -> None:
    policy = ReconnectPolicy(
        initial_delay_seconds=0.5,
        maximum_delay_seconds=2.0,
        backoff_multiplier=2.0,
        maximum_attempts=3,
    )

    assert [policy.delay_for_attempt(index) for index in range(1, 5)] == [0.5, 1.0, 2.0, 2.0]
    assert policy.permits(3)
    assert not policy.permits(4)


def test_unlimited_reconnect_policy_and_disabled_policy() -> None:
    assert ReconnectPolicy(maximum_attempts=None).permits(10_000)
    assert not ReconnectPolicy(enabled=False).permits(1)


def test_buffer_configuration_defaults_to_drop_oldest() -> None:
    configuration = BufferConfiguration()

    assert configuration.capacity == 4
    assert configuration.overflow_policy is OverflowPolicy.DROP_OLDEST


def test_frame_packet_owns_immutable_rgb_payload() -> None:
    dimensions = FrameDimensions(2, 1, 3)
    payload = FramePayload(bytes((1, 2, 3, 4, 5, 6)))
    packet = FramePacket(
        stream=StreamConfiguration.synthetic("camera").identity,
        sequence_number=0,
        timestamp=FrameTimestamp(datetime.now(timezone.utc), 1.0, 0.0),
        dimensions=dimensions,
        payload=payload,
    )

    assert packet.payload.data == bytes((1, 2, 3, 4, 5, 6))
    with pytest.raises(FrozenInstanceError):
        packet.sequence_number = 1  # type: ignore[misc]


def test_frame_payload_length_must_match_dimensions() -> None:
    with pytest.raises(InputDataError, match="exactly 6 bytes"):
        FramePacket(
            stream=StreamConfiguration.synthetic("camera").identity,
            sequence_number=0,
            timestamp=FrameTimestamp(datetime.now(timezone.utc), 1.0),
            dimensions=FrameDimensions(2, 1, 3),
            payload=FramePayload(b"short"),
        )


def test_wall_clock_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(InputDataError, match="timezone-aware"):
        FrameTimestamp(datetime.now(), 1.0)
