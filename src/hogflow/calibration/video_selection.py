"""Deterministic, path-free selection of one autonomous demo video."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from hogflow.core import InputDataError


@dataclass(frozen=True, slots=True)
class AutonomousCandidateSuitability:
    """Bounded local probe result used only for suitability, not performance."""

    readable: bool
    meaningful_pig_detections: bool
    eligible_trajectories: int
    metadata: dict[str, object]
    rejection_reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.readable, bool) or not isinstance(
            self.meaningful_pig_detections, bool
        ):
            raise InputDataError("Candidate suitability booleans must be explicit.")
        if not isinstance(self.eligible_trajectories, int) or self.eligible_trajectories < 0:
            raise InputDataError("Candidate eligible trajectories must be non-negative.")
        if not isinstance(self.metadata, dict):
            raise InputDataError("Candidate metadata must be a dictionary.")
        if self.rejection_reason is not None and not self.rejection_reason.strip():
            raise InputDataError("Candidate rejection reason cannot be empty.")

    @property
    def suitable(self) -> bool:
        return self.readable and self.meaningful_pig_detections and self.eligible_trajectories >= 3


@dataclass(frozen=True, slots=True)
class AutonomousVideoSelection:
    """Sanitized selection result with no local path or private basename."""

    candidate_id: str
    selection_rank: int
    candidate_key: str
    selected: bool
    selection_reason: str
    metadata: tuple[tuple[str, object], ...]
    rejected_candidates: tuple[tuple[str, str], ...]


SuitabilityProbe = Callable[[Path], AutonomousCandidateSuitability]


def _candidate_key(path: Path) -> str:
    return hashlib.sha256(path.name.casefold().encode("utf-8")).hexdigest()


def _candidate_id(path: Path) -> str:
    return f"candidate_{_candidate_key(path)[:12]}"


def _sanitized_metadata(metadata: dict[str, object]) -> tuple[tuple[str, object], ...]:
    result = []
    for key, value in sorted(metadata.items()):
        if not isinstance(key, str) or not key.strip():
            raise InputDataError("Candidate metadata keys must be non-empty text.")
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and any(token in value for token in ("\\", "/", "://")):
                raise InputDataError("Candidate metadata must not contain local paths.")
            result.append((key, value))
        else:
            raise InputDataError("Candidate metadata values must be scalar and sanitized.")
    return tuple(result)


def select_autonomous_demo_candidate(
    candidates: Iterable[Path],
    *,
    excluded_names: set[str],
    suitability_probe: SuitabilityProbe,
) -> AutonomousVideoSelection:
    """Select the first suitable candidate in sanitized-basename hash order."""

    if not callable(suitability_probe):
        raise InputDataError("Autonomous selection requires a suitability probe.")
    excluded = {name.casefold() for name in excluded_names}
    ordered = sorted(
        (path for path in candidates if path.name.casefold() not in excluded),
        key=_candidate_key,
    )
    if not ordered:
        raise InputDataError("No unexcluded autonomous demo candidates are available.")
    rejected: list[tuple[str, str]] = []
    for rank, path in enumerate(ordered, start=1):
        probe = suitability_probe(path)
        candidate_id = _candidate_id(path)
        if not probe.suitable:
            rejected.append((candidate_id, probe.rejection_reason or "insufficient_suitability"))
            continue
        return AutonomousVideoSelection(
            candidate_id="autonomous_demo_video_1",
            selection_rank=rank,
            candidate_key=_candidate_key(path),
            selected=True,
            selection_reason="first_suitable_in_sanitized_hash_order",
            metadata=_sanitized_metadata(probe.metadata),
            rejected_candidates=tuple(rejected),
        )
    return AutonomousVideoSelection(
        candidate_id="autonomous_demo_video_1",
        selection_rank=0,
        candidate_key="",
        selected=False,
        selection_reason="no_suitable_candidate",
        metadata=(),
        rejected_candidates=tuple(rejected),
    )


__all__ = [
    "AutonomousCandidateSuitability",
    "AutonomousVideoSelection",
    "select_autonomous_demo_candidate",
]
