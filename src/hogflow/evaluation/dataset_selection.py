"""Metadata-only Phase 3 inventory selection for local detector preparation."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from re import fullmatch
from typing import Any, Mapping, Sequence

from hogflow.core import (
    HogFlowError,
    InputDataError,
    configure_logging,
    get_logger,
    phase4_clip_id,
)

LOGGER = get_logger(__name__)

FATAL_VALIDATION_ERRORS = frozenset(
    {
        "bounded_decode_failure",
        "decoded_dimensions_mismatch",
        "dimensions_changed_during_decoding",
        "file_cannot_be_opened",
        "invalid_dimensions",
        "invalid_fps",
        "invalid_frame_count",
        "invalid_review_sidecar",
        "unsupported_extension",
        "zero_duration",
    }
)


class SelectionStatus(str, Enum):
    """Outcome of applying Phase 4.1 detection-preparation criteria."""

    SELECTED = "selected"
    REJECTED = "rejected"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


@dataclass(frozen=True, slots=True)
class DetectionSelectionDecision:
    """One privacy-preserving metadata-only clip decision.

    ``clip_id`` is a deterministic hash-derived opaque ID. It is not a path,
    private filename, source reference, or persistent animal identity.
    """

    clip_id: str
    status: SelectionStatus
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.clip_id, str) or fullmatch(r"[0-9a-f]{24}", self.clip_id) is None:
            raise InputDataError("clip_id must be a 24-character lowercase hexadecimal ID.")
        if not isinstance(self.status, SelectionStatus):
            raise InputDataError("status must be a SelectionStatus value.")
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(reason, str) and reason and reason.strip() == reason
            for reason in self.reasons
        ):
            raise InputDataError("reasons must be an immutable tuple of non-empty strings.")
        if tuple(sorted(set(self.reasons))) != self.reasons:
            raise InputDataError("reasons must be unique and sorted.")
        if self.status is SelectionStatus.SELECTED and self.reasons:
            raise InputDataError("Selected clips must not contain rejection or review reasons.")
        if self.status is not SelectionStatus.SELECTED and not self.reasons:
            raise InputDataError("Rejected or manual-review decisions require reasons.")


@dataclass(frozen=True, slots=True)
class DetectionSelectionPlan:
    """Immutable aggregate plan containing no paths or private filenames."""

    decisions: tuple[DetectionSelectionDecision, ...]
    selected_count: int
    rejected_count: int
    manual_review_required_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.decisions, tuple) or not all(
            isinstance(item, DetectionSelectionDecision) for item in self.decisions
        ):
            raise InputDataError("decisions must be an immutable selection-decision tuple.")
        clip_ids = tuple(item.clip_id for item in self.decisions)
        if tuple(sorted(clip_ids)) != clip_ids or len(set(clip_ids)) != len(clip_ids):
            raise InputDataError("decisions must have unique clip IDs in sorted order.")
        expected_counts = {
            status: sum(item.status is status for item in self.decisions)
            for status in SelectionStatus
        }
        supplied_counts = (
            ("selected_count", self.selected_count, SelectionStatus.SELECTED),
            ("rejected_count", self.rejected_count, SelectionStatus.REJECTED),
            (
                "manual_review_required_count",
                self.manual_review_required_count,
                SelectionStatus.MANUAL_REVIEW_REQUIRED,
            ),
        )
        for field_name, value, status in supplied_counts:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise InputDataError(f"{field_name} must be a non-negative integer.")
            if value != expected_counts[status]:
                raise InputDataError(f"{field_name} does not match decision statuses.")

    @property
    def total_count(self) -> int:
        """Return the number of inventory clips represented by the plan."""

        return len(self.decisions)


def load_inventory_json(path: str | Path) -> dict[str, Any]:
    """Load one local Phase 3 inventory object without reading any videos."""

    inventory_path = Path(path)
    if not inventory_path.exists():
        raise InputDataError(f"Inventory file does not exist: {inventory_path}")
    if not inventory_path.is_file():
        raise InputDataError(f"Inventory path is not a file: {inventory_path}")
    try:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError(f"Inventory is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise InputDataError("Inventory must contain one JSON object.")
    return payload


def select_detection_candidates(inventory: Mapping[str, Any]) -> DetectionSelectionPlan:
    """Select detection-preparation clips using Phase 3 metadata only.

    A selected clip must be readable, explicitly authorized, carry the
    ``detection_candidate`` label, and contain no fatal validation error. The
    function never opens, decodes, copies, or exposes the associated video.
    Counting suitability is deliberately ignored as detector-quality evidence.
    """

    files = inventory.get("files")
    if not isinstance(files, list):
        raise InputDataError("Phase 3 inventory must contain a 'files' JSON array.")

    parsed: list[tuple[str, Mapping[str, Any]]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise InputDataError(f"Inventory file entry {index} must be a JSON object.")
        relative_path = _relative_inventory_path(item.get("relative_path"), index=index)
        if relative_path in seen_paths:
            raise InputDataError("Inventory relative_path values must be unique.")
        seen_paths.add(relative_path)
        parsed.append((relative_path, item))

    decisions = tuple(
        sorted(
            (_select_one(relative_path, item) for relative_path, item in parsed),
            key=lambda decision: decision.clip_id,
        )
    )
    return DetectionSelectionPlan(
        decisions=decisions,
        selected_count=sum(item.status is SelectionStatus.SELECTED for item in decisions),
        rejected_count=sum(item.status is SelectionStatus.REJECTED for item in decisions),
        manual_review_required_count=sum(
            item.status is SelectionStatus.MANUAL_REVIEW_REQUIRED for item in decisions
        ),
    )


def write_detection_selection_plan(
    plan: DetectionSelectionPlan,
    output_path: str | Path,
) -> None:
    """Atomically write a deterministic local plan containing only opaque IDs."""

    if not isinstance(plan, DetectionSelectionPlan):
        raise InputDataError("plan must be a DetectionSelectionPlan.")
    path = Path(output_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputDataError(f"Unable to create selection output directory: {path.parent}") from exc
    payload = {
        "format_version": 1,
        "criteria": {
            "authorization_required": True,
            "detection_candidate_required": True,
            "fatal_validation_errors": sorted(FATAL_VALIDATION_ERRORS),
            "readable_required": True,
        },
        "summary": {
            "manual_review_required_count": plan.manual_review_required_count,
            "rejected_count": plan.rejected_count,
            "selected_count": plan.selected_count,
            "total_count": plan.total_count,
        },
        "decisions": [
            {
                "clip_id": item.clip_id,
                "reasons": list(item.reasons),
                "status": item.status.value,
            }
            for item in plan.decisions
        ],
    }
    _atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def prepare_detection_selection(
    inventory_path: str | Path,
    output_path: str | Path,
) -> DetectionSelectionPlan:
    """Load a Phase 3 inventory, select clips, and write the local plan."""

    plan = select_detection_candidates(load_inventory_json(inventory_path))
    write_detection_selection_plan(plan, output_path)
    return plan


def build_parser() -> argparse.ArgumentParser:
    """Create the local Phase 4.1 dataset-selection CLI parser."""

    parser = argparse.ArgumentParser(
        description="Prepare a metadata-only local pig-detection selection plan."
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run local metadata-only selection and return a process status code."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        plan = prepare_detection_selection(arguments.inventory, arguments.output)
    except HogFlowError as exc:
        parser.error(str(exc))
    LOGGER.info(
        "Detection selection complete: %d selected, %d rejected, %d manual review",
        plan.selected_count,
        plan.rejected_count,
        plan.manual_review_required_count,
    )
    return 0


def _select_one(
    relative_path: str,
    item: Mapping[str, Any],
) -> DetectionSelectionDecision:
    readable = item.get("readable")
    if not isinstance(readable, bool):
        raise InputDataError(f"Inventory entry {relative_path!r} readable must be boolean.")
    labels = _string_set(item.get("suitability_labels"), field_name="suitability_labels")
    validation_errors = _string_set(
        item.get("validation_errors"),
        field_name="validation_errors",
    )
    review = item.get("review_metadata")
    if review is not None and not isinstance(review, dict):
        raise InputDataError(f"Inventory entry {relative_path!r} review_metadata is invalid.")
    authorized = review is not None and review.get("authorized_for_project") is True

    rejection_reasons: set[str] = set()
    if not readable:
        rejection_reasons.add("unreadable_clip")
    if not authorized:
        rejection_reasons.add("authorization_not_confirmed")
    fatal_errors = sorted(validation_errors & FATAL_VALIDATION_ERRORS)
    rejection_reasons.update(f"fatal_validation_error:{error}" for error in fatal_errors)
    if rejection_reasons:
        status = SelectionStatus.REJECTED
        reasons = tuple(sorted(rejection_reasons))
    else:
        unclassified_errors = sorted(
            validation_errors - FATAL_VALIDATION_ERRORS - {"authorization_not_confirmed"}
        )
        if unclassified_errors:
            status = SelectionStatus.MANUAL_REVIEW_REQUIRED
            reasons = tuple(
                f"unclassified_validation_error:{error}" for error in unclassified_errors
            )
        elif "detection_candidate" in labels:
            status = SelectionStatus.SELECTED
            reasons = ()
        elif "needs_manual_review" in labels:
            status = SelectionStatus.MANUAL_REVIEW_REQUIRED
            reasons = ("detection_candidate_not_confirmed",)
        else:
            status = SelectionStatus.REJECTED
            reasons = ("detection_candidate_not_confirmed",)

    return DetectionSelectionDecision(
        clip_id=phase4_clip_id(relative_path),
        status=status,
        reasons=reasons,
    )


def _relative_inventory_path(value: object, *, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputDataError(f"Inventory file entry {index} relative_path must be non-empty.")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    has_drive_prefix = bool(path.parts and path.parts[0].endswith(":"))
    if path.is_absolute() or has_drive_prefix or ".." in path.parts:
        raise InputDataError("Inventory relative_path must not be absolute or traverse parents.")
    return path.as_posix()


def _string_set(value: object, *, field_name: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise InputDataError(f"Inventory {field_name} must be a JSON string array.")
    return frozenset(value)


def _atomic_write_text(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise InputDataError(f"Unable to write selection plan: {path.name}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
