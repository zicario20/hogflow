import json
from pathlib import Path

import pytest

from hogflow.annotation.models import DatasetSplit
from hogflow.core import ConfigurationError, InputDataError
from hogflow.data.dataset_splitting import (
    SplitRatios,
    create_source_split_plan,
    load_selected_clip_ids,
    read_split_plan,
    write_split_plan,
)


def _ids(count: int) -> tuple[str, ...]:
    return tuple(f"{index:024x}" for index in range(1, count + 1))


def test_split_is_source_isolated_deterministic_and_order_independent() -> None:
    identifiers = _ids(20)

    first = create_source_split_plan(identifiers, seed=17)
    second = create_source_split_plan(tuple(reversed(identifiers)), seed=17)

    assert first == second
    assert len(first.assignments) == len({item.clip_id for item in first.assignments})
    assert first.summary.total_clips == 20
    assert first.summary.train_clips == 14
    assert first.summary.validation_clips == 4
    assert first.summary.test_clips == 2
    assert first.summary.preparation_clips == 0


def test_different_seed_changes_assignment_without_duplication() -> None:
    identifiers = _ids(20)
    first = create_source_split_plan(identifiers, seed=1)
    second = create_source_split_plan(identifiers, seed=2)

    assert first.assignments != second.assignments
    assert {item.clip_id for item in first.assignments} == set(identifiers)
    assert {item.clip_id for item in second.assignments} == set(identifiers)


def test_small_dataset_becomes_preparation_only_with_warnings() -> None:
    plan = create_source_split_plan(_ids(3))

    assert plan.preparation_only
    assert all(item.split is DatasetSplit.PREPARATION for item in plan.assignments)
    assert "insufficient_source_diversity_for_train_validation_test" in plan.warnings
    assert "preparation_only_not_statistically_meaningful" in plan.warnings


def test_empty_selection_is_safe_and_explicit() -> None:
    plan = create_source_split_plan(())
    assert plan.summary.total_clips == 0
    assert plan.warnings == ("no_selected_clips",)
    assert not plan.preparation_only


def test_split_ratios_and_duplicate_ids_are_validated() -> None:
    with pytest.raises(ConfigurationError, match="sum"):
        SplitRatios(0.8, 0.2, 0.2)
    with pytest.raises(ConfigurationError, match="positive"):
        SplitRatios(0.8, 0.2, 0.0)
    with pytest.raises(InputDataError, match="unique"):
        create_source_split_plan((_ids(1)[0], _ids(1)[0]))


def test_split_plan_serialization_is_stable_and_path_private(tmp_path: Path) -> None:
    plan = create_source_split_plan(_ids(12), seed=99)
    output = tmp_path / "split.json"

    write_split_plan(plan, output)
    first = output.read_text(encoding="utf-8")
    write_split_plan(plan, output)

    assert output.read_text(encoding="utf-8") == first
    assert read_split_plan(output) == plan
    assert "C:/" not in first
    assert "/home/" not in first


def test_selected_clip_loader_ignores_rejected_items(tmp_path: Path) -> None:
    selected, rejected = _ids(2)
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps(
            {
                "decisions": [
                    {"clip_id": rejected, "status": "rejected"},
                    {"clip_id": selected, "status": "selected"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_selected_clip_ids(path) == (selected,)
