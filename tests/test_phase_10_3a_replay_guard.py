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

from hogflow.application import VideoSourceRequest
from hogflow.bootstrap import build_operator_runtime
from hogflow.camera import CameraPipelineLifecycleError, CountingPipelineStatus
from hogflow.presentation import OperatorAction, OperatorPresenter


def _local_video(tmp_path: Path) -> Path:
    video = tmp_path / "synthetic-replay.mp4"
    video.write_bytes(b"synthetic-test-only")
    return video


def _runtime_with_exhausted_file_and_active_session(tmp_path: Path):
    processor = ScriptedCrossingProcessor()
    runtime = build_operator_runtime(
        source_factory=lambda _configuration: RecordingSource(events=finite_events(1)),
        processor_factory=lambda: processor,
    )
    command = registration()
    runtime.application.register_truck(command)
    runtime.application.start_truck(command.dock_id)
    runtime.application.start_session(command.dock_id, command.sessions[0].session_id)
    runtime.application.configure_video_source(
        VideoSourceRequest.video_file(_local_video(tmp_path))
    )
    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    return runtime


def test_restart_video_is_blocked_when_shared_lane_is_occupied(tmp_path: Path) -> None:
    runtime = _runtime_with_exhausted_file_and_active_session(tmp_path)

    with pytest.raises(CameraPipelineLifecycleError, match="active counting session"):
        runtime.application.restart_video()

    assert runtime.counter.statistics().positives_counted == 0
    runtime.application.shutdown()


def test_start_pipeline_cannot_implicitly_replay_an_active_session(tmp_path: Path) -> None:
    runtime = _runtime_with_exhausted_file_and_active_session(tmp_path)

    with pytest.raises(CameraPipelineLifecycleError, match="active counting session"):
        runtime.application.start_counting_pipeline()

    runtime.application.shutdown()


def test_presenter_disables_replay_actions_for_occupied_lane(tmp_path: Path) -> None:
    runtime = _runtime_with_exhausted_file_and_active_session(tmp_path)
    screen = OperatorPresenter(runtime.application, RecordingView()).refresh()

    assert not screen.actions.is_enabled(OperatorAction.RESTART_VIDEO)
    assert not screen.actions.is_enabled(OperatorAction.START_PIPELINE)
    runtime.application.shutdown()
