import json
from pathlib import Path

import pytest

from hogflow.core import InputDataError
from hogflow.evaluation.dataset_selection import (
    FATAL_VALIDATION_ERRORS,
    SelectionStatus,
    load_inventory_json,
    prepare_detection_selection,
    select_detection_candidates,
    write_detection_selection_plan,
)


def _entry(
    relative_path: str,
    *,
    readable: bool = True,
    authorized: bool = True,
    labels: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, object]:
    return {
        "relative_path": relative_path,
        "readable": readable,
        "suitability_labels": labels if labels is not None else ["detection_candidate"],
        "validation_errors": errors if errors is not None else [],
        "review_metadata": {"authorized_for_project": authorized} if authorized else None,
        "source_reference": "must not escape",
    }


def test_selected_clip_requires_readable_authorized_detection_candidate() -> None:
    plan = select_detection_candidates({"files": [_entry("private/source-a.mp4")]})

    assert plan.selected_count == 1
    assert plan.decisions[0].status is SelectionStatus.SELECTED
    assert plan.decisions[0].reasons == ()
    assert "source-a" not in plan.decisions[0].clip_id


def test_authorization_and_unreadable_failures_are_rejected() -> None:
    plan = select_detection_candidates(
        {
            "files": [
                _entry("unauthorized.mp4", authorized=False),
                _entry("unreadable.mp4", readable=False),
            ]
        }
    )

    assert plan.rejected_count == 2
    reasons = {reason for decision in plan.decisions for reason in decision.reasons}
    assert "authorization_not_confirmed" in reasons
    assert "unreadable_clip" in reasons


@pytest.mark.parametrize("fatal_error", sorted(FATAL_VALIDATION_ERRORS))
def test_each_fatal_validation_error_rejects_clip(fatal_error: str) -> None:
    plan = select_detection_candidates(
        {"files": [_entry("fatal.mp4", errors=[fatal_error])]},
    )

    assert plan.rejected_count == 1
    assert plan.decisions[0].reasons == (f"fatal_validation_error:{fatal_error}",)


def test_manual_review_is_distinct_from_rejection() -> None:
    plan = select_detection_candidates(
        {
            "files": [
                _entry(
                    "review.mp4",
                    labels=["tracking_candidate", "needs_manual_review"],
                )
            ]
        }
    )

    assert plan.manual_review_required_count == 1
    assert plan.decisions[0].status is SelectionStatus.MANUAL_REVIEW_REQUIRED
    assert plan.decisions[0].reasons == ("detection_candidate_not_confirmed",)


def test_detection_candidate_is_selected_even_when_counting_review_remains() -> None:
    plan = select_detection_candidates(
        {
            "files": [
                _entry(
                    "irregular-motion.mp4",
                    labels=["detection_candidate", "needs_manual_review"],
                )
            ]
        }
    )

    assert plan.selected_count == 1


def test_counting_candidate_alone_does_not_imply_detection_selection() -> None:
    plan = select_detection_candidates(
        {"files": [_entry("counting-only.mp4", labels=["counting_candidate"])]}
    )

    assert plan.rejected_count == 1
    assert plan.decisions[0].reasons == ("detection_candidate_not_confirmed",)


def test_selection_order_and_serialization_are_deterministic_and_private(tmp_path: Path) -> None:
    inventory = {
        "files": [
            _entry("private-name-z.mp4"),
            _entry("private-name-a.mp4", authorized=False),
        ]
    }
    forward = select_detection_candidates(inventory)
    reverse = select_detection_candidates({"files": list(reversed(inventory["files"]))})
    output = tmp_path / "phase4" / "selection.json"

    write_detection_selection_plan(forward, output)
    first_content = output.read_text(encoding="utf-8")
    write_detection_selection_plan(reverse, output)
    second_content = output.read_text(encoding="utf-8")

    assert forward == reverse
    assert first_content == second_content
    assert "private-name" not in first_content
    assert "source_reference" not in first_content
    assert str(tmp_path) not in first_content
    payload = json.loads(first_content)
    assert payload["summary"] == {
        "manual_review_required_count": 0,
        "rejected_count": 1,
        "selected_count": 1,
        "total_count": 2,
    }


def test_prepare_selection_loads_json_and_generates_local_output(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.json"
    output_path = tmp_path / "output" / "selection.json"
    inventory_path.write_text(
        json.dumps({"files": [_entry("source.mp4")]}),
        encoding="utf-8",
    )

    plan = prepare_detection_selection(inventory_path, output_path)

    assert plan.selected_count == 1
    assert output_path.exists()
    assert load_inventory_json(inventory_path)["files"][0]["relative_path"] == "source.mp4"


def test_selection_rejects_absolute_duplicate_and_malformed_inventory_paths() -> None:
    with pytest.raises(InputDataError, match="absolute"):
        select_detection_candidates({"files": [_entry("C:/private/source.mp4")]})
    with pytest.raises(InputDataError, match="unique"):
        select_detection_candidates({"files": [_entry("same.mp4"), _entry("same.mp4")]})
    with pytest.raises(InputDataError, match="files"):
        select_detection_candidates({})
