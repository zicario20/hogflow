from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from _phase10_3_helpers import calibration_candidate, completed_result

from hogflow.evaluation import LineRankingMethod
from hogflow.validation import (
    VIDEO_3_COUNTING_WARNING,
    CalibrationPlan,
    EvidenceState,
    EvidenceValue,
    GroundTruthAssessment,
    ValidationConfigurationError,
)


def test_evidence_value_supports_all_explicit_states() -> None:
    assert EvidenceValue.measured(1).state is EvidenceState.MEASURED
    assert EvidenceValue.provided(2).state is EvidenceState.PROVIDED_MANUAL_GROUND_TRUTH
    assert EvidenceValue.derived(3).state is EvidenceState.DERIVED
    assert EvidenceValue.unknown().value is None
    assert EvidenceValue.not_applicable().value is None


@pytest.mark.parametrize(
    ("state", "value"),
    [(EvidenceState.UNKNOWN, 1), (EvidenceState.MEASURED, None)],
)
def test_evidence_value_rejects_incoherent_state(state: EvidenceState, value: int | None) -> None:
    with pytest.raises(ValidationConfigurationError, match="omit a value"):
        EvidenceValue(state, value)


def test_evidence_models_are_immutable() -> None:
    value = EvidenceValue.measured(1)
    with pytest.raises(FrozenInstanceError):
        value.value = 2  # type: ignore[misc]


def test_evidence_text_rejects_path_like_values() -> None:
    with pytest.raises(ValidationConfigurationError, match="sanitized text"):
        EvidenceValue.measured("/private/model.pt")


def test_manual_total_derives_count_error_without_fabricating_detector_metrics() -> None:
    assessment = GroundTruthAssessment.build(
        system_count=EvidenceValue.measured(12, "count"),
        manual_total=10,
        counting_applicable=True,
    )
    assert assessment.manual_total.state is EvidenceState.PROVIDED_MANUAL_GROUND_TRUTH
    assert assessment.signed_count_difference.value == 2
    assert assessment.absolute_count_error.value == 2
    assert assessment.percentage_count_error.value == 20.0
    assert assessment.detector_precision.state is EvidenceState.UNKNOWN
    assert assessment.detector_recall.state is EvidenceState.UNKNOWN
    assert assessment.detector_f1.state is EvidenceState.UNKNOWN


def test_missing_manual_total_keeps_all_count_errors_unknown() -> None:
    assessment = GroundTruthAssessment.build(
        system_count=EvidenceValue.measured(4, "count"),
        manual_total=None,
        counting_applicable=True,
    )
    assert assessment.manual_total.state is EvidenceState.UNKNOWN
    assert assessment.absolute_count_error.state is EvidenceState.UNKNOWN
    assert assessment.percentage_count_error.state is EvidenceState.UNKNOWN


def test_zero_manual_total_does_not_divide_by_zero() -> None:
    assessment = GroundTruthAssessment.build(
        system_count=EvidenceValue.measured(0, "count"),
        manual_total=0,
        counting_applicable=True,
    )
    assert assessment.absolute_count_error.value == 0
    assert assessment.percentage_count_error.state is EvidenceState.UNKNOWN


def test_video_3_result_is_not_counting_accuracy_evidence() -> None:
    from hogflow.validation import ModelAvailability, ModelGateState

    model = ModelAvailability(
        ModelGateState.AVAILABLE,
        1,
        "local_pt_model",
        "pt",
        "a" * 64,
        "compatible_local_model_available",
    )
    result = completed_result("video_3", calibration_candidate("video_3"), model)
    assert result.crossing_counting.system_count.state is EvidenceState.NOT_APPLICABLE
    assert VIDEO_3_COUNTING_WARNING in result.limitations


def test_calibration_plan_is_deterministic_and_reuses_phase_6_without_ranking() -> None:
    first = calibration_candidate("video_1", x=0.25)
    second_base = calibration_candidate("video_1", x=0.75)
    second = replace(
        second_base,
        candidate_id="video_1.candidate_b",
        line_candidate=replace(second_base.line_candidate, candidate_id="video_1.line_b"),
    )
    plan_a = CalibrationPlan("video_1.plan", "video_1", (second, first))
    plan_b = CalibrationPlan("video_1.plan", "video_1", (first, second))

    assert plan_a.fingerprint == plan_b.fingerprint
    assert (
        plan_a.line_evaluation_plan().ranking_method
        is LineRankingMethod.NO_AUTOMATIC_RECOMMENDATION
    )


def test_calibration_plans_cannot_mix_video_geometry() -> None:
    with pytest.raises(ValidationConfigurationError, match="cannot mix videos"):
        CalibrationPlan(
            "mixed.plan",
            "video_1",
            (calibration_candidate("video_1"), calibration_candidate("video_2")),
        )


def test_calibration_plan_candidate_collection_is_bounded() -> None:
    candidate = calibration_candidate("video_1")
    with pytest.raises(ValidationConfigurationError, match="requires candidates"):
        CalibrationPlan("video_1.large", "video_1", tuple(candidate for _ in range(65)))


def test_video_specific_candidate_fingerprints_include_video_identity() -> None:
    first = calibration_candidate("video_1", x=0.5)
    second = calibration_candidate("video_2", x=0.5)
    assert first.fingerprint != second.fingerprint
