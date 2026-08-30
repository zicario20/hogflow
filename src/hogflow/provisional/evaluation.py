"""Evaluation-only dataset loading for the Phase 10.3A B holdout."""

from __future__ import annotations

from pathlib import Path

from hogflow.annotation.manifest import load_annotation_manifest, manifest_to_dict
from hogflow.annotation.models import (
    AnnotationStatus,
    DatasetSplit,
    ManifestValidationStatus,
)
from hogflow.annotation.validation import validate_annotation_dataset
from hogflow.core import InputDataError
from hogflow.training.dataset import _dataset_version
from hogflow.training.models import PreparedEvaluationDataset

_EVALUATION_SPLITS = frozenset({DatasetSplit.VALIDATION, DatasetSplit.TEST})
_FINALIZED_STATUSES = frozenset({AnnotationStatus.ANNOTATED, AnnotationStatus.VERIFIED_EMPTY})


def load_prepared_evaluation_dataset(
    dataset_root: str | Path,
    manifest_path: str | Path,
) -> PreparedEvaluationDataset:
    """Load one explicit holdout manifest without requiring a train split.

    Validation is scoped to manifest paths because the B holdout shares an
    ignored local workspace with the A development partitions. A training
    frame is rejected before validation so this boundary cannot accidentally
    become another training input.
    """

    root = Path(dataset_root)
    local_manifest_path = Path(manifest_path)
    manifest = load_annotation_manifest(local_manifest_path)
    if any(frame.split is DatasetSplit.TRAIN for frame in manifest.frames):
        raise InputDataError("An evaluation-only manifest must not contain training frames.")
    report = validate_annotation_dataset(root, manifest, scope_to_manifest=True)
    if not report.valid:
        raise InputDataError(
            f"Prepared evaluation dataset validation failed with {report.error_count} fatal issue(s)."
        )
    records = tuple(frame for frame in manifest.frames if frame.split in _EVALUATION_SPLITS)
    unready = tuple(
        frame
        for frame in records
        if frame.annotation_status not in _FINALIZED_STATUSES
        or frame.validation_status is ManifestValidationStatus.INVALID
    )
    if unready:
        raise InputDataError(
            "Evaluation frames may contain only annotated or verified-empty frames "
            "that are not marked invalid."
        )
    frame_ids = tuple(sorted(frame.frame_id for frame in records))
    if not frame_ids:
        raise InputDataError("Prepared evaluation manifest contains no validation or test frames.")
    return PreparedEvaluationDataset(
        frame_ids=frame_ids,
        root=root,
        manifest_path=local_manifest_path,
        manifest=manifest,
        validation_report=report,
        dataset_version=_dataset_version(root, manifest.frames, manifest_to_dict(manifest)),
    )


__all__ = ["load_prepared_evaluation_dataset"]
