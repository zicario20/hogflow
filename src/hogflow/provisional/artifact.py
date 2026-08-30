"""Local-only final artifact provenance for the Phase 10.3A demo model."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from hogflow.core import InputDataError

_SHA256 = re.compile(r"[0-9a-f]{64}")
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_FINAL_MODEL_IDENTITY = "hogflow_pig_demo"
_FINAL_MODEL_FORMAT = "pt"
_IMAGE_SIZE = 640


def write_demo_model_provenance(
    artifact: str | Path,
    dataset_fingerprint: str,
    configuration_fingerprint: str,
    training_run_id: str,
    evaluation_reference: str,
    output_path: str | Path,
) -> Path:
    """Write one sanitized Phase 10.2-compatible demo-model provenance file.

    The artifact is read locally and fingerprinted; no artifact path or source
    media identity is copied into the JSON.  The helper intentionally writes
    provenance only and does not stage or copy a checkpoint into an approved
    validation-model root.
    """

    artifact_path = _require_local_artifact(artifact)
    _require_fingerprint(dataset_fingerprint, "dataset fingerprint")
    _require_fingerprint(configuration_fingerprint, "configuration fingerprint")
    _require_identifier(training_run_id, "training run ID")
    _require_identifier(evaluation_reference, "evaluation reference")

    destination = _require_output_path(output_path, artifact_path)
    repository_root = _repository_root(destination.parent)
    if repository_root is not None:
        _require_ignored_untracked(destination, repository_root, "provenance output")
        _require_ignored_untracked(artifact_path, repository_root, "model artifact")

    artifact_sha256 = _sha256(artifact_path)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "purpose": "pig_detection",
        "backend": "ultralytics",
        "framework": "ultralytics",
        "framework_version": _ultralytics_version(),
        "format": _FINAL_MODEL_FORMAT,
        "model_identity": _FINAL_MODEL_IDENTITY,
        "model_version": _FINAL_MODEL_IDENTITY,
        "target_class_name": "pig",
        "target_class_id": 0,
        "target_class_ids": [0],
        "class_mapping": {"0": "pig"},
        "image_size": _IMAGE_SIZE,
        "artifact_sha256": artifact_sha256,
        "dataset_fingerprint": dataset_fingerprint,
        "configuration_fingerprint": configuration_fingerprint,
        "training_run_id": training_run_id,
        "evaluation_reference": evaluation_reference,
        "selection_rationale": (
            "Provisional Phase 10.3A demo detector selected for empirical validation; "
            "not production validated."
        ),
        "training_date": datetime.now(timezone.utc).date().isoformat(),
        "complete": True,
    }
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise InputDataError("Unable to write local model provenance.") from exc
    return destination


def _require_local_artifact(value: str | Path) -> Path:
    try:
        path = Path(value).resolve()
    except (TypeError, ValueError, OSError) as exc:
        raise InputDataError("The local model artifact must be a filesystem path.") from exc
    if not path.exists() or not path.is_file():
        raise InputDataError("The local model artifact must exist and be a file.")
    if path.suffix.casefold() != ".pt":
        raise InputDataError("The provisional demo model artifact must use .pt format.")
    return path


def _require_output_path(value: str | Path, artifact: Path) -> Path:
    try:
        path = Path(value).resolve()
    except (TypeError, ValueError, OSError) as exc:
        raise InputDataError("Model provenance output must be a filesystem path.") from exc
    if path.suffix.casefold() != ".json":
        raise InputDataError("Model provenance output must use JSON format.")
    if path == artifact:
        raise InputDataError("Model provenance output must be separate from the artifact.")
    return path


def _require_fingerprint(value: object, label: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise InputDataError(f"The {label} must be a lowercase SHA-256 digest.")


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or _OPAQUE_ID.fullmatch(value) is None:
        raise InputDataError(f"The {label} must be a sanitized opaque identifier.")


def _sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise InputDataError("The local model artifact could not be fingerprinted.") from exc
    return digest.hexdigest()


def _ultralytics_version() -> str:
    try:
        value = version("ultralytics")
    except PackageNotFoundError:
        return "unknown"
    if not value or "/" in value or "\\" in value or len(value) > 64:
        return "unknown"
    return value


def _repository_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _require_ignored_untracked(path: Path, repository_root: Path, label: str) -> None:
    try:
        relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as exc:
        raise InputDataError(f"The {label} must remain inside the local repository.") from exc
    if not _git_status(repository_root, "check-ignore", "--quiet", relative):
        raise InputDataError(f"The {label} must remain ignored and untracked.")
    if _git_status(repository_root, "ls-files", "--error-unmatch", "--", relative):
        raise InputDataError(f"The {label} must remain ignored and untracked.")


def _git_status(repository_root: Path, *arguments: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repository_root.as_posix()}",
            *arguments,
        ],
        cwd=repository_root,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


__all__ = ["write_demo_model_provenance"]
