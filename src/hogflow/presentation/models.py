"""Immutable display models for the Phase 9.1 operator desktop."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CountingLanePanel:
    """Display-only projection of the shared counting lane."""

    status: str
    current_dock: str
    truck: str
    pig_type: str
    current_session: str
    live_count: int


@dataclass(frozen=True, slots=True)
class DockPanel:
    """Display-only projection for one of the four operational docks."""

    dock_id: str
    title: str
    operation_id: str
    status: str
    pig_type: str
    truck_total: int
    current_session: str


@dataclass(frozen=True, slots=True)
class TotalsPanel:
    """Display-only finalized totals from one Phase 8 snapshot."""

    total_pigs: int
    totals_by_pig_type: tuple[tuple[str, int], ...]
    completed_trucks: int
    active_trucks: int


@dataclass(frozen=True, slots=True)
class OperatorScreen:
    """One complete, immutable rendering input produced by a manual refresh."""

    counting_lane: CountingLanePanel
    docks: tuple[DockPanel, ...]
    totals: TotalsPanel
    generated_at: str

    def __post_init__(self) -> None:
        if len(self.docks) != 4:
            raise ValueError("Operator screen requires exactly four dock panels.")


__all__ = ["CountingLanePanel", "DockPanel", "OperatorScreen", "TotalsPanel"]
