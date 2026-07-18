"""Headless local diagnostic CLI for the Phase 5.1 stream foundation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic
from typing import Sequence

from hogflow.core import HogFlowError, configure_logging
from hogflow.streaming import (
    BoundedFrameBuffer,
    BufferConfiguration,
    BufferReadStatus,
    LiveStreamRunner,
    OverflowPolicy,
    ReconnectPolicy,
    SourceType,
    StreamConfiguration,
)

from .camera_source_factory import create_camera_source


def build_parser() -> argparse.ArgumentParser:
    """Create a source-explicit, headless diagnostic parser."""

    parser = argparse.ArgumentParser(
        description="Inspect a local live/development stream without saving frame data."
    )
    parser.add_argument(
        "--source-type",
        choices=tuple(item.value for item in SourceType),
        required=True,
    )
    parser.add_argument("--stream-id", default="camera-1")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--rtsp-url")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument(
        "--backend",
        choices=("any", "dshow", "ffmpeg", "gstreamer", "msmf", "v4l2"),
        default="any",
    )
    parser.add_argument("--buffer-size", type=int, default=4)
    parser.add_argument(
        "--overflow-policy",
        choices=tuple(item.value for item in OverflowPolicy),
        default=OverflowPolicy.DROP_OLDEST.value,
    )
    parser.add_argument("--warmup-frames", type=int, default=0)
    parser.add_argument("--read-timeout", type=float, default=5.0)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument(
        "--reconnect",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--maximum-reconnect-attempts", type=int, default=10)
    parser.add_argument("--health-interval", type=float, default=2.0)
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Explicitly confirm headless operation; Phase 5.1 never opens a preview.",
    )
    return parser


def _configuration(arguments: argparse.Namespace) -> StreamConfiguration:
    settings = {
        "requested_width": arguments.width,
        "requested_height": arguments.height,
        "requested_fps": arguments.fps,
        "backend_preference": arguments.backend,
        "read_timeout_seconds": arguments.read_timeout,
        "warmup_frames": arguments.warmup_frames,
    }
    source_type = SourceType(arguments.source_type)
    if source_type is SourceType.USB:
        return StreamConfiguration.usb(
            arguments.stream_id,
            device_index=arguments.device_index,
            **settings,
        )
    if source_type is SourceType.RTSP:
        if not arguments.rtsp_url:
            raise ValueError("RTSP source requires --rtsp-url supplied at runtime.")
        return StreamConfiguration.rtsp(arguments.stream_id, arguments.rtsp_url, **settings)
    if source_type is SourceType.FILE:
        if arguments.file is None:
            raise ValueError("File source requires --file for local development input.")
        return StreamConfiguration.file(arguments.stream_id, arguments.file, **settings)
    return StreamConfiguration.synthetic(arguments.stream_id, **settings)


def main(argv: Sequence[str] | None = None) -> int:
    """Run a bounded diagnostic and print only sanitized aggregate information."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.duration <= 0:
        parser.error("--duration must be positive.")
    if arguments.max_frames is not None and arguments.max_frames <= 0:
        parser.error("--max-frames must be positive when provided.")
    if arguments.health_interval <= 0:
        parser.error("--health-interval must be positive.")
    try:
        configuration = _configuration(arguments)
        buffer = BoundedFrameBuffer(
            BufferConfiguration(
                capacity=arguments.buffer_size,
                overflow_policy=OverflowPolicy(arguments.overflow_policy),
            )
        )
        synthetic_count = arguments.max_frames or 20
        source = create_camera_source(
            configuration,
            synthetic_frame_count=synthetic_count,
        )
        runner = LiveStreamRunner(
            source,
            buffer,
            configuration,
            ReconnectPolicy(
                enabled=arguments.reconnect,
                maximum_attempts=arguments.maximum_reconnect_attempts,
            ),
        )
        started = monotonic()
        next_health = started + arguments.health_interval
        delivered = 0
        runner.start()
        try:
            while monotonic() - started < arguments.duration:
                result = buffer.get(timeout_seconds=0.2)
                if result.status is BufferReadStatus.FRAME:
                    delivered += 1
                    if arguments.max_frames is not None and delivered >= arguments.max_frames:
                        break
                elif result.status is BufferReadStatus.CLOSED:
                    break
                if monotonic() >= next_health:
                    _print_snapshot(runner, final=False)
                    next_health = monotonic() + arguments.health_interval
        except KeyboardInterrupt:
            pass
        finally:
            runner.stop()
            runner.join(5.0, raise_on_failure=True)
        _print_snapshot(runner, final=True)
    except (HogFlowError, ValueError) as exc:
        parser.error(str(exc))
    return 0


def _print_snapshot(runner: LiveStreamRunner, *, final: bool) -> None:
    health = runner.health()
    statistics = runner.statistics()
    dimensions = health.observed_dimensions
    payload = {
        "buffer_depth": statistics.current_buffer_depth,
        "final": final,
        "frames_acquired": statistics.frames_acquired,
        "frames_delivered": statistics.frames_delivered,
        "frames_dropped": statistics.frames_dropped,
        "health": health.state.value,
        "observed_fps": statistics.observed_fps,
        "observed_resolution": (
            None if dimensions is None else f"{dimensions.width}x{dimensions.height}"
        ),
        "reconnect_count": statistics.reconnect_count,
        "runtime_seconds": round(statistics.runtime_seconds, 3),
        "source_id": health.identity.display_name,
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
