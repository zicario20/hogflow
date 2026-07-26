from __future__ import annotations

import pytest
from _phase9_3_helpers import BlockingSource, ScriptedCrossingProcessor

import hogflow.__main__ as operator_main
from hogflow.application import DockId, OperatorInputError, VideoSourceRequest
from hogflow.bootstrap import build_operator_runtime
from hogflow.camera import CameraStatus, CountingPipelineStatus
from hogflow.presentation import (
    ConfirmationRequest,
    OperatorAction,
    OperatorPresenter,
    OperatorScreen,
    OperatorView,
    parse_video_source_form,
)


class RecordingView:
    def __init__(self) -> None:
        self.screens: list[OperatorScreen] = []
        self.errors: list[str] = []

    def render(self, screen: OperatorScreen) -> None:
        self.screens.append(screen)

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def confirm(self, _request: ConfirmationRequest) -> bool:
        return True

    def close(self) -> None:
        pass


def camera_runtime(source: BlockingSource):
    return build_operator_runtime(
        source_factory=lambda _configuration: source,
        processor_factory=ScriptedCrossingProcessor,
    )


def test_unconfigured_camera_panel_and_button_rules_are_snapshot_driven() -> None:
    runtime = camera_runtime(BlockingSource())
    view = RecordingView()
    presenter = OperatorPresenter(runtime.application, view)

    screen = presenter.refresh()

    assert isinstance(view, OperatorView)
    assert screen.camera_pipeline.source == "Not configured"
    assert screen.camera_pipeline.camera_status == "Not Configured"
    assert screen.camera_pipeline.pipeline_status == "Stopped"
    assert screen.actions.is_enabled(OperatorAction.CONFIGURE_SOURCE)
    assert not screen.actions.is_enabled(OperatorAction.START_PIPELINE)
    assert not screen.actions.is_enabled(OperatorAction.STOP_PIPELINE)


def test_configured_and_running_pipeline_controls_follow_pipeline_snapshot() -> None:
    source = BlockingSource()
    runtime = camera_runtime(source)
    view = RecordingView()
    presenter = OperatorPresenter(runtime.application, view)

    configured = presenter.configure_video_source(VideoSourceRequest.camera(0))
    running = presenter.start_counting_pipeline()
    assert source.read_entered.wait(1)
    running = presenter.refresh(DockId.DOCK_1)

    assert configured.camera_pipeline.camera_status == "Closed"
    assert configured.actions.start_pipeline
    assert running.camera_pipeline.camera_status == "Running"
    assert running.camera_pipeline.pipeline_status == "Running"
    assert not running.actions.start_pipeline
    assert running.actions.stop_pipeline

    stopped = presenter.stop_counting_pipeline()
    assert stopped.camera_pipeline.camera_status == "Closed"
    assert stopped.camera_pipeline.pipeline_status == "Stopped"
    assert stopped.actions.start_pipeline
    assert not stopped.actions.stop_pipeline


def test_pipeline_metrics_and_errors_render_from_immutable_snapshots() -> None:
    runtime = camera_runtime(BlockingSource())
    screen = OperatorPresenter(runtime.application, RecordingView()).refresh()

    assert screen.camera_pipeline.frames_acquired == 0
    assert screen.camera_pipeline.frames_processed == 0
    assert screen.camera_pipeline.last_error
    assert screen.camera_pipeline.active_crossing_lifecycle
    assert not hasattr(screen, "__dict__")


def test_video_source_form_validates_before_application_call(tmp_path) -> None:
    video = tmp_path / "fixture.mp4"
    video.write_bytes(b"synthetic")

    assert parse_video_source_form("camera", "0") == VideoSourceRequest.camera(0)
    assert parse_video_source_form("video", str(video)).kind.value == "video_file"
    with pytest.raises(OperatorInputError, match="non-negative"):
        parse_video_source_form("camera", "-1")
    with pytest.raises(OperatorInputError, match="existing"):
        parse_video_source_form("video", str(tmp_path / "missing.mp4"))


def test_cli_rejects_conflicting_camera_and_video_without_composing(monkeypatch) -> None:
    monkeypatch.setattr(
        operator_main,
        "compose_operator_desktop",
        lambda **_settings: pytest.fail("Conflicting CLI options must fail before composition."),
    )

    with pytest.raises(SystemExit) as error:
        operator_main.main(["run", "--camera", "0", "--video", "fixture.mp4"])

    assert error.value.code == 2


def test_cli_camera_configuration_reaches_composition_without_opening_source(monkeypatch) -> None:
    captured: list[VideoSourceRequest] = []

    class Composition:
        def run(self) -> None:
            pass

    def compose(*, video_source: VideoSourceRequest):
        captured.append(video_source)
        return Composition()

    monkeypatch.setattr(operator_main, "compose_operator_desktop", compose)

    assert operator_main.main(["run", "--camera", "2"]) == 0
    assert captured == [VideoSourceRequest.camera(2)]


def test_application_camera_snapshots_are_public_and_safe() -> None:
    runtime = camera_runtime(BlockingSource())

    assert runtime.application.camera_snapshot().status is CameraStatus.NOT_CONFIGURED
    runtime.application.configure_video_source(VideoSourceRequest.camera(0))
    snapshot = runtime.application.pipeline_snapshot()

    assert snapshot.status is CountingPipelineStatus.STOPPED
    assert snapshot.camera.status is CameraStatus.CLOSED
    assert snapshot.camera.display_name == "usb-camera:shared_operator_lane"
