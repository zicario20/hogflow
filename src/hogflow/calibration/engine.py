"""Deterministic, bounded geometry analysis for autonomous counting."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from statistics import fmean
from typing import Iterable

from hogflow.calibration.models import (
    CorridorEstimate,
    DirectionVector,
    LineCandidate,
    TrajectoryObservation,
    TrajectorySummary,
)
from hogflow.counting import LiveCrossingDirection, NormalizedLine, NormalizedPoint


@dataclass(frozen=True, slots=True)
class AutonomousCalibrationSettings:
    """Explicit bounded thresholds for autonomous geometry analysis."""

    minimum_lifetime_frames: int = 8
    minimum_displacement: float = 0.04
    minimum_continuity_ratio: float = 0.5
    minimum_mean_confidence: float = 0.2
    maximum_jitter_ratio: float = 3.5
    maximum_sampled_centers: int = 64
    max_tracks: int = 512
    edge_margin: float = 0.08
    corridor_margin: float = 0.04
    minimum_direction_resultant: float = 0.35
    corridor_low_percentile: float = 0.10
    corridor_high_percentile: float = 0.90
    candidate_positions: tuple[float, ...] = (
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
    )
    neighbor_offsets: tuple[float, ...] = (-0.04, -0.02, 0.02, 0.04)
    diagnostic_confidences: tuple[float, ...] = (0.20, 0.30)

    def __post_init__(self) -> None:
        if self.minimum_lifetime_frames <= 0 or self.maximum_sampled_centers <= 0:
            raise ValueError("Calibration frame bounds must be positive.")
        if self.max_tracks <= 0:
            raise ValueError("Calibration max_tracks must be positive.")
        for value, name in (
            (self.minimum_displacement, "minimum_displacement"),
            (self.minimum_continuity_ratio, "minimum_continuity_ratio"),
            (self.minimum_mean_confidence, "minimum_mean_confidence"),
            (self.corridor_margin, "corridor_margin"),
            (self.edge_margin, "edge_margin"),
            (self.minimum_direction_resultant, "minimum_direction_resultant"),
            (self.corridor_low_percentile, "corridor_low_percentile"),
            (self.corridor_high_percentile, "corridor_high_percentile"),
        ):
            if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")
        if self.corridor_low_percentile >= self.corridor_high_percentile:
            raise ValueError("Corridor percentiles must be ordered.")
        if (
            not self.candidate_positions
            or tuple(sorted(self.candidate_positions)) != self.candidate_positions
        ):
            raise ValueError("Candidate positions must be a non-empty sorted tuple.")
        if not self.neighbor_offsets or 0.0 in self.neighbor_offsets:
            raise ValueError("Neighbor offsets must be non-empty and exclude the primary line.")


@dataclass(slots=True)
class _TrackAccumulator:
    tracker_id: int
    first_frame: int
    last_frame: int
    first_center: tuple[float, float]
    last_center: tuple[float, float]
    sampled_centers: list[tuple[float, float]] = field(default_factory=list)
    observation_count: int = 0
    path_length: float = 0.0
    confidence_total: float = 0.0
    edge_touched: bool = False

    def add(
        self, observation: TrajectoryObservation, settings: AutonomousCalibrationSettings
    ) -> None:
        if observation.frame_sequence < self.last_frame:
            return
        previous = self.last_center
        current = observation.center
        self.path_length += hypot(current[0] - previous[0], current[1] - previous[1])
        self.last_frame = observation.frame_sequence
        self.last_center = current
        self.observation_count += 1
        self.confidence_total += observation.confidence
        edge = settings.edge_margin
        self.edge_touched = (
            self.edge_touched
            or min(current[0], current[1], 1.0 - current[0], 1.0 - current[1]) <= edge
        )
        if len(self.sampled_centers) < settings.maximum_sampled_centers:
            self.sampled_centers.append(current)
        elif len(self.sampled_centers) > 1:
            slot = 1 + ((self.observation_count - 1) % (len(self.sampled_centers) - 1))
            self.sampled_centers[slot] = current

    def summary(self) -> TrajectorySummary:
        frame_span = self.last_frame - self.first_frame + 1
        displacement = hypot(
            self.last_center[0] - self.first_center[0],
            self.last_center[1] - self.first_center[1],
        )
        return TrajectorySummary(
            tracker_id=self.tracker_id,
            first_frame=self.first_frame,
            last_frame=self.last_frame,
            first_center=self.first_center,
            last_center=self.last_center,
            sampled_centers=tuple(self.sampled_centers),
            lifetime_frames=frame_span,
            displacement=displacement,
            path_length=self.path_length,
            continuity_ratio=min(1.0, self.observation_count / frame_span),
            mean_confidence=(self.confidence_total / self.observation_count),
            edge_touched=self.edge_touched,
        )


class AutonomousCalibrationEngine:
    """Accumulate bounded tracker centers without owning operational state."""

    def __init__(self, settings: AutonomousCalibrationSettings | None = None) -> None:
        self.settings = settings or AutonomousCalibrationSettings()
        self._tracks: dict[int, _TrackAccumulator] = {}

    def observe(self, observation: TrajectoryObservation) -> None:
        """Retain one current observation, rejecting stale or over-capacity IDs."""

        track = self._tracks.get(observation.tracker_id)
        if track is None:
            if len(self._tracks) >= self.settings.max_tracks:
                return
            track = _TrackAccumulator(
                tracker_id=observation.tracker_id,
                first_frame=observation.frame_sequence,
                last_frame=observation.frame_sequence,
                first_center=observation.center,
                last_center=observation.center,
                sampled_centers=[observation.center],
                observation_count=1,
                confidence_total=observation.confidence,
                edge_touched=min(
                    observation.center[0],
                    observation.center[1],
                    1.0 - observation.center[0],
                    1.0 - observation.center[1],
                )
                <= self.settings.edge_margin,
            )
            self._tracks[observation.tracker_id] = track
            return
        track.add(observation, self.settings)

    def summaries(self) -> tuple[TrajectorySummary, ...]:
        """Return bounded summaries in deterministic tracker-ID order."""

        return tuple(self._tracks[key].summary() for key in sorted(self._tracks))


def select_eligible_trajectories(
    summaries: Iterable[TrajectorySummary],
    settings: AutonomousCalibrationSettings,
) -> tuple[TrajectorySummary, ...]:
    """Return summaries that provide meaningful directional evidence."""

    eligible = []
    for summary in summaries:
        if summary.lifetime_frames < settings.minimum_lifetime_frames:
            continue
        if summary.displacement < settings.minimum_displacement:
            continue
        if summary.continuity_ratio < settings.minimum_continuity_ratio:
            continue
        if summary.mean_confidence < settings.minimum_mean_confidence:
            continue
        if (
            summary.displacement > 0
            and summary.path_length / summary.displacement > settings.maximum_jitter_ratio
        ):
            continue
        eligible.append(summary)
    return tuple(sorted(eligible, key=lambda item: item.tracker_id))


def _summary_direction(summary: TrajectorySummary) -> DirectionVector | None:
    dx = summary.last_center[0] - summary.first_center[0]
    dy = summary.last_center[1] - summary.first_center[1]
    if hypot(dx, dy) <= 1e-9:
        return None
    return DirectionVector(dx, dy)


def estimate_dominant_direction(
    summaries: Iterable[TrajectorySummary],
    settings: AutonomousCalibrationSettings,
) -> tuple[DirectionVector | None, float]:
    """Estimate robust direction and alignment purity from eligible tracks."""

    eligible = select_eligible_trajectories(summaries, settings)
    vectors = [
        (direction, summary.displacement)
        for summary in eligible
        if (direction := _summary_direction(summary))
    ]
    total_weight = sum(weight for _, weight in vectors)
    if total_weight <= 0.0:
        return None, 0.0
    sum_dx = sum(direction.dx * weight for direction, weight in vectors)
    sum_dy = sum(direction.dy * weight for direction, weight in vectors)
    resultant = hypot(sum_dx, sum_dy) / total_weight
    if resultant < settings.minimum_direction_resultant:
        return None, 0.0
    dominant = DirectionVector(sum_dx, sum_dy)
    purity = fmean(
        (max(0.0, min(1.0, (direction.dot(dominant) + 1.0) / 2.0)) for direction, _ in vectors)
    )
    return dominant, purity


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def estimate_corridor(
    summaries: Iterable[TrajectorySummary],
    direction: DirectionVector,
    settings: AutonomousCalibrationSettings,
) -> CorridorEstimate:
    """Estimate robust along/cross bounds around the sampled pig corridor."""

    points = [point for summary in summaries for point in summary.sampled_centers]
    if not points:
        raise ValueError("At least one trajectory point is required for a corridor.")
    reference = (fmean(point[0] for point in points), fmean(point[1] for point in points))
    perpendicular = (-direction.dy, direction.dx)
    along = [
        (point[0] - reference[0]) * direction.dx + (point[1] - reference[1]) * direction.dy
        for point in points
    ]
    cross = [
        (point[0] - reference[0]) * perpendicular[0] + (point[1] - reference[1]) * perpendicular[1]
        for point in points
    ]
    along_min = _percentile(along, settings.corridor_low_percentile) - settings.corridor_margin
    along_max = _percentile(along, settings.corridor_high_percentile) + settings.corridor_margin
    cross_min = _percentile(cross, settings.corridor_low_percentile) - settings.corridor_margin
    cross_max = _percentile(cross, settings.corridor_high_percentile) + settings.corridor_margin
    if along_min >= along_max or cross_min >= cross_max:
        raise ValueError("Trajectory corridor has no measurable span.")
    return CorridorEstimate(reference, along_min, along_max, cross_min, cross_max, direction)


def _inside(point: tuple[float, float]) -> bool:
    return all(0.0 <= value <= 1.0 for value in point)


def generate_line_candidates(
    corridor: CorridorEstimate,
    direction: DirectionVector,
    settings: AutonomousCalibrationSettings,
) -> tuple[LineCandidate, ...]:
    """Generate finite lines perpendicular to flow and reject unsafe geometry."""

    perpendicular = (-direction.dy, direction.dx)
    candidates: list[LineCandidate] = []
    for index, position in enumerate(settings.candidate_positions, start=1):
        along = corridor.along_min + (corridor.along_max - corridor.along_min) * position
        first = (
            corridor.reference_center[0]
            + direction.dx * along
            + perpendicular[0] * corridor.cross_max,
            corridor.reference_center[1]
            + direction.dy * along
            + perpendicular[1] * corridor.cross_max,
        )
        second = (
            corridor.reference_center[0]
            + direction.dx * along
            + perpendicular[0] * corridor.cross_min,
            corridor.reference_center[1]
            + direction.dy * along
            + perpendicular[1] * corridor.cross_min,
        )
        if not _inside(first) or not _inside(second):
            continue
        edge_distance = min(
            first[0],
            first[1],
            1.0 - first[0],
            1.0 - first[1],
            second[0],
            second[1],
            1.0 - second[0],
            1.0 - second[1],
        )
        if position < settings.edge_margin or position > 1.0 - settings.edge_margin:
            continue
        edge_penalty = max(
            0.0, min(1.0, (settings.edge_margin - edge_distance) / settings.edge_margin)
        )
        candidates.append(
            LineCandidate(
                candidate_id=f"line_{index:02d}",
                line=NormalizedLine(NormalizedPoint(*first), NormalizedPoint(*second)),
                along_position=position,
                positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
                edge_penalty=edge_penalty,
            )
        )
    return tuple(candidates)


__all__ = [
    "AutonomousCalibrationEngine",
    "AutonomousCalibrationSettings",
    "estimate_corridor",
    "estimate_dominant_direction",
    "generate_line_candidates",
    "select_eligible_trajectories",
]
