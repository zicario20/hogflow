"""Command-line entry point for the local Operator MVP desktop."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from hogflow.application import OperatorInputError, VideoSourceRequest
from hogflow.bootstrap import compose_operator_desktop
from hogflow.camera import PreviewConfiguration
from hogflow.core import HogFlowError
from hogflow.detection import (
    DetectorBackend,
    DetectorConfigurationError,
    PigDetectorConfiguration,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded Phase 9.4 executable parser."""

    parser = argparse.ArgumentParser(
        prog="hogflow",
        description="Run the local HogFlow Operator MVP with an optional shared source.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=("run",),
        help="Run the local Operator MVP desktop (default: run).",
    )
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        "--camera",
        type=int,
        metavar="INDEX",
        help="Configure one local camera index without opening it during startup.",
    )
    sources.add_argument(
        "--video",
        metavar="FILE",
        help="Configure one existing local video file for deterministic validation.",
    )
    parser.add_argument(
        "--disable-preview",
        action="store_true",
        help="Disable the local latest-frame operator preview.",
    )
    parser.add_argument(
        "--real-time-video",
        action="store_true",
        help="Pace a local video near its embedded timestamps; cameras are unchanged.",
    )
    parser.add_argument(
        "--detector",
        choices=tuple(item.value for item in DetectorBackend),
        default=DetectorBackend.EMPTY.value,
        help=(
            "Select explicit empty mode or one supported local model artifact; "
            "no model is downloaded and no pig accuracy is implied."
        ),
    )
    parser.add_argument("--model-path", type=Path, help="Existing local detector artifact.")
    parser.add_argument(
        "--model-provenance",
        type=Path,
        help="Optional local JSON provenance for the configured artifact.",
    )
    parser.add_argument("--target-class-name", default="pig")
    parser.add_argument("--target-class-id", type=int, action="append")
    parser.add_argument("--confidence-threshold", type=float, default=0.4)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--inference-size", type=int, default=640)
    parser.add_argument("--device", default="auto", metavar="auto|cpu|cuda[:INDEX]")
    parser.add_argument("--max-detections", type=int, default=300)
    parser.add_argument("--half-precision", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Compose and run the local desktop without opening resources on import/help."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        detector_configuration = _detector_configuration(arguments)
        source = None
        if arguments.camera is not None:
            source = VideoSourceRequest.camera(arguments.camera)
        elif arguments.video is not None:
            source = VideoSourceRequest.video_file(arguments.video)
        if arguments.real_time_video and arguments.video is None:
            raise OperatorInputError("--real-time-video requires an explicit --video source.")
        settings = {}
        if source is not None:
            settings["video_source"] = source
        if arguments.disable_preview:
            settings["preview_configuration"] = PreviewConfiguration(enabled=False)
        if detector_configuration.backend is not DetectorBackend.EMPTY:
            settings["detector_configuration"] = detector_configuration
        if arguments.real_time_video:
            settings["real_time_file_playback"] = True
        composition = compose_operator_desktop(**settings)
        composition.run()
    except (HogFlowError, OperatorInputError) as exc:
        parser.error(str(exc))
    return 0


def _detector_configuration(arguments: argparse.Namespace) -> PigDetectorConfiguration:
    backend = DetectorBackend(arguments.detector)
    target_ids = arguments.target_class_id
    if target_ids is not None and len(set(target_ids)) != len(target_ids):
        raise DetectorConfigurationError("Detector target class IDs must not be duplicated.")
    normalized_ids = None if target_ids is None else tuple(sorted(target_ids))
    if backend is DetectorBackend.EMPTY:
        non_default_execution_setting = any(
            (
                arguments.model_path is not None,
                arguments.model_provenance is not None,
                normalized_ids is not None,
                arguments.target_class_name != "pig",
                arguments.confidence_threshold != 0.4,
                arguments.iou_threshold != 0.5,
                arguments.inference_size != 640,
                arguments.device != "auto",
                arguments.max_detections != 300,
                arguments.half_precision,
            )
        )
        if non_default_execution_setting:
            raise DetectorConfigurationError(
                "Detector execution options require a non-empty --detector."
            )
        return PigDetectorConfiguration.empty()
    if arguments.model_path is None:
        raise DetectorConfigurationError(
            "Configured local detector requires an explicit existing --model-path."
        )
    return PigDetectorConfiguration.local_model(
        arguments.model_path,
        provenance_path=arguments.model_provenance,
        target_class_name=arguments.target_class_name,
        target_class_ids=normalized_ids,
        confidence_threshold=arguments.confidence_threshold,
        iou_threshold=arguments.iou_threshold,
        inference_image_size=arguments.inference_size,
        device=arguments.device,
        maximum_detections=arguments.max_detections,
        half_precision=arguments.half_precision,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
