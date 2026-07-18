"""Framework-neutral continuous camera acquisition foundation."""

from hogflow.streaming.buffering import BoundedFrameBuffer
from hogflow.streaming.configuration import (
    BufferConfiguration,
    ReconnectPolicy,
    StreamConfiguration,
)
from hogflow.streaming.contracts import CameraSource
from hogflow.streaming.lifecycle import LiveStreamRunner
from hogflow.streaming.models import (
    BufferReadResult,
    BufferReadStatus,
    BufferStatistics,
    FrameDimensions,
    FramePacket,
    FramePayload,
    FrameTimestamp,
    OverflowPolicy,
    PixelFormat,
    SourceFrame,
    SourceType,
    StreamErrorCategory,
    StreamHealth,
    StreamHealthState,
    StreamIdentity,
    StreamReadResult,
    StreamReadStatus,
    StreamStatistics,
)
from hogflow.streaming.synthetic import (
    SyntheticCameraSource,
    SyntheticEvent,
    SyntheticEventType,
    synthetic_frame_events,
)

__all__ = [
    "BoundedFrameBuffer",
    "BufferConfiguration",
    "BufferReadResult",
    "BufferReadStatus",
    "BufferStatistics",
    "CameraSource",
    "FrameDimensions",
    "FramePacket",
    "FramePayload",
    "FrameTimestamp",
    "LiveStreamRunner",
    "OverflowPolicy",
    "PixelFormat",
    "ReconnectPolicy",
    "SourceFrame",
    "SourceType",
    "StreamConfiguration",
    "StreamErrorCategory",
    "StreamHealth",
    "StreamHealthState",
    "StreamIdentity",
    "StreamReadResult",
    "StreamReadStatus",
    "StreamStatistics",
    "SyntheticCameraSource",
    "SyntheticEvent",
    "SyntheticEventType",
    "synthetic_frame_events",
]
