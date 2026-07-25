from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest
from _phase6_helpers import (
    BASE_TIME,
    clean_pass_replay,
    tracking_result,
    vertical_candidate,
)

from hogflow.counting import LiveCrossingDirection, NormalizedLine, NormalizedPoint
from hogflow.evaluation import (
    EvidenceLevel,
    GroundTruthCrossingEvent,
    LineCandidate,
    LineEvaluationPlan,
    LineRankingMethod,
    TrackingReplay,
)
from hogflow.evaluation.line_errors import (
    LineEvaluationConfigurationError,
    TrackingReplayError,
)


def test_candidate_is_immutable_and_has_stable_fingerprint() -> None:
    candidate = vertical_candidate("line-center", 0.5)
    same = vertical_candidate("line-center", 0.5)
    changed = vertical_candidate("line-center", 0.6)

    assert candidate.fingerprint == same.fingerprint
    assert candidate.fingerprint != changed.fingerprint
    assert candidate.to_live_crossing_configuration().line == candidate.line
    with pytest.raises(FrozenInstanceError):
        candidate.epsilon = 0.2  # type: ignore[misc]


@pytest.mark.parametrize(
    "candidate_id",
    ("", "contains space", "private/path", "x" * 129),
)
def test_candidate_rejects_invalid_identifier(candidate_id: str) -> None:
    with pytest.raises(LineEvaluationConfigurationError):
        LineCandidate(
            candidate_id=candidate_id,
            line=NormalizedLine(NormalizedPoint(0.5, 0), NormalizedPoint(0.5, 1)),
        )


def test_candidate_rejects_duplicate_or_unbounded_tags_and_description() -> None:
    with pytest.raises(LineEvaluationConfigurationError, match="unique"):
        LineCandidate(
            candidate_id="candidate",
            line=NormalizedLine(NormalizedPoint(0.5, 0), NormalizedPoint(0.5, 1)),
            tags=("same", "same"),
        )
    with pytest.raises(LineEvaluationConfigurationError, match="240"):
        LineCandidate(
            candidate_id="candidate",
            line=NormalizedLine(NormalizedPoint(0.5, 0), NormalizedPoint(0.5, 1)),
            description="x" * 241,
        )


def test_plan_rejects_empty_and_duplicate_candidates() -> None:
    with pytest.raises(LineEvaluationConfigurationError, match="at least one"):
        LineEvaluationPlan(plan_id="empty", candidates=())

    candidate = vertical_candidate("same", 0.5)
    with pytest.raises(LineEvaluationConfigurationError, match="unique"):
        LineEvaluationPlan(plan_id="duplicate", candidates=(candidate, candidate))


def test_plan_canonicalizes_candidate_order_and_fingerprint() -> None:
    first = vertical_candidate("a", 0.3)
    second = vertical_candidate("b", 0.7)

    forward = LineEvaluationPlan(plan_id="plan", candidates=(first, second))
    reverse = LineEvaluationPlan(plan_id="plan", candidates=(second, first))

    assert forward == reverse
    assert forward.fingerprint == reverse.fingerprint
    assert tuple(item.candidate_id for item in forward.candidates) == ("a", "b")


def test_replay_is_immutable_and_accepts_sequence_gaps() -> None:
    replay = TrackingReplay(
        source_id="synthetic-source",
        replay_id="gaps",
        tracker_lifecycle_id="lifecycle",
        tracking_results=(tracking_result(1), tracking_result(10)),
        evidence_level=EvidenceLevel.CONTROLLED_REPLAY,
        provenance="controlled",
    )

    assert replay.duration_seconds == 9
    assert len(replay.fingerprint) == 64
    with pytest.raises(FrozenInstanceError):
        replay.replay_id = "changed"  # type: ignore[misc]


def test_replay_rejects_mixed_source_repeated_or_stale_sequences() -> None:
    with pytest.raises(TrackingReplayError, match="mix"):
        TrackingReplay(
            source_id="synthetic-source",
            replay_id="mixed",
            tracker_lifecycle_id="lifecycle",
            tracking_results=(
                tracking_result(0),
                tracking_result(1, source_id="other-source"),
            ),
            evidence_level=EvidenceLevel.SYNTHETIC,
            provenance="synthetic",
        )
    for sequences in ((1, 1), (2, 1)):
        with pytest.raises(TrackingReplayError, match="increase"):
            TrackingReplay(
                source_id="synthetic-source",
                replay_id="stale",
                tracker_lifecycle_id="lifecycle",
                tracking_results=tuple(tracking_result(value) for value in sequences),
                evidence_level=EvidenceLevel.SYNTHETIC,
                provenance="synthetic",
            )


def test_replay_rejects_decreasing_timestamps_and_empty_input() -> None:
    with pytest.raises(TrackingReplayError, match="at least one"):
        TrackingReplay(
            source_id="synthetic-source",
            replay_id="empty",
            tracker_lifecycle_id="lifecycle",
            tracking_results=(),
            evidence_level=EvidenceLevel.SYNTHETIC,
            provenance="synthetic",
        )
    with pytest.raises(TrackingReplayError, match="timestamps"):
        TrackingReplay(
            source_id="synthetic-source",
            replay_id="time-order",
            tracker_lifecycle_id="lifecycle",
            tracking_results=(
                tracking_result(0, captured_offset_seconds=2),
                tracking_result(1, captured_offset_seconds=1),
            ),
            evidence_level=EvidenceLevel.SYNTHETIC,
            provenance="synthetic",
        )


def test_ground_truth_validates_window_timestamp_and_evidence_level() -> None:
    event = GroundTruthCrossingEvent(
        event_id="event-1",
        frame_start=2,
        frame_end=4,
        direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        timestamp=BASE_TIME,
        annotation_quality=0.9,
        provenance="human-review",
    )
    assert event.frame_end == 4

    with pytest.raises(TrackingReplayError, match="timezone"):
        GroundTruthCrossingEvent(
            event_id="event-2",
            frame_start=1,
            frame_end=1,
            timestamp=datetime(2026, 1, 1),
            provenance="human-review",
        )
    with pytest.raises(TrackingReplayError, match="requires"):
        TrackingReplay(
            source_id="synthetic-source",
            replay_id="representative",
            tracker_lifecycle_id="lifecycle",
            tracking_results=(tracking_result(0),),
            evidence_level=EvidenceLevel.REPRESENTATIVE_WITH_GROUND_TRUTH,
            provenance="authorized-review",
        )


def test_clean_replay_fingerprint_is_stable() -> None:
    assert clean_pass_replay().fingerprint == clean_pass_replay().fingerprint
    assert clean_pass_replay().ground_truth_events[0].event_id == "reference-crossing"
    assert LineRankingMethod.EVENT_F1.value == "event_f1"
