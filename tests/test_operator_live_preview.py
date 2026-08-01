from __future__ import annotations

from dataclasses import dataclass, field

from _phase9_3_helpers import RecordingSource, finite_events, wait_for_status
from _phase9_helpers import LifecycleIdFactory, StepClock
from test_preview_channel import preview_frame

import hogflow.presentation.presenter as presenter_module
from hogflow.application import VideoSourceRequest
from hogflow.bootstrap import build_operator_runtime
from hogflow.camera import (
    CameraSnapshot,
    CameraStatus,
    CountingPipelineSnapshot,
    CountingPipelineStatus,
    PipelineFailureCategory,
    PreviewConfiguration,
    PreviewHealthState,
)
from hogflow.presentation import (
    ConfirmationRequest,
    OperatorPresenter,
    OperatorPreviewView,
    OperatorScreen,
    PreviewRenderPlan,
    TkOperatorView,
    screen_from_snapshot,
)
from hogflow.streaming import SourceType


@dataclass
class PreviewRecordingView:
    screens: list[OperatorScreen] = field(default_factory=list)
    plans: list[PreviewRenderPlan | None] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def render(self, screen: OperatorScreen) -> None:
        self.screens.append(screen)

    def render_preview(self, plan, _diagnostics) -> None:
        self.plans.append(plan)

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def confirm(self, _request: ConfirmationRequest) -> bool:
        return True

    def close(self) -> None:
        pass


def test_presenter_consumes_preview_only_through_application_boundary() -> None:
    runtime = build_operator_runtime(
        clock=StepClock(),
        lifecycle_id_factory=LifecycleIdFactory(),
    )
    view = PreviewRecordingView()
    presenter = OperatorPresenter(runtime.application, view)
    runtime.preview_channel.publish(preview_frame(3))

    screen = presenter.refresh()

    assert isinstance(view, OperatorPreviewView)
    assert len(view.plans) == 1
    assert view.plans[0] is not None
    assert view.plans[0].frame.frame_sequence == 3
    assert view.plans[0].display_width <= 640
    assert view.plans[0].display_height <= 270
    assert screen.camera_pipeline.preview_available
    assert runtime.application.preview_snapshot().frames_consumed == 1
    assert not runtime.application.preview_snapshot().frame_available


def test_preview_disabled_is_explicit_and_renders_no_frame() -> None:
    runtime = build_operator_runtime(
        preview_configuration=PreviewConfiguration(enabled=False),
    )
    view = PreviewRecordingView()
    runtime.preview_channel.publish(preview_frame())

    screen = OperatorPresenter(runtime.application, view).refresh()

    assert screen.camera_pipeline.preview_status == "Disabled"
    assert view.plans == [None]
    assert runtime.application.latest_preview_frame() is None


def test_render_failure_is_operator_visible_and_does_not_fail_pipeline() -> None:
    class FailingView(PreviewRecordingView):
        def render_preview(self, _plan, _diagnostics) -> None:
            raise RuntimeError("synthetic Tk rendering failure")

    runtime = build_operator_runtime()
    view = FailingView()
    runtime.preview_channel.publish(preview_frame())

    OperatorPresenter(runtime.application, view).refresh()

    assert view.errors == ["Live preview rendering stopped; counting continues."]
    assert runtime.application.preview_snapshot().health_state is PreviewHealthState.FAILED
    assert runtime.application.pipeline_snapshot().failure_message is None


def test_overlay_planning_failure_is_isolated_from_counting(
    monkeypatch,
) -> None:
    runtime = build_operator_runtime()
    view = PreviewRecordingView()
    runtime.preview_channel.publish(preview_frame())
    monkeypatch.setattr(
        presenter_module,
        "build_preview_render_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("overlay failed")),
    )

    OperatorPresenter(runtime.application, view).refresh()

    assert view.errors == ["Live preview rendering stopped; counting continues."]
    assert runtime.application.preview_snapshot().health_state is PreviewHealthState.FAILED
    assert runtime.application.pipeline_snapshot().failure_message is None


