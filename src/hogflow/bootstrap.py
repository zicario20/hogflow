"""Executable Phase 9 desktop composition with optional shared camera source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import uuid4

from hogflow.adapters.camera_source_factory import create_camera_source
from hogflow.application import (
    Clock,
    CrossingLifecycleIdFactory,
    DockId,
    OperatorApplicationService,
    SerializedMultiDockRuntimeAccess,
    VideoSourceRequest,
)
from hogflow.camera import (
    CameraRecoveryConfiguration,
    CountingFrameProcessorFactory,
    CountingPipelineController,
    DetectorTrackingCrossingProcessor,
    LatestPreviewFrameChannel,
    PreviewConfiguration,
    VideoSourceFactory,
)
from hogflow.counting import (
    LifecycleDirectionalCounter,
    LiveCountingConfiguration,
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
    VirtualLineCrossingDetector,
)
from hogflow.detection import EmptyDetector
from hogflow.presentation import (
    OperatorDesktopView,
    OperatorPresenter,
    create_tk_operator_view,
)
from hogflow.sessions import MultiDockRuntimeCoordinator, SharedCountingLane
from hogflow.tracking import EmptyTracker

OPERATOR_LANE_SOURCE_ID = "shared_operator_lane"
DEFAULT_CAMERA_CROSSING_CONFIGURATION = LiveCrossingConfiguration(
    enabled=True,
    line=NormalizedLine(
        start=NormalizedPoint(0.5, 0.0),
        end=NormalizedPoint(0.5, 1.0),
    ),
)
DEFAULT_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT = (
    DEFAULT_CAMERA_CROSSING_CONFIGURATION.fingerprint
)
# Backward-compatible Phase 9.2 import alias. New composition uses the explicit
# camera configuration name above.
NO_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT = DEFAULT_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT

ViewFactory = Callable[[], OperatorDesktopView]


class LocalCrossingLifecycleIdFactory:
    """Create opaque local lifecycle IDs for the in-memory executable."""

    def __call__(self, _dock_id: DockId, _session_id: str) -> str:
        return f"operator-{uuid4().hex}"


@dataclass(frozen=True, slots=True)
class OperatorRuntimeComposition:
    """Application resources created once by the executable composition root."""

    counter: LifecycleDirectionalCounter
    counting_lane: SharedCountingLane
    coordinator: MultiDockRuntimeCoordinator
    runtime_access: SerializedMultiDockRuntimeAccess
    counting_pipeline: CountingPipelineController
    preview_channel: LatestPreviewFrameChannel
    application: OperatorApplicationService


@dataclass(frozen=True, slots=True)
class OperatorDesktopComposition:
    """Fully wired one-window Operator MVP composition."""

    runtime: OperatorRuntimeComposition
    presenter: OperatorPresenter
    view: OperatorDesktopView

    def run(self) -> None:
        """Start the local desktop and its UI-thread visual refresh."""

        try:
            self.view.start()
        except BaseException:
            self.runtime.application.shutdown()
            raise


def _default_processor_factory(
    preview_channel: LatestPreviewFrameChannel,
) -> DetectorTrackingCrossingProcessor:
    """Build a framework-free no-detection processor for safe local composition."""

    return DetectorTrackingCrossingProcessor(
        EmptyDetector(),
        EmptyTracker(),
        lambda lifecycle_id: VirtualLineCrossingDetector(
            DEFAULT_CAMERA_CROSSING_CONFIGURATION,
            lifecycle_id_factory=lambda _generation: lifecycle_id,
        ),
        preview_publisher=preview_channel,
        preview_configuration=DEFAULT_CAMERA_CROSSING_CONFIGURATION,
    )


def build_operator_runtime(
    *,
    clock: Clock | None = None,
    lifecycle_id_factory: CrossingLifecycleIdFactory | None = None,
    source_factory: VideoSourceFactory | None = None,
    processor_factory: CountingFrameProcessorFactory | None = None,
    preview_configuration: PreviewConfiguration = PreviewConfiguration(),
    recovery_configuration: CameraRecoveryConfiguration = CameraRecoveryConfiguration(),
) -> OperatorRuntimeComposition:
    """Build one shared lane, source controller, and operator application."""

    configuration = LiveCountingConfiguration(
        enabled=True,
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        crossing_configuration_fingerprint=DEFAULT_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT,
    )
    counter = LifecycleDirectionalCounter(configuration)
    lane = SharedCountingLane(counter, source_id=OPERATOR_LANE_SOURCE_ID)
    coordinator = MultiDockRuntimeCoordinator(lane, clock=clock)
    runtime_access = SerializedMultiDockRuntimeAccess(coordinator)
    preview_channel = LatestPreviewFrameChannel(preview_configuration)
    counting_pipeline = CountingPipelineController(
        runtime_access,
        source_factory or create_camera_source,
        processor_factory or (lambda: _default_processor_factory(preview_channel)),
        clock=clock,
        recovery_configuration=recovery_configuration,
        preview_channel=preview_channel,
    )
    application = OperatorApplicationService(
        coordinator,
        crossing_lifecycle_id_factory=(lifecycle_id_factory or LocalCrossingLifecycleIdFactory()),
        clock=clock,
        runtime_access=runtime_access,
        counting_pipeline=counting_pipeline,
    )
    return OperatorRuntimeComposition(
        counter=counter,
        counting_lane=lane,
        coordinator=coordinator,
        runtime_access=runtime_access,
        counting_pipeline=counting_pipeline,
        preview_channel=preview_channel,
        application=application,
    )


def compose_operator_desktop(
    *,
    view_factory: ViewFactory | None = None,
    clock: Callable[[], datetime] | None = None,
    lifecycle_id_factory: CrossingLifecycleIdFactory | None = None,
    video_source: VideoSourceRequest | None = None,
    source_factory: VideoSourceFactory | None = None,
    processor_factory: CountingFrameProcessorFactory | None = None,
    preview_configuration: PreviewConfiguration = PreviewConfiguration(),
    recovery_configuration: CameraRecoveryConfiguration = CameraRecoveryConfiguration(),
) -> OperatorDesktopComposition:
    """Create and wire lane → coordinator → application → presenter → view."""

    runtime = build_operator_runtime(
        clock=clock,
        lifecycle_id_factory=lifecycle_id_factory,
        source_factory=source_factory,
        processor_factory=processor_factory,
        preview_configuration=preview_configuration,
        recovery_configuration=recovery_configuration,
    )
    try:
        if video_source is not None:
            runtime.application.configure_video_source(video_source)
        view = (view_factory or create_tk_operator_view)()
        presenter = OperatorPresenter(runtime.application, view)
        view.bind_presenter(presenter)
    except Exception:
        runtime.application.shutdown()
        raise
    return OperatorDesktopComposition(
        runtime=runtime,
        presenter=presenter,
        view=view,
    )


__all__ = [
    "DEFAULT_CAMERA_CROSSING_CONFIGURATION",
    "DEFAULT_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT",
    "LocalCrossingLifecycleIdFactory",
    "NO_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT",
    "OPERATOR_LANE_SOURCE_ID",
    "OperatorDesktopComposition",
    "OperatorRuntimeComposition",
    "build_operator_runtime",
    "compose_operator_desktop",
]
