from __future__ import annotations

from pathlib import Path

from hogflow.calibration.video_selection import (
    AutonomousCandidateSuitability,
    select_autonomous_demo_candidate,
)


def test_selection_excludes_development_and_historical_names() -> None:
    candidates = (
        Path("video A.mp4"),
        Path("video B.mp4"),
        Path("old-1.mp4"),
        Path("new-1.mp4"),
    )

    result = select_autonomous_demo_candidate(
        candidates,
        excluded_names={"video A.mp4", "video B.mp4", "old-1.mp4"},
        suitability_probe=lambda path: AutonomousCandidateSuitability(
            readable=path.name == "new-1.mp4",
            meaningful_pig_detections=True,
            eligible_trajectories=8,
            metadata={"duration_seconds": 1.0},
            rejection_reason=None,
        ),
    )

    assert result.candidate_id == "autonomous_demo_video_1"
    assert result.selection_reason == "first_suitable_in_sanitized_hash_order"
    assert result.rejected_candidates == ()
    assert result.metadata == (("duration_seconds", 1.0),)


def test_selection_is_deterministic_and_does_not_use_performance() -> None:
    candidates = (Path("z.mp4"), Path("a.mp4"))

    def probe(path: Path) -> AutonomousCandidateSuitability:
        return AutonomousCandidateSuitability(
            readable=True,
            meaningful_pig_detections=True,
            eligible_trajectories=100 if path.name == "z.mp4" else 8,
            metadata={},
            rejection_reason=None,
        )

    first = select_autonomous_demo_candidate(
        candidates, excluded_names=set(), suitability_probe=probe
    )
    second = select_autonomous_demo_candidate(
        tuple(reversed(candidates)), excluded_names=set(), suitability_probe=probe
    )

    assert first == second


def test_selection_reports_rejections_without_private_paths() -> None:
    result = select_autonomous_demo_candidate(
        (Path("bad.mp4"),),
        excluded_names=set(),
        suitability_probe=lambda _path: AutonomousCandidateSuitability(
            readable=False,
            meaningful_pig_detections=False,
            eligible_trajectories=0,
            metadata={},
            rejection_reason="unreadable",
        ),
    )

    assert result.selected is False
    assert result.rejected_candidates[0][1] == "unreadable"
    assert "bad.mp4" not in repr(result)


def test_selection_reports_no_suitable_candidate_without_private_paths() -> None:
    result = select_autonomous_demo_candidate(
        (Path("bad.mp4"),),
        excluded_names=set(),
        suitability_probe=lambda _path: AutonomousCandidateSuitability(
            readable=True,
            meaningful_pig_detections=False,
            eligible_trajectories=0,
            metadata={},
            rejection_reason="no_pigs",
        ),
    )

    assert result.selected is False
    assert result.selection_reason == "no_suitable_candidate"
    assert result.rejected_candidates[0][1] == "no_pigs"
