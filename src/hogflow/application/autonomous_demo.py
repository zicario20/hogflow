"""Controlled application bridge for the bounded autonomous demo workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import RLock, Thread
from typing import Callable

from hogflow.calibration import (
    AutonomousCalibrationResult,
    AutonomousDemoResult,
    CalibrationConfidence,
    CalibrationStatus,
)


class AutonomousDemoState(str, Enum):
    """Presentation state for one mutually-exclusive autonomous demo run."""

    IDLE = "AUTO CALIBRATION IDLE"
    CALIBRATING = "CALIBRATING"
    READY = "AUTO CALIBRATION READY"
    LOW_CONFIDENCE = "AUTO CALIBRATION LOW CONFIDENCE"
    LOW = "AUTO CALIBRATION LOW CONFIDENCE"
    INCONCLUSIVE = "AUTOCALIBRATION INCONCLUSIVE"
    COUNTING = "COUNTING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class AutonomousDemoSnapshot:
    """Immutable, path-free autonomous state consumed by the presenter."""

    state: AutonomousDemoState = AutonomousDemoState.IDLE
    demo_id: str | None = None
    calibration: AutonomousCalibrationResult | None = None
    primary_count: int | None = None
    observed_count_min: int | None = None
    observed_count_max: int | None = None
    message: str = "Select a local video to begin."
    worker_alive: bool = False
    failures: tuple[str, ...] = ()

    @property
    def line_locked(self) -> bool:
        """Return whether a final selected line is safe to display."""

        return self.calibration is not None and self.calibration.selected_line is not None


RunFactory = Callable[
    [Path, Callable[[str, AutonomousCalibrationResult | None], None]], AutonomousDemoResult
]


class AutonomousDemoController:
    """Run one autonomous demo in one controlled, non-daemon worker.

    The bridge owns no counter, tracker, queue, or frame history. It is
    mutually exclusive with the normal camera worker at the application
    boundary and publishes only bounded immutable snapshots.
    """

    def __init__(self, run_factory: RunFactory) -> None:
        if not callable(run_factory):
            raise TypeError("Autonomous demo run factory must be callable.")
        self._run_factory = run_factory
        self._lock = RLock()
        self._thread: Thread | None = None
        self._snapshot = AutonomousDemoSnapshot()

    def snapshot(self) -> AutonomousDemoSnapshot:
        """Return the latest immutable state without exposing the worker."""

        with self._lock:
            return self._snapshot

    def start(self, video_path: Path) -> AutonomousDemoSnapshot:
        """Start one bounded run without blocking the caller/UI thread."""

        if not isinstance(video_path, Path) or not video_path.is_file():
            raise ValueError("Autonomous demo requires an existing local video file.")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("An autonomous demo is already running.")
            self._snapshot = AutonomousDemoSnapshot(
                state=AutonomousDemoState.CALIBRATING,
                demo_id="operator_autonomous_demo",
                message="Calibrating autonomous line and detector consistency…",
                worker_alive=True,
            )
            thread = Thread(
                target=self._run,
                args=(video_path,),
                name="hogflow-autonomous-demo",
                daemon=False,
            )
            self._thread = thread
            thread.start()
            return self._snapshot

    def close(self) -> AutonomousDemoSnapshot:
        """Wait briefly for a finished run and expose its final state."""

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.25)
        with self._lock:
            if self._thread is not None and not self._thread.is_alive():
                self._snapshot = AutonomousDemoSnapshot(
                    state=self._snapshot.state,
                    demo_id=self._snapshot.demo_id,
                    calibration=self._snapshot.calibration,
                    primary_count=self._snapshot.primary_count,
                    observed_count_min=self._snapshot.observed_count_min,
                    observed_count_max=self._snapshot.observed_count_max,
                    message=self._snapshot.message,
                    worker_alive=False,
                    failures=self._snapshot.failures,
                )
            return self._snapshot

    def _run(self, video_path: Path) -> None:
        def progress(stage: str, calibration: AutonomousCalibrationResult | None) -> None:
            with self._lock:
                if stage == "calibrating":
                    state = AutonomousDemoState.CALIBRATING
                    message = "Calibrating autonomous line and detector consistency…"
                elif stage == "calibration_ready":
                    confidence = (
                        CalibrationConfidence.INCONCLUSIVE
                        if calibration is None
                        else calibration.confidence
                    )
                    state = (
                        AutonomousDemoState.LOW_CONFIDENCE
                        if confidence is CalibrationConfidence.LOW
                        else AutonomousDemoState.READY
                    )
                    message = "Calibration geometry locked; preparing clean count pass."
                elif stage == "counting":
                    state = AutonomousDemoState.COUNTING
                    message = "Counting with the frozen calibrated configuration."
                else:
                    return
                current = self._snapshot
                self._snapshot = AutonomousDemoSnapshot(
                    state=state,
                    demo_id=current.demo_id,
                    calibration=calibration or current.calibration,
                    primary_count=current.primary_count,
                    observed_count_min=current.observed_count_min,
                    observed_count_max=current.observed_count_max,
                    message=message,
                    worker_alive=True,
                    failures=current.failures,
                )

        try:
            result = self._run_factory(video_path, progress)
            calibration = result.calibration
            with self._lock:
                if calibration.status is CalibrationStatus.INCONCLUSIVE:
                    state = AutonomousDemoState.INCONCLUSIVE
                    message = "Calibration is inconclusive; no automatic count was started."
                elif calibration.status is CalibrationStatus.FAILED:
                    state = AutonomousDemoState.FAILED
                    message = "Autonomous calibration failed; review the bounded diagnostics."
                else:
                    state = AutonomousDemoState.COMPLETE
                    message = "Autonomous demo complete; live count is technical evidence only."
                self._snapshot = AutonomousDemoSnapshot(
                    state=state,
                    demo_id=result.demo_id,
                    calibration=calibration,
                    primary_count=result.primary_count,
                    observed_count_min=calibration.line_count_min,
                    observed_count_max=calibration.line_count_max,
                    message=message,
                    worker_alive=False,
                    failures=result.failures,
                )
        except Exception:
            with self._lock:
                current = self._snapshot
                self._snapshot = AutonomousDemoSnapshot(
                    state=AutonomousDemoState.FAILED,
                    demo_id=current.demo_id,
                    calibration=current.calibration,
                    message="Autonomous demo failed; no business count was changed.",
                    worker_alive=False,
                    failures=("bounded_runtime_failure",),
                )


__all__ = ["AutonomousDemoController", "AutonomousDemoSnapshot", "AutonomousDemoState"]
