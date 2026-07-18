"""Deterministic source-video-level dataset splitting on opaque clip IDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from hogflow.annotation.models import DatasetSplit, validate_phase4_identifier
from hogflow.core import (
    ConfigurationError,
    HogFlowError,
    InputDataError,
    configure_logging,
    get_logger,
)

LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SplitRatios:
    """Requested train, validation, and test proportions."""

    train: float = 0.70
    validation: float = 0.20
    test: float = 0.10

    def __post_init__(self) -> None:
        values = (self.train, self.validation, self.test)
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
            for value in values
        ):
            raise ConfigurationError("Split ratios must be finite positive numbers.")
        if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ConfigurationError("Train, validation, and test ratios must sum to 1.")


@dataclass(frozen=True, slots=True)
class SourceClipAssignment:
    """One opaque source clip assigned to exactly one dataset split."""

    clip_id: str
    split: DatasetSplit

    def __post_init__(self) -> None:
        validate_phase4_identifier(self.clip_id, field_name="clip_id")
        if not isinstance(self.split, DatasetSplit):
            raise InputDataError("split must be a DatasetSplit value.")


@dataclass(frozen=True, slots=True)
class SplitSummary:
    """Source counts for each split without dataset-quality claims."""

    total_clips: int
    train_clips: int
    validation_clips: int
    test_clips: int
    preparation_clips: int

    def __post_init__(self) -> None:
        values = (
            self.total_clips,
            self.train_clips,
            self.validation_clips,
            self.test_clips,
            self.preparation_clips,
        )
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in values
        ):
            raise InputDataError("Split summary counts must be non-negative integers.")
        if sum(values[1:]) != self.total_clips:
            raise InputDataError("Split summary component counts must equal total_clips.")


@dataclass(frozen=True, slots=True)
class DatasetSplitPlan:
    """Validated source-level split plan with deterministic assignments."""

    seed: int
    ratios: SplitRatios
    minimum_sources_for_evaluation: int
    assignments: tuple[SourceClipAssignment, ...]
    warnings: tuple[str, ...]
    summary: SplitSummary

    def __post_init__(self) -> None:
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise InputDataError("seed must be an integer.")
        if not isinstance(self.ratios, SplitRatios):
            raise InputDataError("ratios must be SplitRatios.")
        if (
            not isinstance(self.minimum_sources_for_evaluation, int)
            or isinstance(self.minimum_sources_for_evaluation, bool)
            or self.minimum_sources_for_evaluation < 3
        ):
            raise InputDataError("minimum_sources_for_evaluation must be at least 3.")
        if not isinstance(self.assignments, tuple) or not all(
            isinstance(item, SourceClipAssignment) for item in self.assignments
        ):
            raise InputDataError("assignments must be an immutable assignment tuple.")
        clip_ids = tuple(item.clip_id for item in self.assignments)
        if tuple(sorted(clip_ids)) != clip_ids or len(set(clip_ids)) != len(clip_ids):
            raise InputDataError("Split assignments must have unique clip IDs in sorted order.")
        if (
            not isinstance(self.warnings, tuple)
            or tuple(sorted(set(self.warnings))) != self.warnings
        ):
            raise InputDataError("warnings must be a unique sorted tuple.")
        if not isinstance(self.summary, SplitSummary) or self.summary != _summarize(
            self.assignments
        ):
            raise InputDataError("summary must match split assignments.")
        split_by_clip: dict[str, DatasetSplit] = {}
        for assignment in self.assignments:
            previous = split_by_clip.setdefault(assignment.clip_id, assignment.split)
            if previous is not assignment.split:
                raise InputDataError("A source clip cannot appear in more than one split.")

    @property
    def preparation_only(self) -> bool:
        """Return whether the plan intentionally avoids evaluation split claims."""

        return bool(self.assignments) and all(
            assignment.split is DatasetSplit.PREPARATION for assignment in self.assignments
        )


def create_source_split_plan(
    clip_ids: Sequence[str],
    *,
    seed: int = 42,
    ratios: SplitRatios = SplitRatios(),
    minimum_sources_for_evaluation: int = 10,
) -> DatasetSplitPlan:
    """Create an order-independent source-level split without duplicating clips."""

    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ConfigurationError("seed must be an integer.")
    if not isinstance(ratios, SplitRatios):
        raise ConfigurationError("ratios must be SplitRatios.")
    if (
        not isinstance(minimum_sources_for_evaluation, int)
        or isinstance(minimum_sources_for_evaluation, bool)
        or minimum_sources_for_evaluation < 3
    ):
        raise ConfigurationError("minimum_sources_for_evaluation must be at least 3.")
    identifiers = tuple(clip_ids)
    for identifier in identifiers:
        validate_phase4_identifier(identifier, field_name="clip_id")
    if len(set(identifiers)) != len(identifiers):
        raise InputDataError("Selected clip IDs must be unique.")

    warnings: set[str] = set()
    if not identifiers:
        warnings.add("no_selected_clips")
        assignments: tuple[SourceClipAssignment, ...] = ()
    elif len(identifiers) < minimum_sources_for_evaluation:
        warnings.update(
            {
                "insufficient_source_diversity_for_train_validation_test",
                "preparation_only_not_statistically_meaningful",
            }
        )
        assignments = tuple(
            SourceClipAssignment(clip_id=identifier, split=DatasetSplit.PREPARATION)
            for identifier in sorted(identifiers)
        )
    else:
        ranked = sorted(
            identifiers, key=lambda identifier: (_seeded_rank(identifier, seed), identifier)
        )
        counts = _allocate_split_counts(len(ranked), ratios)
        split_sequence = (
            (DatasetSplit.TRAIN, counts[DatasetSplit.TRAIN]),
            (DatasetSplit.VALIDATION, counts[DatasetSplit.VALIDATION]),
            (DatasetSplit.TEST, counts[DatasetSplit.TEST]),
        )
        assigned: list[SourceClipAssignment] = []
        offset = 0
        for split, count in split_sequence:
            assigned.extend(
                SourceClipAssignment(clip_id=identifier, split=split)
                for identifier in ranked[offset : offset + count]
            )
            offset += count
        assignments = tuple(sorted(assigned, key=lambda item: item.clip_id))

    return DatasetSplitPlan(
        seed=seed,
        ratios=ratios,
        minimum_sources_for_evaluation=minimum_sources_for_evaluation,
        assignments=assignments,
        warnings=tuple(sorted(warnings)),
        summary=_summarize(assignments),
    )


def load_selected_clip_ids(path: str | Path) -> tuple[str, ...]:
    """Load only selected opaque IDs from a Phase 4.1 sanitized plan."""

    payload = _load_json_object(path, description="detection selection plan")
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise InputDataError("Detection selection plan must contain a decisions array.")
    selected: list[str] = []
    for item in decisions:
        if not isinstance(item, dict):
            raise InputDataError("Detection selection decisions must be JSON objects.")
        if item.get("status") != "selected":
            continue
        identifier = item.get("clip_id")
        validate_phase4_identifier(identifier, field_name="clip_id")
        selected.append(identifier)
    if len(set(selected)) != len(selected):
        raise InputDataError("Detection selection plan contains duplicate clip IDs.")
    return tuple(sorted(selected))


def write_split_plan(plan: DatasetSplitPlan, path: str | Path) -> None:
    """Atomically write one sanitized deterministic split plan."""

    if not isinstance(plan, DatasetSplitPlan):
        raise InputDataError("plan must be DatasetSplitPlan.")
    payload = {
        "format_version": 1,
        "seed": plan.seed,
        "ratios": {
            "test": plan.ratios.test,
            "train": plan.ratios.train,
            "validation": plan.ratios.validation,
        },
        "minimum_sources_for_evaluation": plan.minimum_sources_for_evaluation,
        "preparation_only": plan.preparation_only,
        "warnings": list(plan.warnings),
        "summary": {
            "preparation_clips": plan.summary.preparation_clips,
            "test_clips": plan.summary.test_clips,
            "total_clips": plan.summary.total_clips,
            "train_clips": plan.summary.train_clips,
            "validation_clips": plan.summary.validation_clips,
        },
        "assignments": [
            {"clip_id": item.clip_id, "split": item.split.value} for item in plan.assignments
        ],
    }
    _atomic_write_json(Path(path), payload)


def read_split_plan(path: str | Path) -> DatasetSplitPlan:
    """Read and validate one sanitized split plan."""

    payload = _load_json_object(path, description="dataset split plan")
    try:
        ratios_payload = payload["ratios"]
        assignments_payload = payload["assignments"]
        warnings_payload = payload["warnings"]
        if not isinstance(ratios_payload, dict) or not isinstance(assignments_payload, list):
            raise TypeError
        if not isinstance(warnings_payload, list):
            raise TypeError
        assignments = tuple(
            SourceClipAssignment(
                clip_id=item["clip_id"],
                split=DatasetSplit(item["split"]),
            )
            for item in assignments_payload
        )
        ratios = SplitRatios(
            train=ratios_payload["train"],
            validation=ratios_payload["validation"],
            test=ratios_payload["test"],
        )
        return DatasetSplitPlan(
            seed=payload["seed"],
            ratios=ratios,
            minimum_sources_for_evaluation=payload["minimum_sources_for_evaluation"],
            assignments=assignments,
            warnings=tuple(warnings_payload),
            summary=_summarize(assignments),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InputDataError("Dataset split plan has an invalid structure.") from exc


def build_parser() -> argparse.ArgumentParser:
    """Create the source-video split CLI parser."""

    parser = argparse.ArgumentParser(
        description="Create a deterministic source-video-level dataset split plan."
    )
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.20)
    parser.add_argument("--test-ratio", type=float, default=0.10)
    parser.add_argument("--minimum-sources", type=int, default=10)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run source-level planning without reading any video."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        plan = create_source_split_plan(
            load_selected_clip_ids(arguments.selection),
            seed=arguments.seed,
            ratios=SplitRatios(
                train=arguments.train_ratio,
                validation=arguments.validation_ratio,
                test=arguments.test_ratio,
            ),
            minimum_sources_for_evaluation=arguments.minimum_sources,
        )
        write_split_plan(plan, arguments.output)
    except HogFlowError as exc:
        parser.error(str(exc))
    LOGGER.info(
        "Source split plan complete: %d opaque clips; preparation_only=%s",
        plan.summary.total_clips,
        plan.preparation_only,
    )
    return 0


def _allocate_split_counts(total: int, ratios: SplitRatios) -> dict[DatasetSplit, int]:
    splits = (DatasetSplit.TRAIN, DatasetSplit.VALIDATION, DatasetSplit.TEST)
    values = (ratios.train, ratios.validation, ratios.test)
    exact = [total * value for value in values]
    counts = [math.floor(value) for value in exact]
    remaining = total - sum(counts)
    order = sorted(range(3), key=lambda index: (-(exact[index] - counts[index]), index))
    for index in order[:remaining]:
        counts[index] += 1
    for empty_index in (index for index, count in enumerate(counts) if count == 0):
        donor = max(range(3), key=lambda index: (counts[index], values[index], -index))
        if counts[donor] <= 1:
            raise ConfigurationError("Not enough sources to create non-empty requested splits.")
        counts[donor] -= 1
        counts[empty_index] += 1
    return dict(zip(splits, counts, strict=True))


def _seeded_rank(identifier: str, seed: int) -> str:
    return hashlib.sha256(f"hogflow-split:{seed}:{identifier}".encode()).hexdigest()


def _summarize(assignments: tuple[SourceClipAssignment, ...]) -> SplitSummary:
    counts = {split: sum(item.split is split for item in assignments) for split in DatasetSplit}
    return SplitSummary(
        total_clips=len(assignments),
        train_clips=counts[DatasetSplit.TRAIN],
        validation_clips=counts[DatasetSplit.VALIDATION],
        test_clips=counts[DatasetSplit.TEST],
        preparation_clips=counts[DatasetSplit.PREPARATION],
    )


def _load_json_object(path: str | Path, *, description: str) -> dict[str, Any]:
    input_path = Path(path)
    if not input_path.is_file():
        raise InputDataError(f"The local {description} is missing or is not a file.")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError(f"The local {description} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise InputDataError(f"The local {description} must contain one JSON object.")
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
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
        raise InputDataError("Unable to write the sanitized dataset split plan.") from exc


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DatasetSplitPlan",
    "SourceClipAssignment",
    "SplitRatios",
    "SplitSummary",
    "create_source_split_plan",
    "load_selected_clip_ids",
    "read_split_plan",
    "write_split_plan",
]
