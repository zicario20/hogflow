from __future__ import annotations

from pathlib import Path

import pytest
from _phase10_3_helpers import (
    NOW,
    FakeGitPolicy,
    FakeMetadataInspector,
    calibration_candidate,
    completed_result,
    create_authorized_media,
)

from hogflow.validation import (
    BLOCKED_EMPIRICAL_VERDICT,
    VIDEO_3_COUNTING_WARNING,
    EvidenceState,
    LocalValidationWorkspace,
    ModelAvailability,
    RealWorldValidationWorkflow,
    ValidationExecutionError,
    ValidationRunStatus,
)


class RecordingBackend:
    def __init__(self, model: ModelAvailability, *, incomplete_video: str | None = None) -> None:
        self.model = model
        self.incomplete_video = incomplete_video
        self.calls: list[str] = []

    def run(self, *, video_path: Path, model_path: Path, candidate, manual_total):
        del video_path, model_path
        self.calls.append(candidate.video_id)
        return completed_result(
            candidate.video_id,
            candidate,
            self.model,
            system_count=0 if candidate.video_id == "video_1" else 2,
            manual_total=manual_total,
            structurally_complete=candidate.video_id != self.incomplete_video,
        )


def _workspace(tmp_path: Path) -> tuple[LocalValidationWorkspace, tuple]:
    create_authorized_media(tmp_path)
    workspace = LocalValidationWorkspace(
        tmp_path,
        FakeMetadataInspector(),
        git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
    )
    return workspace, workspace.inspect_authorized_videos()


def _available_model(workspace: LocalValidationWorkspace, root: Path) -> ModelAvailability:
    path = root / "data" / "models" / "local.pt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake-model")
    return workspace.locate_model()


def test_missing_model_hard_gate_executes_no_backend_and_preserves_three_results(
    tmp_path: Path,
) -> None:
    workspace, inspected = _workspace(tmp_path)
    report = RealWorldValidationWorkflow(clock=lambda: NOW).run(
        workspace=workspace,
        inspected_videos=inspected,
        model_availability=workspace.locate_model(),
    )
    assert report.empirical_verdict == BLOCKED_EMPIRICAL_VERDICT
    assert [item.status for item in report.results] == [ValidationRunStatus.BLOCKED] * 3
    assert all(
        item.performance.frames_processed.state is EvidenceState.UNKNOWN for item in report.results
    )
    assert report.results[2].crossing_counting.system_count.state is EvidenceState.NOT_APPLICABLE
    assert VIDEO_3_COUNTING_WARNING in report.results[2].limitations


def test_model_present_backend_runs_videos_in_required_order(tmp_path: Path) -> None:
    workspace, inspected = _workspace(tmp_path)
    model = _available_model(workspace, tmp_path)
    backend = RecordingBackend(model)
    candidates = {
        video_id: calibration_candidate(video_id) for video_id in ("video_1", "video_2", "video_3")
    }
    report = RealWorldValidationWorkflow(clock=lambda: NOW).run(
        workspace=workspace,
        inspected_videos=inspected,
        model_availability=model,
        selected_candidates=candidates,
        backend=backend,
    )
    assert backend.calls == ["video_1", "video_2", "video_3"]
    assert all(item.status is ValidationRunStatus.COMPLETED for item in report.results)
    assert report.results[0].crossing_counting.system_count.value == 0


def test_video_2_waits_for_video_1_structural_success(tmp_path: Path) -> None:
    workspace, inspected = _workspace(tmp_path)
    model = _available_model(workspace, tmp_path)
    backend = RecordingBackend(model, incomplete_video="video_1")
    candidates = {
        video_id: calibration_candidate(video_id) for video_id in ("video_1", "video_2", "video_3")
    }
    report = RealWorldValidationWorkflow(clock=lambda: NOW).run(
        workspace=workspace,
        inspected_videos=inspected,
        model_availability=model,
        selected_candidates=candidates,
        backend=backend,
    )
    assert backend.calls == ["video_1"]
    assert report.results[1].status is ValidationRunStatus.BLOCKED
    assert report.results[1].conclusion == "video_1_structural_validation_incomplete"


def test_manual_total_is_kept_separate_for_each_counting_video(tmp_path: Path) -> None:
    workspace, inspected = _workspace(tmp_path)
    model = _available_model(workspace, tmp_path)
    backend = RecordingBackend(model)
    candidates = {
        video_id: calibration_candidate(video_id) for video_id in ("video_1", "video_2", "video_3")
    }
    report = RealWorldValidationWorkflow(clock=lambda: NOW).run(
        workspace=workspace,
        inspected_videos=inspected,
        model_availability=model,
        selected_candidates=candidates,
        manual_totals={"video_1": 0, "video_2": 3},
        backend=backend,
    )
    assert report.results[0].ground_truth.manual_total.value == 0
    assert report.results[1].ground_truth.manual_total.value == 3
    assert report.results[1].ground_truth.absolute_count_error.value == 1
    assert report.results[2].ground_truth.manual_total.state is EvidenceState.NOT_APPLICABLE


def test_backend_provenance_mismatch_fails_without_accepting_result(tmp_path: Path) -> None:
    workspace, inspected = _workspace(tmp_path)
    model = _available_model(workspace, tmp_path)
    candidate = calibration_candidate("video_1")

    class BadBackend:
        def run(self, **_kwargs):
            return completed_result("video_2", calibration_candidate("video_2"), model)

    with pytest.raises(ValidationExecutionError, match="mismatched"):
        RealWorldValidationWorkflow(clock=lambda: NOW).run(
            workspace=workspace,
            inspected_videos=inspected,
            model_availability=model,
            selected_candidates={
                "video_1": candidate,
                "video_2": calibration_candidate("video_2"),
                "video_3": calibration_candidate("video_3"),
            },
            backend=BadBackend(),
        )


@pytest.mark.parametrize("failure_stage", ["detector", "tracker", "crossing"])
def test_incomplete_backend_failure_cannot_fabricate_a_count(
    tmp_path: Path, failure_stage: str
) -> None:
    workspace, inspected = _workspace(tmp_path)
    model = _available_model(workspace, tmp_path)
    candidate = calibration_candidate("video_1")

    class FailingBackend:
        def run(self, **_kwargs):
            result = completed_result(
                "video_1", candidate, model, system_count=0, structurally_complete=False
            )
            assert result.crossing_counting.system_count.value == 0
            assert failure_stage in {"detector", "tracker", "crossing"}
            return result

    report = RealWorldValidationWorkflow(clock=lambda: NOW).run(
        workspace=workspace,
        inspected_videos=inspected,
        model_availability=model,
        selected_candidates={
            "video_1": candidate,
            "video_2": calibration_candidate("video_2"),
            "video_3": calibration_candidate("video_3"),
        },
        backend=FailingBackend(),
    )
    assert report.results[0].status is ValidationRunStatus.INCOMPLETE
    assert report.results[0].crossing_counting.system_count.value == 0
