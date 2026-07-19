"""Local stream-first CLI for Phase 5.2 live detector integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from hogflow.adapters.camera_source_factory import create_camera_source
from hogflow.adapters.opencv_detection_preview import OpenCVDetectionPreview
from hogflow.adapters.ultralytics_live_detector import UltralyticsLiveDetector
from hogflow.core import HogFlowError, configure_logging
from hogflow.detection import (
    EmptyDetector,
    LiveDetectionRunSummary,
    LiveDetectionStats,
    LiveInferenceConfiguration,
)
from hogflow.pipeline import LiveDetectionPipeline
from hogflow.streaming import (
    BoundedFrameBuffer,
    BufferConfiguration,
    LiveStreamRunner,
    OverflowPolicy,
    ReconnectPolicy,
    SourceType,
    StreamConfiguration,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit local source, detector, scheduling, and preview CLI."""

    parser = argparse.ArgumentParser(
        description=(
            "Run bounded-latency live detection without tracking, counting, recording, or upload."
        )
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
    parser.add_argument("--warmup-frames", type=int, default=0)
    parser.add_argument("--read-timeout", type=float, default=5.0)
    parser.add_argument("--buffer-capacity", type=int, default=4)
    parser.add_argument(
        "--overflow-policy",
        choices=tuple(item.value for item in OverflowPolicy),
        default=OverflowPolicy.DROP_OLDEST.value,
    )
    parser.add_argument(
        "--reconnect",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--maximum-reconnect-attempts", type=int, default=10)
    parser.add_argument("--synthetic-frames", type=int, default=100)

    parser.add_argument("--detector", choices=("empty", "yolo"), default="empty")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--model-provenance", type=Path)
    parser.add_argument("--confidence", type=_probability_argument, default=0.4)
    parser.add_argument("--iou-threshold", type=_probability_argument, default=0.5)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--permitted-class-ids", type=_class_ids)

    parser.add_argument("--inference-every", type=int, default=1)
    parser.add_argument("--target-inference-fps", type=float)
    parser.add_argument("--maximum-frame-age-ms", type=float)
    parser.add_argument("--maximum-frames", type=int)
    parser.add_argument("--maximum-duration", type=float)
    parser.add_argument("--statistics-interval", type=float, default=2.0)
    parser.add_argument("--preview", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Compose one local camera-to-detector run and print sanitized JSON."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        stream_configuration = _stream_configuration(arguments)
        inference_configuration = LiveInferenceConfiguration(
            inference_every_n_frames=arguments.inference_every,
            target_inference_fps=arguments.target_inference_fps,
            maximum_frame_age_ms=arguments.maximum_frame_age_ms,
        )
        detector = _detector(arguments)
        source = create_camera_source(
            stream_configuration,
            synthetic_frame_count=arguments.synthetic_frames,
        )
        stream_runner = LiveStreamRunner(
            source,
            BoundedFrameBuffer(
                BufferConfiguration(
                    capacity=arguments.buffer_capacity,
                    overflow_policy=OverflowPolicy(arguments.overflow_policy),
                )
            ),
            stream_configuration,
            ReconnectPolicy(
                enabled=arguments.reconnect,
                maximum_attempts=arguments.maximum_reconnect_attempts,
            ),
        )
        preview = OpenCVDetectionPreview() if arguments.preview else None
        pipeline = LiveDetectionPipeline(
            stream_runner,
            detector,
            inference_configuration,
            preview=preview,
            statistics_callback=lambda statistics: print(
                json.dumps(_statistics_payload(statistics, final=False), sort_keys=True),
                flush=True,
            ),
        )
        summary = pipeline.run(
            maximum_frames=arguments.maximum_frames,
            maximum_duration_seconds=arguments.maximum_duration,
            statistics_interval_seconds=arguments.statistics_interval,
        )
        print(json.dumps(_summary_payload(summary), sort_keys=True), flush=True)
    except (HogFlowError, ValueError) as exc:
        parser.error(str(exc))
    return 0


def _stream_configuration(arguments: argparse.Namespace) -> StreamConfiguration:
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


def _detector(arguments: argparse.Namespace):
    if arguments.detector == "empty":
        return EmptyDetector()
    if arguments.model_path is None:
        raise ValueError("YOLO detector requires an explicit existing --model-path.")
    return UltralyticsLiveDetector(
        arguments.model_path,
        provenance_path=arguments.model_provenance,
        confidence_threshold=arguments.confidence,
        iou_threshold=arguments.iou_threshold,
        image_size=arguments.image_size,
        device=arguments.device,
        permitted_class_ids=arguments.permitted_class_ids,
    )


def _class_ids(value: str) -> tuple[int, ...]:
    try:
        values = tuple(sorted({int(item.strip()) for item in value.split(",")}))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Class IDs must be comma-separated integers.") from exc
    if not values or any(item < 0 for item in values):
        raise argparse.ArgumentTypeError("Class IDs must be non-negative integers.")
    return values


def _probability_argument(value: str) -> float:
    try:
        probability = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Probability must be numeric.") from exc
    if not 0 < probability <= 1:
        raise argparse.ArgumentTypeError("Probability must be greater than 0 and at most 1.")
    return probability


def _statistics_payload(statistics: LiveDetectionStats, *, final: bool) -> dict[str, object]:
    return {
        "average_inference_ms": round(statistics.average_inference_ms, 3),
        "camera_fps": statistics.camera_fps,
        "effective_inference_fps": round(statistics.effective_inference_fps, 3),
        "final": final,
        "frames_acquired": statistics.frames_acquired,
        "frames_inferred": statistics.frames_inferred,
        "frames_skipped": statistics.frames_skipped,
        "frames_submitted": statistics.frames_submitted,
        "inference_failures": statistics.inference_failures,
        "latest_frame_age_ms": statistics.latest_frame_age_ms,
        "p95_inference_ms": round(statistics.p95_inference_ms, 3),
        "source_frames_dropped": statistics.source_frames_dropped,
        "total_detections": statistics.total_detections,
    }


def _summary_payload(summary: LiveDetectionRunSummary) -> dict[str, object]:
    payload = _statistics_payload(summary.statistics, final=True)
    payload.update(
        {
            "camera_released": summary.camera_released,
            "detector_closed": summary.detector_closed,
            "detector_identity": summary.detector.model_id,
            "final_camera_health": summary.final_camera_health.value,
            "model_artifact": summary.detector.artifact_filename,
            "model_fingerprint": summary.detector.artifact_fingerprint,
            "model_framework": summary.detector.framework,
            "model_version": summary.detector.model_version,
            "pig_model_provenance_complete": (summary.detector.pig_detection_provenance_complete),
            "shutdown_reason": summary.shutdown_reason.value,
            "source": summary.source_type.value,
            "source_id": summary.source_id,
            "source_identity": summary.source_display_name,
        }
    )
    return payload


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
