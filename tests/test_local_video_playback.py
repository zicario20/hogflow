from __future__ import annotations

from pathlib import Path

import pytest
from _phase9_3_helpers import (
    RecordingSource,
    ScriptedCrossingProcessor,
    finite_events,
    wait_for_status,
)
from _phase9_helpers import registration
from test_operator_camera_integration import RecordingView
from test_operator_live_preview import PreviewRecordingView
from test_preview_channel import preview_frame

import hogflow.__main__ as operator_main
from hogflow.application import VideoSourceRequest
from hogflow.bootstrap import OPERATOR_LANE_SOURCE_ID, build_operator_runtime
from hogflow.camera import (
    CameraPipelineLifecycleError,
    CameraStatus,
    CountingPipelineStatus,
)
from hogflow.presentation import OperatorAction, OperatorPresenter
from hogflow.streaming import StreamConfiguration


def _local_video(tmp_path: Path) -> Path:
    video = tmp_path / "synthetic-playback.mp4"
    video.write_bytes(b"synthetic-test-only")
    return video


def test_local_video_replays_repeatedly_without_reloading_processor(tmp_path: Path) -> None:
    video = _local_video(tmp_path)
    sources: list[RecordingSource] = []
    processor = ScriptedCrossingProcessor()
    processor_factory_calls = 0

    def source_factory(_configuration):
        source = RecordingSource(events=finite_events(2))
        sources.append(source)
        return source

    def processor_factory():
        nonlocal processor_factory_calls
        processor_factory_calls += 1
        return processor

    runtime = build_operator_runtime(
        source_factory=source_factory,
        processor_factory=processor_factory,
    )
    runtime.application.configure_video_source(VideoSourceRequest.video_file(video))

    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    first = runtime.application.pipeline_snapshot()
    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    runtime.application.restart_video()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    third = runtime.application.pipeline_snapshot()

    assert first.camera.status is CameraStatus.ENDED
    assert first.camera.source_exhausted
    assert third.camera.status is CameraStatus.ENDED
    assert third.camera.source_exhausted
    assert third.camera.frames_acquired == 6
    assert len(sources) == 3
    assert [source.open_calls for source in sources] == [1, 1, 1]
    assert [source.close_calls for source in sources] == [1, 1, 1]
    assert processor_factory_calls == 1
    assert processor.started == 1
    assert processor.resets == 2
    assert processor.closed == 0
    assert [sequence for sequence, _lifecycle in processor.processed] == list(range(6))

    runtime.application.shutdown()
    assert processor.closed == 1


def test_eof_enables_restart_video_and_exposes_completion_status(tmp_path: Path) -> None:
    video = _local_video(tmp_path)
    sources: list[RecordingSource] = []

    def source_factory(_configuration):
        source = RecordingSource(events=finite_events(1))
        sources.append(source)
        return source

    runtime = build_operator_runtime(
        source_factory=source_factory,
        processor_factory=ScriptedCrossingProcessor,
    )
    presenter = OperatorPresenter(runtime.application, RecordingView())
    presenter.configure_video_source(VideoSourceRequest.video_file(video))
    presenter.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    completed = presenter.refresh()

    assert completed.camera_pipeline.camera_status == "Exhausted"
    assert completed.camera_pipeline.preview_status == "End of Video"
    assert completed.actions.is_enabled(OperatorAction.START_PIPELINE)
    assert completed.actions.is_enabled(OperatorAction.RESTART_VIDEO)
    assert not completed.actions.is_enabled(OperatorAction.STOP_PIPELINE)

    restarted = presenter.restart_video()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert restarted.status_message == "Local Video Restarted"
    assert len(sources) == 2


def test_replay_keeps_session_counting_sequence_monotonic(tmp_path: Path) -> None:
    video = _local_video(tmp_path)
    processor = ScriptedCrossingProcessor(event_sequences=(1, 3), tracker_id=42)
    runtime = build_operator_runtime(
        source_factory=lambda _configuration: RecordingSource(events=finite_events(2)),
        processor_factory=lambda: processor,
    )
    application = runtime.application
    command = registration()
    application.register_truck(command)
    application.start_truck(command.dock_id)
    application.start_session(command.dock_id, "dock_1-session-1")
    application.configure_video_source(VideoSourceRequest.video_file(video))

    application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    application.restart_video()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert application.snapshot().counting_lane.current_session_count == 1
    assert runtime.counting_pipeline.snapshot().stale_results_rejected == 0
    assert runtime.counter.statistics().positives_counted == 1
    assert runtime.counter.statistics().duplicate_positives == 1


