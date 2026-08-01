from __future__ import annotations

from pathlib import Path

import pytest
from _phase10_3_helpers import FakeGitPolicy, FakeMetadataInspector, create_authorized_media

from hogflow.validation import (
    AuthorizedVideoError,
    LocalValidationWorkspace,
    ModelAvailabilityError,
    ModelGateState,
    authorized_video_for_path,
    exact_authorized_filenames,
)


def test_exact_authorized_filenames_are_stable_and_ordered() -> None:
    assert exact_authorized_filenames() == (
        "WhatsApp Video 2026-07-18 at 9.39.07 AM.mp4",
        "WhatsApp Video 2026-07-18 at 9.42.24 AM.mp4",
        "WhatsApp Video 2026-07-18 at 9.43.17 AM.mp4",
    )
    assert authorized_video_for_path(exact_authorized_filenames()[0]).video_id == "video_1"


def test_unauthorized_video_is_rejected() -> None:
    with pytest.raises(AuthorizedVideoError, match="not authorized"):
        authorized_video_for_path("another.mp4")


def test_workspace_inspects_three_ignored_files_without_exposing_paths(tmp_path: Path) -> None:
    create_authorized_media(tmp_path)
    workspace = LocalValidationWorkspace(
        tmp_path,
        FakeMetadataInspector(),
        git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
    )
    inspected = workspace.inspect_authorized_videos()

    assert [item.video.video_id for item in inspected] == ["video_1", "video_2", "video_3"]
    assert all(not item.sidecar_present for item in inspected)
    assert all(item.classification_source == "phase_10_3_authorization" for item in inspected)
    assert "WhatsApp" not in repr(inspected)
    assert str(tmp_path) not in repr(inspected)


def test_missing_authorized_video_is_reported_by_sanitized_id(tmp_path: Path) -> None:
    (tmp_path / "data" / "raw").mkdir(parents=True)
    with pytest.raises(AuthorizedVideoError, match="video_1 is missing"):
        LocalValidationWorkspace(
            tmp_path,
            FakeMetadataInspector(),
            git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
        ).inspect_authorized_videos()


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (FakeGitPolicy(ignored=False), "ignored and untracked"),
        (FakeGitPolicy(tracked=True), "ignored and untracked"),
    ],
)
def test_media_must_be_ignored_and_untracked(
    tmp_path: Path, policy: FakeGitPolicy, message: str
) -> None:
    create_authorized_media(tmp_path)
    with pytest.raises(AuthorizedVideoError, match=message):
        LocalValidationWorkspace(
            tmp_path,
            FakeMetadataInspector(),
            git_policy=policy,  # type: ignore[arg-type]
        ).inspect_authorized_videos()


def test_missing_model_returns_truthful_gate(tmp_path: Path) -> None:
    workspace = LocalValidationWorkspace(
        tmp_path,
        FakeMetadataInspector(),
        git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
    )
    gate = workspace.locate_model()
    assert gate.state is ModelGateState.MISSING
    assert gate.compatible_artifact_count == 0
    assert gate.sanitized_model_identity is None


def test_one_ignored_compatible_model_returns_sanitized_provenance(tmp_path: Path) -> None:
    path = tmp_path / "data" / "models" / "private-pig-model.pt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake-model-for-hash")
    workspace = LocalValidationWorkspace(
        tmp_path,
        FakeMetadataInspector(),
        git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
    )
    gate = workspace.locate_model()
    assert gate.state is ModelGateState.AVAILABLE
    assert gate.sanitized_model_identity == "local_pt_model"
    assert len(gate.artifact_fingerprint or "") == 64
    assert "private-pig-model" not in repr(gate)
    assert str(tmp_path) not in repr(gate)


def test_tracked_model_is_rejected_without_path_exposure(tmp_path: Path) -> None:
    path = tmp_path / "weights" / "private.pt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")
    gate = LocalValidationWorkspace(
        tmp_path,
        FakeMetadataInspector(),
        git_policy=FakeGitPolicy(tracked=True),  # type: ignore[arg-type]
    ).locate_model()
    assert gate.state is ModelGateState.REJECTED
    assert gate.sanitized_model_identity is None
    assert str(tmp_path) not in repr(gate)


def test_multiple_compatible_models_require_explicit_selection(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    (root / "first.pt").write_bytes(b"one")
    (root / "second.onnx").write_bytes(b"two")
    gate = LocalValidationWorkspace(
        tmp_path,
        FakeMetadataInspector(),
        git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
    ).locate_model()
    assert gate.state is ModelGateState.AMBIGUOUS
    assert gate.compatible_artifact_count == 2
    assert gate.sanitized_model_identity is None


def test_explicit_model_outside_approved_roots_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "other" / "model.pt"
    path.parent.mkdir()
    path.write_bytes(b"fake")
    with pytest.raises(ModelAvailabilityError, match="outside approved"):
        LocalValidationWorkspace(
            tmp_path,
            FakeMetadataInspector(),
            git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
        ).locate_model("other/model.pt")
