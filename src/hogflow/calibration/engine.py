"""Deterministic, bounded geometry analysis for autonomous counting."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from statistics import fmean, median
from typing import Iterable

from hogflow.calibration.models import (
    CalibrationConfidence,
    CorridorEstimate,
    CountFamilyMetrics,
    DirectionVector,
    LineCandidate,
    LineCandidateMetrics,
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
    lost_near_line_distance: float = 0.05
    minimum_post_line_samples: int = 2

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
            (self.lost_near_line_distance, "lost_near_line_distance"),
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
        if self.minimum_post_line_samples <= 0:
            raise ValueError("minimum_post_line_samples must be positive.")


@dataclass(slots=True)
class _TrackAccumulator:
    tracker_id: int
    first_frame: int
    last_frame: int
    first_center: tuple[float, float]
    last_center: tuple[float, float]
    sampled_centers: list[tuple[float, float]] = field(default_factory=list)
    sampled_frames: list[int] = field(default_factory=list)
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
            self.sampled_frames.append(observation.frame_sequence)
        elif len(self.sampled_centers) > 1:
            slot = 1 + ((self.observation_count - 1) % (len(self.sampled_centers) - 1))
            self.sampled_centers[slot] = current
            self.sampled_frames[slot] = observation.frame_sequence

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
            sampled_centers=tuple(
                center
                for _, center in sorted(
                    zip(self.sampled_frames, self.sampled_centers),
                    key=lambda item: item[0],
                )
            ),
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
                sampled_frames=[observation.frame_sequence],
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


def _side_transition_details(
    candidate: LineCandidate,
    summary: TrajectorySummary,
    *,
    epsilon: float = 0.005,
) -> tuple[int, int, int, tuple[tuple[int, bool], ...], tuple[int, ...]]:
    """Return directional crossings and bounded local transition evidence."""

    forward = 0
    reverse = 0
    crossings = 0
    transitions: list[tuple[int, bool]] = []
    points = tuple(NormalizedPoint(*point) for point in summary.sampled_centers)
    previous_side = None
    previous_point = None
    for index, current in enumerate(points):
        current_side = candidate.line.classify(current, epsilon)
        if current_side.value == "on_line":
            continue
        if previous_side is None:
            previous_side = current_side
            previous_point = current
            continue
        if previous_side is current_side:
            previous_point = current
            continue
        assert previous_point is not None
        finite = candidate.line.movement_intersection_parameter(previous_point, current) is not None
        transitions.append((index, finite))
        if finite:
            crossings += 1
            if (
                previous_side.value == "negative"
                and current_side.value == "positive"
                and candidate.positive_direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE
            ) or (
                previous_side.value == "positive"
                and current_side.value == "negative"
                and candidate.positive_direction is LiveCrossingDirection.POSITIVE_TO_NEGATIVE
            ):
                forward += 1
            else:
                reverse += 1
        previous_side = current_side
        previous_point = current
    return (
        forward,
        reverse,
        crossings,
        tuple(transitions),
        tuple(index for index, finite in transitions if finite),
    )


def _side_transition_count(
    candidate: LineCandidate,
    summary: TrajectorySummary,
    *,
    epsilon: float = 0.005,
) -> tuple[int, int, int]:
    """Return unique track-bounded finite crossings for compatibility."""

    forward, reverse, crossings, _, _ = _side_transition_details(
        candidate, summary, epsilon=epsilon
    )
    return forward, reverse, crossings


def count_family_metrics(primary_count: int, variant_counts: tuple[int, ...]) -> CountFamilyMetrics:
    """Summarize a primary count with variants using a median consensus."""

    if isinstance(primary_count, bool) or not isinstance(primary_count, int) or primary_count < 0:
        raise ValueError("primary_count must be a non-negative integer.")
    if not isinstance(variant_counts, tuple) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in variant_counts
    ):
        raise ValueError("variant_counts must be a tuple of non-negative integers.")
    family = (primary_count, *variant_counts)
    family_median = float(median(family))
    minimum = min(family)
    maximum = max(family)
    spread = maximum - minimum
    if family_median <= 0.0:
        relative = 0.0 if spread == 0 else 1.0
    else:
        relative = min(1.0, spread / family_median)
    primary_deviation = abs(primary_count - family_median)
    if family_median <= 0.0:
        primary_agreement = 0.0
    else:
        primary_agreement = max(0.0, min(1.0, 1.0 - primary_deviation / family_median))
    return CountFamilyMetrics(
        minimum=minimum,
        maximum=maximum,
        median=family_median,
        absolute_spread=spread,
        relative_spread=relative,
        primary_deviation=primary_deviation,
        primary_agreement=primary_agreement,
    )


def _legacy_or_primary_family(
    primary_or_counts: int | tuple[int, ...],
    variant_counts: tuple[int, ...] | None,
) -> CountFamilyMetrics:
    if variant_counts is None:
        if not isinstance(primary_or_counts, tuple):
            raise ValueError("variant_counts are required when a primary count is supplied.")
        if not primary_or_counts:
            return count_family_metrics(0, ())
        inferred_primary = int(median(primary_or_counts))
        return count_family_metrics(inferred_primary, primary_or_counts)
    if not isinstance(primary_or_counts, int):
        raise ValueError("primary count must be an integer.")
    return count_family_metrics(primary_or_counts, variant_counts)


def line_band_agreement(
    primary_count: int | tuple[int, ...],
    neighbor_counts: tuple[int, ...] | None = None,
) -> float:
    """Return primary-inclusive stability for a finite candidate line family."""

    metrics = _legacy_or_primary_family(primary_count, neighbor_counts)
    return max(0.0, min(1.0, metrics.primary_agreement * (1.0 - metrics.relative_spread)))


def relative_spread(counts: tuple[int, ...]) -> float:
    """Return max-min spread divided by the robust median, zero-safe."""

    if not counts:
        return 1.0
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
        raise ValueError("counts must be non-negative integers.")
    return count_family_metrics(int(median(counts)), counts).relative_spread


def detector_perturbation_agreement(
    primary_count: int | tuple[int, ...],
    variant_counts: tuple[int, ...] | None = None,
) -> float:
    """Return primary-inclusive stability for detector variants."""

    return line_band_agreement(primary_count, variant_counts)


def evaluate_candidate_tracks(
    candidate: LineCandidate,
    summaries: Iterable[TrajectorySummary],
    settings: AutonomousCalibrationSettings,
    *,
    neighbor_counts: tuple[int, ...] = (0,),
    detector_perturbation_counts: tuple[tuple[float, int], ...] = (),
    primary_count: int | None = None,
) -> LineCandidateMetrics:
    """Evaluate geometry-only crossings without changing an operational counter."""

    selected = select_eligible_trajectories(summaries, settings)
    expected = 0
    forward = 0
    reverse = 0
    multiple = 0
    continuity_values = []
    local_continuity_values = []
    alignments = []
    supporting_tracks = 0
    finite_tracks = 0
    near_line_candidates = 0
    lost_near_line = 0
    for summary in selected:
        details = _side_transition_details(candidate, summary)
        crossings = details[:3]
        transitions = details[3]
        finite_transition_indexes = details[4]
        if transitions:
            supporting_tracks += 1
        if crossings[2] > 0:
            finite_tracks += 1
            expected += 1
            forward += int(crossings[0] == 1 and crossings[1] == 0)
            reverse += int(crossings[1] > 0)
            if crossings[2] > 1:
                multiple += 1
            continuity_values.append(summary.continuity_ratio)
            transition_index = finite_transition_indexes[0]
            points = tuple(NormalizedPoint(*point) for point in summary.sampled_centers)
            before_side = (
                "negative"
                if candidate.positive_direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE
                else "positive"
            )
            after_side = "positive" if before_side == "negative" else "negative"
            before = sum(
                candidate.line.classify(point, 0.005).value == before_side
                for point in points[:transition_index]
            )
            after = sum(
                candidate.line.classify(point, 0.005).value == after_side
                for point in points[transition_index:]
            )
            minimum_samples = max(1, settings.minimum_post_line_samples)
            local_continuity_values.append(
                min(1.0, before / minimum_samples, after / minimum_samples)
            )
        normal = DirectionVector(
            -(candidate.line.end.y - candidate.line.start.y),
            candidate.line.end.x - candidate.line.start.x,
        )
        movement = _summary_direction(summary)
        if movement is not None:
            alignment = (movement.dot(normal) + 1.0) / 2.0
            if candidate.positive_direction is LiveCrossingDirection.POSITIVE_TO_NEGATIVE:
                alignment = 1.0 - alignment
            alignments.append(max(0.0, min(1.0, alignment)))
        points = tuple(NormalizedPoint(*point) for point in summary.sampled_centers)
        distances = [abs(candidate.line.signed_distance(point)) for point in points]
        near_line = bool(distances) and min(distances) <= settings.lost_near_line_distance
        if near_line or transitions:
            near_line_candidates += 1
            post_evidence = 0
            if finite_transition_indexes:
                transition_index = finite_transition_indexes[0]
                expected_side = (
                    "positive"
                    if candidate.positive_direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE
                    else "negative"
                )
                post_evidence = sum(
                    candidate.line.classify(point, 0.005).value == expected_side
                    for point in points[transition_index:]
                )
            endpoint_distance = abs(
                candidate.line.signed_distance(NormalizedPoint(*summary.last_center))
            )
            if (
                endpoint_distance <= settings.lost_near_line_distance
                and post_evidence < settings.minimum_post_line_samples
            ):
                lost_near_line += 1
    resolved_primary = forward if primary_count is None else primary_count
    line_family = count_family_metrics(resolved_primary, neighbor_counts)
    neighbor_agreement = line_band_agreement(resolved_primary, neighbor_counts)
    perturbation_counts = tuple(detector_perturbation_counts)
    detector_variant_values = tuple(count for _, count in perturbation_counts)
    detector_family = count_family_metrics(resolved_primary, detector_variant_values)
    perturbation_agreement = detector_perturbation_agreement(
        resolved_primary,
        detector_variant_values,
    )
    continuity = fmean(continuity_values) if continuity_values else 0.0
    alignment = fmean(alignments) if alignments else 0.0
    unique_ratio = forward / expected if expected else 0.0
    reverse_ratio = reverse / expected if expected else 0.0
    multiple_ratio = multiple / expected if expected else 0.0
    corridor_coverage = finite_tracks / supporting_tracks if supporting_tracks else 0.0
    lost_ratio = lost_near_line / near_line_candidates if near_line_candidates else 0.0
    local_continuity = fmean(local_continuity_values) if local_continuity_values else 0.0
    primary_disagreement = 1.0 - min(
        line_family.primary_agreement, detector_family.primary_agreement
    )
    score = (
        0.18 * alignment
        + 0.16 * unique_ratio
        + 0.14 * local_continuity
        + 0.14 * corridor_coverage
        + 0.14 * neighbor_agreement
        + 0.12 * perturbation_agreement
        + 0.06 * continuity
        + 0.06 * (1.0 - candidate.edge_penalty)
        - 0.08 * reverse_ratio
        - 0.06 * multiple_ratio
        - 0.08 * lost_ratio
        - 0.10 * primary_disagreement
    )
    reasons: list[str] = []
    if len(selected) < 5:
        reasons.append("INSUFFICIENT_TRACKS")
    if neighbor_agreement < 0.80:
        reasons.append("LOW_LINE_STABILITY")
    if line_family.primary_agreement < 0.80:
        reasons.append("PRIMARY_COUNT_DISAGREES_WITH_NEIGHBORS")
    if perturbation_agreement < 0.80:
        reasons.append("LOW_DETECTOR_PERTURBATION_STABILITY")
    if lost_ratio > 0.10:
        reasons.append("TRACK_LOSS_NEAR_LINE")
    if corridor_coverage < 0.80:
        reasons.append("LOW_CORRIDOR_COVERAGE")
    if reverse_ratio > 0.20:
        reasons.append("HIGH_REVERSE_RATE")
    if not reasons:
        reasons.append("CONSISTENT_INTERNAL_EVIDENCE")
    return LineCandidateMetrics(
        candidate=candidate,
        eligible_tracks=len(selected),
        expected_crossing_tracks=expected,
        forward_crossings=forward,
        reverse_crossings=reverse,
        multiple_crossings=multiple,
        continuity_score=continuity,
        direction_alignment=alignment,
        corridor_coverage=max(0.0, min(1.0, corridor_coverage)),
        lost_near_line_ratio=max(0.0, min(1.0, lost_ratio)),
        neighbor_counts=neighbor_counts,
        neighbor_agreement=neighbor_agreement,
        detector_perturbation_counts=perturbation_counts,
        perturbation_agreement=perturbation_agreement,
        score=max(0.0, min(1.0, score)),
        primary_count=resolved_primary,
        line_count_min=line_family.minimum,
        line_count_max=line_family.maximum,
        line_count_median=line_family.median,
        line_relative_spread=line_family.relative_spread,
        primary_line_agreement=line_family.primary_agreement,
        detector_variant_counts=detector_variant_values,
        detector_count_min=detector_family.minimum,
        detector_count_max=detector_family.maximum,
        detector_count_median=detector_family.median,
        detector_relative_spread=detector_family.relative_spread,
        primary_detector_agreement=detector_family.primary_agreement,
        crossing_local_continuity=local_continuity,
        confidence_reason_codes=tuple(reasons[:16]),
    )


def consistency_confidence(
    *,
    eligible_tracks: int,
    direction_purity: float,
    neighbor_agreement: float,
    continuity_score: float,
    score: float,
    detector_agreement: float | None = None,
    corridor_coverage: float | None = None,
    crossing_local_continuity: float | None = None,
    lost_near_line_ratio: float | None = None,
    unique_ratio: float | None = None,
    primary_line_agreement: float | None = None,
    primary_detector_agreement: float | None = None,
) -> CalibrationConfidence:
    """Classify internal consistency using fixed, non-accuracy thresholds."""

    detector = 1.0 if detector_agreement is None else detector_agreement
    coverage = 1.0 if corridor_coverage is None else corridor_coverage
    local = continuity_score if crossing_local_continuity is None else crossing_local_continuity
    lost = 0.0 if lost_near_line_ratio is None else lost_near_line_ratio
    unique = 1.0 if unique_ratio is None else unique_ratio
    primary_line = 1.0 if primary_line_agreement is None else primary_line_agreement
    primary_detector = 1.0 if primary_detector_agreement is None else primary_detector_agreement
    if (
        eligible_tracks >= 8
        and direction_purity >= 0.80
        and neighbor_agreement >= 0.80
        and detector >= 0.80
        and continuity_score >= 0.75
        and local >= 0.70
        and coverage >= 0.80
        and lost <= 0.10
        and unique >= 0.85
        and primary_line >= 0.80
        and primary_detector >= 0.80
        and score >= 0.75
    ):
        return CalibrationConfidence.HIGH
    if (
        eligible_tracks >= 5
        and direction_purity >= 0.65
        and neighbor_agreement >= 0.60
        and detector >= 0.60
        and continuity_score >= 0.55
        and local >= 0.45
        and coverage >= 0.50
        and lost <= 0.30
        and unique >= 0.65
        and score >= 0.55
    ):
        return CalibrationConfidence.MEDIUM
    if eligible_tracks >= 3:
        return CalibrationConfidence.LOW
    return CalibrationConfidence.INCONCLUSIVE


__all__ = [
    "AutonomousCalibrationEngine",
    "AutonomousCalibrationSettings",
    "count_family_metrics",
    "estimate_corridor",
    "estimate_dominant_direction",
    "consistency_confidence",
    "detector_perturbation_agreement",
    "evaluate_candidate_tracks",
    "generate_line_candidates",
    "line_band_agreement",
    "relative_spread",
    "select_eligible_trajectories",
]