def test_last_preview_frame_is_retained_after_local_video_eof(tmp_path: Path) -> None:
    video = _local_video(tmp_path)
    runtime_ref = {}

    class PreviewPublishingProcessor(ScriptedCrossingProcessor):
        def process(self, frame, crossing_lifecycle_id):
            runtime_ref["runtime"].preview_channel.publish(preview_frame(frame.sequence_number))
            return super().process(frame, crossing_lifecycle_id)

    runtime = build_operator_runtime(
        source_factory=lambda _configuration: RecordingSource(events=finite_events(3)),
        processor_factory=PreviewPublishingProcessor,
    )
    runtime_ref["runtime"] = runtime
    runtime.application.configure_video_source(VideoSourceRequest.video_file(video))
    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    view = PreviewRecordingView()
    presenter = OperatorPresenter(runtime.application, view)
    first_screen = presenter.refresh()
    second_screen = presenter.refresh()

    assert first_screen.camera_pipeline.preview_status == "End of Video"
    assert second_screen.camera_pipeline.preview_status == "End of Video"
    assert len(view.plans) == 2
    assert all(plan is not None for plan in view.plans)
    assert [plan.frame.frame_sequence for plan in view.plans if plan is not None] == [2, 2]
    assert runtime.application.preview_snapshot().frames_consumed == 1
    assert not runtime.application.preview_snapshot().frame_available

    runtime.application.restart_video()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    replayed_screen = presenter.refresh()

    assert runtime.application.preview_snapshot().frames_published == 6
    assert view.plans[-1] is not None
    assert view.plans[-1].frame.frame_sequence == 5
    assert replayed_screen.camera_pipeline.preview_status == "End of Video"


def test_real_time_file_playback_is_optional_and_never_paces_camera(tmp_path: Path) -> None:
    video = _local_video(tmp_path)
    waits: list[float] = []

    class MonotonicClock:
        def __init__(self) -> None:
            self.value = 0.0

        def __call__(self) -> float:
            self.value += 0.01
            return self.value

    def source_factory(_configuration):
        return RecordingSource(
            events=finite_events(3),
            frame_interval_seconds=1.0,
        )

    runtime = build_operator_runtime(
        source_factory=source_factory,
        processor_factory=ScriptedCrossingProcessor,
        real_time_file_playback=True,
        playback_waiter=lambda delay: waits.append(delay) or False,
    )
    runtime.counting_pipeline._monotonic = MonotonicClock()
    runtime.application.configure_video_source(VideoSourceRequest.video_file(video))
    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert len(waits) == 2
    assert all(delay > 0.5 for delay in waits)

    waits.clear()
    camera_sources: list[RecordingSource] = []

    def camera_source_factory(_configuration):
        source = RecordingSource(
            events=finite_events(3),
            frame_interval_seconds=1.0,
        )
        camera_sources.append(source)
        return source

    camera_runtime = build_operator_runtime(
        source_factory=camera_source_factory,
        processor_factory=ScriptedCrossingProcessor,
        real_time_file_playback=True,
        playback_waiter=lambda delay: waits.append(delay) or False,
    )
    camera_runtime.counting_pipeline.configure(StreamConfiguration.usb(OPERATOR_LANE_SOURCE_ID, 0))
    camera_runtime.counting_pipeline.start()
    wait_for_status(camera_runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    camera_runtime.application.start_counting_pipeline()
    wait_for_status(camera_runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert waits == []
    assert camera_runtime.application.pipeline_snapshot().camera.status is CameraStatus.ENDED
    assert camera_sources[0].open_calls == 2
    with pytest.raises(CameraPipelineLifecycleError, match="only for"):
        camera_runtime.application.restart_video()


def test_cli_real_time_video_requires_file_and_reaches_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = _local_video(tmp_path)
    captured = {}

    class Composition:
        def run(self) -> None:
            pass

    def compose(**settings):
        captured.update(settings)
        return Composition()

    monkeypatch.setattr(operator_main, "compose_operator_desktop", compose)

    assert operator_main.main(["run", "--video", str(video), "--real-time-video"]) == 0
    assert captured["real_time_file_playback"] is True
    with pytest.raises(SystemExit) as invalid:
        operator_main.main(["run", "--camera", "0", "--real-time-video"])
    assert invalid.value.code == 2