def test_operator_screen_exposes_bounded_live_diagnostics() -> None:
    runtime = build_operator_runtime()
    runtime.preview_channel.publish(preview_frame())

    screen = OperatorPresenter(runtime.application, PreviewRecordingView()).refresh()
    diagnostics = screen.camera_pipeline

    assert diagnostics.effective_fps == 0.0
    assert diagnostics.temporary_failures == 0
    assert diagnostics.stale_evidence_rejected == 0
    assert diagnostics.recovery_attempts == 0
    assert not diagnostics.worker_alive
    assert diagnostics.preview_status == "Available"


def test_operator_screen_distinguishes_exhausted_source() -> None:
    runtime = build_operator_runtime()
    pipeline = CountingPipelineSnapshot(
        status=CountingPipelineStatus.STOPPED,
        camera=CameraSnapshot(
            source_id="shared_operator_lane",
            source_type=SourceType.FILE,
            display_name="Local video",
            status=CameraStatus.ENDED,
            last_frame_index=4,
            frames_acquired=5,
            last_successful_frame_at=None,
            source_exhausted=True,
            failure_category=PipelineFailureCategory.NONE,
            failure_message=None,
        ),
        frames_processed=5,
        temporary_processing_failures=0,
        stale_results_rejected=0,
        active_crossing_lifecycle_id=None,
        worker_alive=False,
        failure_category=PipelineFailureCategory.NONE,
        failure_message=None,
        started_at=None,
        stopped_at=None,
    )

    screen = screen_from_snapshot(runtime.application.snapshot(), pipeline=pipeline)

    assert screen.camera_pipeline.camera_status == "Exhausted"


def test_preview_starts_only_with_pipeline_and_closes_on_application_shutdown() -> None:
    source = RecordingSource(events=finite_events(2))
    runtime = build_operator_runtime(source_factory=lambda _configuration: source)
    runtime.application.configure_video_source(VideoSourceRequest.camera(0))

    assert runtime.application.preview_snapshot().frames_published == 0
    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert runtime.application.preview_snapshot().frames_published == 2
    assert runtime.application.latest_preview_frame() is not None
    runtime.application.shutdown()
    assert runtime.application.preview_snapshot().health_state is PreviewHealthState.CLOSED


class ScheduledRoot:
    def __init__(self) -> None:
        self.callbacks = {}
        self.after_calls = 0
        self.cancelled = []

    def after(self, _milliseconds: int, callback):
        self.after_calls += 1
        identifier = f"after-{self.after_calls}"
        self.callbacks[identifier] = callback
        return identifier

    def after_cancel(self, identifier) -> None:
        self.cancelled.append(identifier)


class RefreshingPresenter:
    def __init__(self) -> None:
        self.refreshes = 0

    def refresh(self, _dock) -> None:
        self.refreshes += 1


class Value:
    def get(self) -> str:
        return "dock_1"


def test_tk_live_refresh_keeps_exactly_one_scheduled_callback() -> None:
    view = object.__new__(TkOperatorView)
    root = ScheduledRoot()
    presenter = RefreshingPresenter()
    view._root = root  # type: ignore[attr-defined]
    view._closed = False  # type: ignore[attr-defined]
    view._live_refresh_after_id = None  # type: ignore[attr-defined]
    view._presenter = presenter  # type: ignore[attr-defined]
    view._dock_value = Value()  # type: ignore[attr-defined]

    view._schedule_live_refresh()  # type: ignore[attr-defined]
    view._schedule_live_refresh()  # type: ignore[attr-defined]
    first = view._live_refresh_after_id  # type: ignore[attr-defined]
    root.callbacks[first]()

    assert presenter.refreshes == 1
    assert root.after_calls == 2
    assert len(root.callbacks) == 2
    assert view._live_refresh_after_id != first  # type: ignore[attr-defined]
