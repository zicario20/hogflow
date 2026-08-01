from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from math import inf, nan

import pytest

from hogflow.runtime import (
    ProcessMemorySnapshot,
    ProductionRuntimeConfiguration,
    ProductionRuntimeConfigurationError,
    StandardProcessMemoryProbe,
)


def test_production_runtime_configuration_defaults_are_bounded_and_stable() -> None:
    first = ProductionRuntimeConfiguration()
    second = ProductionRuntimeConfiguration()

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert first.warning_capacity == 32
    assert first.require_idle_lane_for_restart


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("heartbeat_interval_seconds", 0),
        ("stale_frame_after_seconds", nan),
        ("stalled_pipeline_after_seconds", inf),
        ("repeated_camera_failure_threshold", 0),
        ("repeated_detector_failure_threshold", True),
        ("maximum_manual_restarts", -1),
        ("warning_capacity", 0),
    ),
)
def test_production_runtime_configuration_rejects_invalid_values(field, value) -> None:
    with pytest.raises(ProductionRuntimeConfigurationError):
        ProductionRuntimeConfiguration(**{field: value})


def test_runtime_configuration_is_immutable() -> None:
    configuration = ProductionRuntimeConfiguration()

    with pytest.raises(FrozenInstanceError):
        configuration.warning_capacity = 2


def test_process_memory_snapshot_is_immutable_and_validated() -> None:
    captured = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = ProcessMemorySnapshot(captured, True, 10, 12)

    assert snapshot.resident_bytes == 10
    with pytest.raises(FrozenInstanceError):
        snapshot.resident_bytes = 11
    with pytest.raises(ValueError, match="Peak"):
        ProcessMemorySnapshot(captured, True, 12, 10)
    with pytest.raises(ValueError, match="timezone-aware"):
        ProcessMemorySnapshot(datetime(2026, 1, 1), True, 1, 1)
    with pytest.raises(ValueError, match="zero"):
        ProcessMemorySnapshot(captured, False, 1, 1)


def test_standard_memory_probe_returns_a_valid_bounded_sample() -> None:
    snapshot = StandardProcessMemoryProbe().snapshot()

    assert snapshot.available or (snapshot.resident_bytes == snapshot.peak_resident_bytes == 0)
