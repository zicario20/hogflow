"""Lifecycle-aware directional counting over Phase 5.4 crossing events."""

from __future__ import annotations

from datetime import datetime, timezone
from re import fullmatch
from time import monotonic
from typing import Callable

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting.live_counting_errors import (
    CountingCapacityError,
    CountingLifecycleError,
    CrossingCountingMismatchError,
    DuplicateCountingEventIdentityError,
    StaleCountingRequestError,
)
from hogflow.counting.live_counting_models import (
    CountingDecisionType,
    LiveCountingConfiguration,
    LiveCountingDecision,
    LiveCountingErrorCategory,
    LiveCountingResult,
    LiveCountingStats,
    OperationalCrossingDirection,
    TemporaryTrackIdentity,
)
from hogflow.counting.live_counting_telemetry import LiveCountingTelemetry
from hogflow.counting.live_models import LiveCrossingEvent, LiveCrossingResult

_SOURCE_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"


class LifecycleDirectionalCounter:
    """Count each temporary identity at most once in one crossing lifecycle.

    Reverses and repeated positives are explicit zero-increment decisions.
    Counted identities remain for the whole lifecycle and are cleared only by
    reset or close. This state is bounded by a configured capacity; reaching
    the limit fails atomically instead of evicting identities silently.
    """

    def __init__(
        self,
        configuration: LiveCountingConfiguration,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(configuration, LiveCountingConfiguration):
            raise InputDataError("Directional counter requires LiveCountingConfiguration.")
        self._configuration = configuration
        self._monotonic = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._telemetry = LiveCountingTelemetry()
        self._source_id: str | None = None
        self._crossing_lifecycle_id: str | None = None
        self._counting_lifecycle_generation = 0
        self._last_sequence: int | None = None
        self._counted_identities: set[TemporaryTrackIdentity] = set()

    @property
    def configuration(self) -> LiveCountingConfiguration:
        return self._configuration

    @property
    def is_started(self) -> bool:
        return self._source_id is not None

    @property
    def source_id(self) -> str:
        if self._source_id is None:
            raise CountingLifecycleError("Counting source is available only after startup.")
        return self._source_id

    @property
    def crossing_lifecycle_id(self) -> str:
        if self._crossing_lifecycle_id is None:
            raise CountingLifecycleError(
                "Crossing lifecycle identity is available only after counting startup."
            )
        return self._crossing_lifecycle_id

    @property
    def counting_lifecycle_id(self) -> str:
        if not self.is_started:
            raise CountingLifecycleError(
                "Counting lifecycle identity is available only after startup."
            )
        return f"counting-lifecycle-{self._counting_lifecycle_generation}"

    def start(self, source_id: str, crossing_lifecycle_id: str) -> None:
        """Bind empty counting state to one explicit crossing lifecycle."""

        if not self._configuration.enabled:
            self._telemetry.record_failure(LiveCountingErrorCategory.CONFIGURATION)
            raise ConfigurationError("Directional counting must be explicitly enabled.")
        self._validate_source_and_lifecycle(source_id, crossing_lifecycle_id)
        if self.is_started:
            if source_id != self._source_id or crossing_lifecycle_id != self._crossing_lifecycle_id:
                self._telemetry.record_failure(
                    LiveCountingErrorCategory.LIFECYCLE,
                    lifecycle_mismatch=True,
                )
                raise CountingLifecycleError(
                    "One directional counter cannot mix sources or crossing lifecycles."
                )
            return
        self._source_id = source_id
        self._crossing_lifecycle_id = crossing_lifecycle_id
        self._begin_new_counting_lifecycle()
        self._telemetry.record_started()

    def update(self, crossing: LiveCrossingResult) -> LiveCountingResult:
        """Validate and apply one frame atomically."""

        self._validate_update(crossing)
        started_monotonic = float(self._monotonic())
        started_at = self._wall_clock()
        ordered_events = tuple(sorted(crossing.events, key=lambda event: event.tracker_id))
        prospective_identities = set(self._counted_identities)
        prospective_total = len(prospective_identities)
        decisions: list[LiveCountingDecision] = []

        for event in ordered_events:
            identity = TemporaryTrackIdentity(
                source_id=event.source_id,
                crossing_lifecycle_id=event.tracker_lifecycle_id,
                tracker_id=event.tracker_id,
            )
            previously_counted = identity in prospective_identities
            operational_direction = self._operational_direction(event)
            total_before = prospective_total
            if operational_direction is OperationalCrossingDirection.REVERSE:
                decision_type = CountingDecisionType.IGNORED_REVERSE
                increment = 0
            elif previously_counted:
                decision_type = CountingDecisionType.IGNORED_DUPLICATE_POSITIVE
                increment = 0
            else:
                if len(prospective_identities) >= self._configuration.maximum_counted_identities:
                    self._telemetry.record_failure(LiveCountingErrorCategory.CAPACITY)
                    raise CountingCapacityError(
                        "Counted-identity capacity would be exceeded; frame was not applied."
                    )
                decision_type = CountingDecisionType.COUNTED_POSITIVE
                increment = 1
                prospective_identities.add(identity)
                prospective_total += 1
            decisions.append(
                self._decision(
                    event,
                    identity,
                    operational_direction,
                    decision_type,
                    increment,
                    total_before,
                    prospective_total,
                    previously_counted,
                )
            )

        finished_monotonic = float(self._monotonic())
        finished_at = self._wall_clock()
        result = LiveCountingResult(
            source_id=crossing.source_id,
            counting_lifecycle_id=self.counting_lifecycle_id,
            crossing_lifecycle_id=crossing.tracker_lifecycle_id,
            frame_sequence=crossing.frame_sequence,
            captured_at=crossing.captured_at,
            decisions=tuple(decisions),
            frame_increments=sum(item.count_increment for item in decisions),
            lifecycle_directional_count=prospective_total,
            counted_identities_current=len(prospective_identities),
            configuration_fingerprint=self._configuration.fingerprint,
            processing_started_at=started_at,
            processing_finished_at=finished_at,
            counting_latency_ms=max(0.0, finished_monotonic - started_monotonic) * 1000,
        )

        self._counted_identities = prospective_identities
        self._last_sequence = crossing.frame_sequence
        self._telemetry.record_success(result)
        return result

    def reset(self, crossing_lifecycle_id: str) -> None:
        """Clear total and counted identities for a new crossing lifecycle."""

        if not self.is_started:
            self._telemetry.record_failure(LiveCountingErrorCategory.RESET)
            raise CountingLifecycleError("Directional counter must be started before reset.")
        self._validate_source_and_lifecycle(self.source_id, crossing_lifecycle_id)
        if crossing_lifecycle_id == self._crossing_lifecycle_id:
            self._telemetry.record_failure(
                LiveCountingErrorCategory.RESET,
                lifecycle_mismatch=True,
            )
            raise CountingLifecycleError("Counting reset requires a new crossing lifecycle ID.")
        self._crossing_lifecycle_id = crossing_lifecycle_id
        self._begin_new_counting_lifecycle()
        self._telemetry.record_reset()

    def close(self) -> None:
        """Clear all active state; repeated calls are safe."""

        if not self.is_started:
            return
        self._counted_identities.clear()
        self._source_id = None
        self._crossing_lifecycle_id = None
        self._last_sequence = None
        self._telemetry.record_closed()

    def statistics(self) -> LiveCountingStats:
        return self._telemetry.snapshot()

    def record_preview_failure(self) -> None:
        self._telemetry.record_preview_failure()

    def _validate_update(self, crossing: LiveCrossingResult) -> None:
        if not self.is_started:
            self._telemetry.record_failure(LiveCountingErrorCategory.LIFECYCLE)
            raise CountingLifecycleError("Directional counter must be started before update.")
        if not isinstance(crossing, LiveCrossingResult):
            self._telemetry.record_failure(LiveCountingErrorCategory.INPUT)
            raise InputDataError("Directional counting input must be a LiveCrossingResult.")
        if crossing.source_id != self.source_id:
            self._telemetry.record_failure(
                LiveCountingErrorCategory.LIFECYCLE,
                lifecycle_mismatch=True,
            )
            raise CountingLifecycleError("Directional counter cannot mix source streams.")
        if crossing.tracker_lifecycle_id != self.crossing_lifecycle_id:
            self._telemetry.record_failure(
                LiveCountingErrorCategory.LIFECYCLE,
                lifecycle_mismatch=True,
            )
            raise CountingLifecycleError("Crossing lifecycle does not match active counting state.")
        if self._last_sequence is not None and crossing.frame_sequence <= self._last_sequence:
            self._telemetry.record_failure(
                LiveCountingErrorCategory.STALE,
                stale=True,
            )
            raise StaleCountingRequestError(
                "Counting crossing results must have increasing frame sequences."
            )
        if (
            crossing.configuration_fingerprint
            != self._configuration.crossing_configuration_fingerprint
        ):
            self._telemetry.record_failure(LiveCountingErrorCategory.CROSSING_MISMATCH)
            raise CrossingCountingMismatchError(
                "Crossing configuration does not match the counting policy."
            )
        event_ids = [event.tracker_id for event in crossing.events]
        if len(event_ids) != len(set(event_ids)):
            self._telemetry.record_failure(LiveCountingErrorCategory.DUPLICATE_EVENT)
            raise DuplicateCountingEventIdentityError(
                "One temporary tracker may have at most one crossing event per frame."
            )
        for event in crossing.events:
            self._validate_event(crossing, event)

    def _validate_event(
        self,
        crossing: LiveCrossingResult,
        event: LiveCrossingEvent,
    ) -> None:
        if (
            event.source_id != crossing.source_id
            or event.tracker_lifecycle_id != crossing.tracker_lifecycle_id
            or event.frame_sequence != crossing.frame_sequence
            or event.captured_at != crossing.captured_at
        ):
            self._telemetry.record_failure(LiveCountingErrorCategory.CROSSING_MISMATCH)
            raise CrossingCountingMismatchError(
                "Crossing event does not match its result source, lifecycle, or frame."
            )
        if (
            event.line_id != crossing.line_id
            or event.configuration_fingerprint != crossing.configuration_fingerprint
        ):
            self._telemetry.record_failure(LiveCountingErrorCategory.CROSSING_MISMATCH)
            raise CrossingCountingMismatchError(
                "Crossing event geometry provenance does not match its result."
            )

    def _decision(
        self,
        event: LiveCrossingEvent,
        identity: TemporaryTrackIdentity,
        operational_direction: OperationalCrossingDirection,
        decision_type: CountingDecisionType,
        increment: int,
        total_before: int,
        total_after: int,
        previously_counted: bool,
    ) -> LiveCountingDecision:
        return LiveCountingDecision(
            identity=identity,
            crossing_event=event,
            source_id=event.source_id,
            counting_lifecycle_id=self.counting_lifecycle_id,
            crossing_lifecycle_id=event.tracker_lifecycle_id,
            tracker_id=event.tracker_id,
            frame_sequence=event.frame_sequence,
            previous_frame_sequence=event.previous_frame_sequence,
            captured_at=event.captured_at,
            geometric_direction=event.direction,
            operational_direction=operational_direction,
            decision_type=decision_type,
            count_increment=increment,
            total_before=total_before,
            total_after=total_after,
            identity_previously_counted=previously_counted,
            counting_configuration_fingerprint=self._configuration.fingerprint,
            crossing_configuration_fingerprint=event.configuration_fingerprint,
            line_id=event.line_id,
        )

    def _operational_direction(
        self,
        event: LiveCrossingEvent,
    ) -> OperationalCrossingDirection:
        return (
            OperationalCrossingDirection.POSITIVE
            if event.direction is self._configuration.positive_direction
            else OperationalCrossingDirection.REVERSE
        )

    @staticmethod
    def _validate_source_and_lifecycle(
        source_id: object,
        crossing_lifecycle_id: object,
    ) -> None:
        if not isinstance(source_id, str) or fullmatch(_SOURCE_ID, source_id) is None:
            raise InputDataError("Counting source ID must be opaque text.")
        if (
            not isinstance(crossing_lifecycle_id, str)
            or fullmatch(_OPAQUE_ID, crossing_lifecycle_id) is None
        ):
            raise InputDataError("Crossing lifecycle ID must be opaque text.")

    def _begin_new_counting_lifecycle(self) -> None:
        self._counting_lifecycle_generation += 1
        self._last_sequence = None
        self._counted_identities.clear()


__all__ = ["LifecycleDirectionalCounter"]
