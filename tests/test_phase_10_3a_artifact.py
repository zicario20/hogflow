from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from _phase10_3_helpers import FakeGitPolicy, FakeMetadataInspector

from hogflow.core import InputDataError
from hogflow.provisional.artifact import write_demo_model_provenance
from hogflow.validation import LocalValidationWorkspace, ModelGateState


def _workspace(root: Path) -> LocalValidationWorkspace:
    return LocalValidationWorkspace(
        root,
        FakeMetadataInspector(),
        git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
    )


def test_provenance_is_path_free_and_has_existing_phase_10_2_fields(tmp_path: Path) -> None:
    artifact = tmp_path / "hogflow_pig_demo.pt"
    artifact.write_bytes(b"demo")

    provenance = write_demo_model_provenance(
        artifact=artifact,
        dataset_fingerprint="a" * 64,
        configuration_fingerprint="b" * 64,
        training_run_id="phase10_3a_demo",
        evaluation_reference="demo_video_b_holdout",
        output_path=tmp_path / "provenance.json",
    )

    payload = json.loads(provenance.read_text(encoding="utf-8"))
    assert payload["purpose"] == "pig_detection"
    assert payload["backend"] == "ultralytics"
    assert payload["format"] == "pt"
    assert payload["class_mapping"] == {"0": "pig"}
    assert payload["artifact_sha256"] == hashlib.sha256(b"demo").hexdigest()
    assert payload["dataset_fingerprint"] == "a" * 64
    assert payload["configuration_fingerprint"] == "b" * 64
    assert payload["target_class_name"] == "pig"
    assert payload["target_class_id"] == 0
    assert payload["target_class_ids"] == [0]
    assert payload["complete"] is True
    assert str(tmp_path) not in json.dumps(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset_fingerprint", "not-a-sha"),
        ("configuration_fingerprint", "not-a-sha"),
        ("training_run_id", "private/path"),
        ("evaluation_reference", "private/path"),
    ],
)
def test_provenance_rejects_invalid_or_path_like_identifiers(
    tmp_path: Path, field: str, value: str
) -> None:
    artifact = tmp_path / "checkpoint.pt"
    artifact.write_bytes(b"demo")
    arguments = {
        "artifact": artifact,
        "dataset_fingerprint": "a" * 64,
        "configuration_fingerprint": "b" * 64,
        "training_run_id": "phase10_3a_demo",
        "evaluation_reference": "demo_video_b_holdout",
        "output_path": tmp_path / "provenance.json",
    }
    arguments[field] = value

    with pytest.raises(InputDataError):
        write_demo_model_provenance(**arguments)


def test_provenance_requires_existing_local_pt_artifact(tmp_path: Path) -> None:
    with pytest.raises(InputDataError, match="local model artifact"):
        write_demo_model_provenance(
            artifact=tmp_path / "missing.pt",
            dataset_fingerprint="a" * 64,
            configuration_fingerprint="b" * 64,
            training_run_id="phase10_3a_demo",
            evaluation_reference="demo_video_b_holdout",
            output_path=tmp_path / "provenance.json",
        )


def test_model_gate_is_available_only_for_one_ignored_candidate(tmp_path: Path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "hogflow_pig_demo.pt").write_bytes(b"demo")

    assert _workspace(tmp_path).locate_model().state is ModelGateState.AVAILABLE
