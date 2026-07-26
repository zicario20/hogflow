from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from hogflow.application import OperatorInputError, VideoSourceKind, VideoSourceRequest
from hogflow.camera import (
    CameraRecoveryConfiguration,
    CameraSnapshot,
    CameraStatus,
    CountingPipelineSnapshot,
    CountingPipelineStatus,
    PipelineFailureCategory,
)
from hogflow.core import ConfigurationError
from hogflow.streaming import SourceType


def test_camera_and_file_source_requests_are_immutable_and_explicit(tmp_path) -> None:
    video = tmp_path / "synthetic.mp4"
    video.write_bytes(b"fixture")

    camera = VideoSourceRequest.camera(0)
    file_source = VideoSourceRequest.video_file(video)

    assert camera.kind is VideoSourceKind.CAMERA
    assert file_source.kind is VideoSourceKind.VIDEO_FILE
    assert camera.camera_index == 0
    assert file_source.local_file == video
    assert str(video) not in repr(file_source)
    with pytest.raises(FrozenInstanceError):
        camera.camera_index = 1  # type: ignore[misc]


def test_video_source_request_rejects_conflicting_or_missing_values(tmp_path) -> None:
    with pytest.raises(OperatorInputError, match="non-negative"):
        VideoSourceRequest.camera(-1)
    with pytest.raises(OperatorInputError, match="existing file"):
        VideoSourceRequest.video_file(tmp_path / "missing.mp4")
    with pytest.raises(OperatorInputError, match="non-negative"):
        VideoSourceRequest(
            VideoSourceKind.CAMERA,
            camera_index=0,
            local_file=tmp_path,
        )


def test_pipeline_snapshots_are_immutable_and_contain_no_framework_objects() -> None:
    timestamp = datetime(2026, 7, 26, tzinfo=timezone.utc)
    camera = CameraSnapshot(
        source_id="shared_lane",
        source_type=SourceType.USB,
        display_name="USB camera",
        status=CameraStatus.RUNNING,
        last_frame_index=4,
        frames_acquired=5,
        last_successful_frame_at=timestamp,
        source_exhausted=False,
        failure_category=PipelineFailureCategory.NONE,
        failure_message=None,
    )
    snapshot = CountingPipelineSnapshot(
        status=CountingPipelineStatus.RUNNING,
        camera=camera,
        frames_processed=4,
        temporary_processing_failures=1,
        stale_results_rejected=0,
        active_crossing_lifecycle_id="crossing-1",
        worker_alive=True,
        failure_category=PipelineFailureCategory.NONE,
        failure_message=None,
        started_at=timestamp,
        stopped_at=None,
    )

    assert snapshot.camera.source_type is SourceType.USB
    assert snapshot.frames_processed == 4
    with pytest.raises(FrozenInstanceError):
        snapshot.frames_processed = 9  # type: ignore[misc]


def test_snapshot_rejects_unsafe_failure_text() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        CameraSnapshot(
            source_id="shared_lane",
            source_type=SourceType.FILE,
            display_name="Local video",
            status=CameraStatus.FAILED,
            last_frame_index=None,
            frames_acquired=0,
            last_successful_frame_at=None,
            source_exhausted=False,
            failure_category=PipelineFailureCategory.SOURCE_OPEN,
            failure_message=r"C:\private\video.mp4 failed",
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"enabled": 1}, "boolean"),
        ({"max_reopen_attempts": -1}, "non-negative"),
        ({"max_reopen_attempts": 0}, "at least one"),
        ({"temporary_failures_before_reopen": True}, "non-negative"),
        ({"temporary_failures_before_reopen": 0}, "at least one"),
        ({"retry_delay_seconds": float("nan")}, "finite"),
        ({"retry_delay_seconds": float("inf")}, "finite"),
        ({"retry_delay_seconds": -0.1}, "finite"),
    ],
)
def test_camera_recovery_configuration_rejects_invalid_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        CameraRecoveryConfiguration(**kwargs)  # type: ignore[arg-type]


def test_camera_recovery_configuration_is_immutable() -> None:
    configuration = CameraRecoveryConfiguration(
        max_reopen_attempts=2,
        temporary_failures_before_reopen=4,
        retry_delay_seconds=0,
    )

    assert configuration.retry_delay_seconds == 0.0
    with pytest.raises(FrozenInstanceError):
        configuration.max_reopen_attempts = 3  # type: ignore[misc]
