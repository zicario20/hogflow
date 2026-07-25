"""Immutable four-dock occupancy registry for Phase 8.1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hogflow.domain.truck_operation import TruckOperation
from hogflow.domain.unloading_errors import (
    DockOccupiedError,
    DomainInvariantError,
    DuplicateOperationIdError,
    InvalidDockError,
    InvalidOperationTransitionError,
    OperationNotFoundError,
)
from hogflow.domain.unloading_models import (
    DockId,
    TruckOperationStatus,
    UnloadingSession,
)


@dataclass(frozen=True, slots=True)
class DockOperationRegistry:
    """Pure copy-on-write registry holding at most one current record per dock.

    A terminal operation remains retrievable until a new planned operation is
    registered at that dock. Replacing that terminal record is intentionally
    not persistence; historical storage belongs to a later phase.
    """

    operations: tuple[TruckOperation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.operations, tuple) or not all(
            isinstance(operation, TruckOperation) for operation in self.operations
        ):
            raise DomainInvariantError("Dock operations must be an immutable tuple.")
        dock_ids = tuple(operation.dock_id for operation in self.operations)
        operation_ids = tuple(operation.operation_id for operation in self.operations)
        if len(dock_ids) != len(set(dock_ids)):
            raise DomainInvariantError(
                "A dock registry may contain only one current record per dock."
            )
        if len(operation_ids) != len(set(operation_ids)):
            raise DuplicateOperationIdError("Current dock records must use unique operation IDs.")
        if len(self.operations) > len(DockId):
            raise DomainInvariantError("The Phase 8.1 registry supports exactly four docks.")
        object.__setattr__(
            self,
            "operations",
            tuple(
                sorted(
                    self.operations,
                    key=lambda operation: operation.dock_id.sequence_number,
                )
            ),
        )

    def operation_for(self, dock_id: DockId) -> TruckOperation | None:
        """Return the current record for a dock, including a terminal record."""

        dock = self._require_dock(dock_id)
        return next(
            (operation for operation in self.operations if operation.dock_id is dock),
            None,
        )

    def is_available(self, dock_id: DockId) -> bool:
        """Return whether a new planned operation may occupy the dock."""

        operation = self.operation_for(dock_id)
        return operation is None or operation.is_terminal

    def register_operation(self, operation: TruckOperation) -> DockOperationRegistry:
        """Register one planned aggregate if its dock is available."""

        if not isinstance(operation, TruckOperation):
            raise DomainInvariantError("Only a truck operation may occupy a dock.")
        if operation.status is not TruckOperationStatus.PLANNED:
            raise InvalidOperationTransitionError(
                "Only a planned truck operation may be registered."
            )
        existing = self.operation_for(operation.dock_id)
        if existing is not None and not existing.is_terminal:
            raise DockOccupiedError(
                f"{operation.dock_id.value} already has a non-terminal operation."
            )
        if any(
            current.operation_id == operation.operation_id
            and current.dock_id is not operation.dock_id
            for current in self.operations
        ):
            raise DuplicateOperationIdError(
                "Operation ID already belongs to another current dock record."
            )
        retained = tuple(
            current for current in self.operations if current.dock_id is not operation.dock_id
        )
        return DockOperationRegistry((*retained, operation))

    def add_session(
        self,
        dock_id: DockId,
        session: UnloadingSession,
    ) -> DockOperationRegistry:
        """Add a session through the current dock aggregate."""

        operation = self._require_operation(dock_id)
        return self._replace(operation.add_session(session))

    def start_operation(
        self,
        dock_id: DockId,
        started_at: datetime,
    ) -> DockOperationRegistry:
        """Start the current planned operation at one dock."""

        operation = self._require_operation(dock_id)
        return self._replace(operation.start(started_at))

    def start_session(
        self,
        dock_id: DockId,
        session_id: str,
        started_at: datetime,
    ) -> DockOperationRegistry:
        """Start one ordered session at one dock."""

        operation = self._require_operation(dock_id)
        return self._replace(operation.start_session(session_id, started_at))

    def complete_session(
        self,
        dock_id: DockId,
        session_id: str,
        actual_count: int,
        completed_at: datetime,
    ) -> DockOperationRegistry:
        """Finalize one active session at one dock."""

        operation = self._require_operation(dock_id)
        return self._replace(operation.complete_session(session_id, actual_count, completed_at))

    def cancel_session(
        self,
        dock_id: DockId,
        session_id: str,
        cancelled_at: datetime,
    ) -> DockOperationRegistry:
        """Cancel one unfinished session at one dock."""

        operation = self._require_operation(dock_id)
        return self._replace(operation.cancel_session(session_id, cancelled_at))

    def complete_operation(
        self,
        dock_id: DockId,
        completed_at: datetime,
    ) -> DockOperationRegistry:
        """Complete the current operation and release its dock."""

        operation = self._require_operation(dock_id)
        return self._replace(operation.complete(completed_at))

    def cancel_operation(
        self,
        dock_id: DockId,
        cancelled_at: datetime,
    ) -> DockOperationRegistry:
        """Cancel the current operation and release its dock."""

        operation = self._require_operation(dock_id)
        return self._replace(operation.cancel(cancelled_at))

    def _replace(self, replacement: TruckOperation) -> DockOperationRegistry:
        return DockOperationRegistry(
            tuple(
                replacement if current.dock_id is replacement.dock_id else current
                for current in self.operations
            )
        )

    def _require_operation(self, dock_id: DockId) -> TruckOperation:
        dock = self._require_dock(dock_id)
        operation = self.operation_for(dock)
        if operation is None:
            raise OperationNotFoundError(f"{dock.value} has no registered operation.")
        return operation

    @staticmethod
    def _require_dock(dock_id: DockId) -> DockId:
        if not isinstance(dock_id, DockId):
            raise InvalidDockError("Dock registry operations require a supported dock.")
        return dock_id


__all__ = ["DockOperationRegistry"]
