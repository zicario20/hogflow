"""Controlled application bridge for the bounded autonomous demo workflow."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from re import fullmatch
from threading import Event, RLock, Thread
from typing import Callable

from hogflow.calibration import (
    AutonomousCalibrationResult,
    AutonomousDemoProgress,
    AutonomousDemoResult,
    CalibrationConfidence,
    CalibrationStatus,
)
from hogflow.camera import LatestPreviewFrameChannel, PreviewFrame
from hogflow.detection import DetectorBackend, PigDetectorConfiguration

EXPECTED_V2_ARTIFACT_FINGERPRINT = (
    "892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c"
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
    CANCELLED = "CANCELLED"
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
    live_count: int | None = None
    frames_processed: int = 0
    crossing_events: int = 0
    latest_preview: PreviewFrame | None = None
    failure_category: str | None = None
    detector_ready: bool = False

    @property
    def line_locked(self) -> bool:
        """Return whether a final selected line is safe to display."""

        return (
            self.state
            in {
                AutonomousDemoState.READY,
                AutonomousDemoState.LOW_CONFIDENCE,
                AutonomousDemoState.COUNTING,
                AutonomousDemoState.COMPLETE,
            }
            and self.calibration is not None
            and self.calibration.selected_line is not None
        )


RunFactory = Callable[..., AutonomousDemoResult]


class AutonomousDemoController:
    """Run one autonomous demo in one controlled, non-daemon worker.

    The bridge owns no counter, tracker, queue, or frame history. It is
    mutually exclusive with the normal camera worker at the application
    boundary and publishes only bounded immutable snapshots.
    """

    def __init__(
        self,
        run_factory: RunFactory,
        *,
        preview_channel: LatestPreviewFrameChannel | None = None,
        detector_configuration: PigDetectorConfiguration | None = None,
        expected_artifact_fingerprint: str = EXPECTED_V2_ARTIFACT_FINGERPRINT,
        worker_join_timeout_seconds: float = 5.0,
    ) -> None:
        if not callable(run_factory):
            raise TypeError("Autonomous demo run factory must be callable.")
        self._run_factory = run_factory
        if preview_channel is not None and not isinstance(
            preview_channel, LatestPreviewFrameChannel
        ):
            raise TypeError("Autonomous preview channel must be a LatestPreviewFrameChannel.")
        self._preview = preview_channel or LatestPreviewFrameChannel()
        if detector_configuration is not None and not isinstance(
            detector_configuration, PigDetectorConfiguration
        ):
            raise TypeError("Autonomous detector configuration is invalid.")
        if (
            not isinstance(expected_artifact_fingerprint, str)
            or len(expected_artifact_fingerprint) != 64
            or any(
                character not in "0123456789abcdef" for character in expected_artifact_fingerprint
            )
        ):
            raise ValueError("Expected detector artifact fingerprint must be SHA-256 text.")
        if (
            not isinstance(worker_join_timeout_seconds, (int, float))
            or isinstance(worker_join_timeout_seconds, bool)
            or float(worker_join_timeout_seconds) <= 0
        ):
            raise ValueError("Autonomous worker join timeout must be positive.")
        self._detector_configuration = detector_configuration
        self._expected_artifact_fingerprint = expected_artifact_fingerprint
        self._join_timeout = float(worker_join_timeout_seconds)
        self._detector_ready_cache: bool | None = None
        self._detector_signature: tuple[object, ...] | None = None
        self._lock = RLock()
        self._thread: Thread | None = None
        self._stop_requested = Event()
        self._snapshot = AutonomousDemoSnapshot()

    @property
    def detector_ready(self) -> bool:
        """Return whether the configured detector is the frozen V2 model."""

        configuration = self._detector_configuration
        if configuration is None:
            return False
        if configuration.backend is not DetectorBackend.ULTRALYTICS:
            return False
        if (
            configuration.target_class_name.casefold() != "pig"
            or configuration.target_class_ids != (0,)
            or configuration.confidence_threshold != 0.25
            or configuration.iou_threshold != 0.5
            or configuration.inference_image_size != 640
            or configuration.maximum_detections != 300
            or configuration.half_precision
            or configuration.model_path is None
            or not configuration.model_path.is_file()
        ):
            return False
        try:
            stat = configuration.model_path.stat()
            provenance = configuration.provenance_path
            provenance_signature = None
            if provenance is not None:
                provenance_stat = provenance.stat()
                provenance_signature = (
                    str(provenance),
                    provenance_stat.st_mtime_ns,
                    provenance_stat.st_size,
                )
            signature = (
                str(configuration.model_path),
                stat.st_mtime_ns,
                stat.st_size,
                provenance_signature,
            )
        except OSError:
            return False
        if signature == self._detector_signature and self._detector_ready_cache is not None:
            return self._detector_ready_cache
        try:
            digest = hashlib.sha256(configuration.model_path.read_bytes()).hexdigest()
        except OSError:
            return False
        self._detector_signature = signature
        self._detector_ready_cache = digest == self._expected_artifact_fingerprint
        provenance = configuration.provenance_path
        if self._detector_ready_cache and provenance is not None:
            try:
                payload = json.loads(provenance.read_text(encoding="utf-8"))
                self._detector_ready_cache = (
                    payload.get("artifact_sha256") == self._expected_artifact_fingerprint
                    and payload.get("model_identity") == "hogflow_pig_demo_v2"
                    and payload.get("target_class_name") == "pig"
                    and payload.get("target_class_ids") == [0]
                )
            except (OSError, ValueError, TypeError):
                self._detector_ready_cache = False
        return self._detector_ready_cache

    def snapshot(self) -> AutonomousDemoSnapshot:
        """Return the latest immutable state without exposing the worker."""

        with self._lock:
            return self._snapshot

    def start(self, video_path: Path) -> AutonomousDemoSnapshot:
        """Start one bounded run without blocking the caller/UI thread."""

        if not isinstance(video_path, Path) or not video_path.is_file():
            raise ValueError("Autonomous demo requires an existing local video file.")
        if not self.detector_ready:
            raise RuntimeError("Auto Demo requires the frozen HogFlow pig demo detector.")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("An autonomous demo is already running.")
            self._stop_requested.clear()
            self._preview.reset()
            self._snapshot = AutonomousDemoSnapshot(
                state=AutonomousDemoState.CALIBRATING,
                demo_id="operator_autonomous_demo",
                message="Calibrating autonomous line and detector consistency…",
                worker_alive=True,
                detector_ready=self.detector_ready,
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
        """Cooperatively stop the worker and wait for bounded termination."""

        self.cancel()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._join_timeout)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return replace(
                    self._snapshot,
                    message="Auto Demo is still stopping; retry shutdown shortly.",
                )
            if self._snapshot.worker_alive:
                self._snapshot = replace(self._snapshot, worker_alive=False)
            return self._snapshot

    def cancel(self) -> AutonomousDemoSnapshot:
        """Request cooperative cancellation; never force-kill inference."""

        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return self._snapshot
            self._stop_requested.set()
            self._snapshot = replace(
                self._snapshot,
                message="Cancelling Auto Demo…",
            )
            return self._snapshot

    def reset_for_normal_mode(self) -> AutonomousDemoSnapshot:
        """Clear ephemeral autonomous state after a run before normal mode."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Cannot reset an active autonomous demo.")
            self._preview.clear()
            self._snapshot = AutonomousDemoSnapshot()
            self._thread = None
            self._stop_requested.clear()
            return self._snapshot

    def _run(self, video_path: Path) -> None:
        def progress(
            stage: str,
            calibration: AutonomousCalibrationResult | None,
            update: AutonomousDemoProgress | None = None,
        ) -> None:
            with self._lock:
                if update is not None:
                    if update.preview_frame is not None:
                        self._preview.publish(update.preview_frame)
                    current = self._snapshot
                    self._snapshot = replace(
                        current,
                        calibration=calibration or current.calibration,
                        live_count=(
                            update.current_count
                            if update.current_count is not None
                            else current.live_count
                        ),
                        frames_processed=max(current.frames_processed, update.frames_processed),
                        crossing_events=max(current.crossing_events, update.crossing_events),
                        latest_preview=(update.preview_frame or current.latest_preview),
                    )
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
                elif stage == "cancelled":
                    state = AutonomousDemoState.CANCELLED
                    message = "Auto Demo cancelled; no business count was changed."
                else:
                    return
                current = self._snapshot
                if (
                    stage == "calibration_ready"
                    and calibration is not None
                    and calibration.selected_line is not None
                    and current.latest_preview is not None
                ):
                    locked_preview = replace(
                        current.latest_preview,
                        line=calibration.selected_line,
                    )
                    self._preview.publish(locked_preview)
                    current = replace(current, latest_preview=locked_preview)
                self._snapshot = replace(
                    current,
                    state=state,
                    demo_id=current.demo_id,
                    calibration=calibration or current.calibration,
                    message=message,
                    worker_alive=True,
                )
                if stage == "counting" and update is None:
                    self._snapshot = replace(
                        self._snapshot,
                        live_count=0,
                        frames_processed=0,
                        crossing_events=0,
                    )

        try:
            try:
                parameters = inspect.signature(self._run_factory).parameters.values()
                accepts_stop = any(
                    parameter.kind is inspect.Parameter.VAR_POSITIONAL
                    or parameter.kind
                    in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                    and index >= 2
                    for index, parameter in enumerate(parameters)
                )
            except (TypeError, ValueError):
                accepts_stop = True
            result = (
                self._run_factory(video_path, progress, self._stop_requested.is_set)
                if accepts_stop
                else self._run_factory(video_path, progress)
            )
            calibration = result.calibration
            with self._lock:
                if (
                    result.cancelled
                    or result.hmi_state == "CANCELLED"
                    or (
                        self._stop_requested.is_set()
                        and calibration.status is not CalibrationStatus.FAILED
                    )
                ):
                    state = AutonomousDemoState.CANCELLED
                    message = "Auto Demo cancelled; no business count was changed."
                elif calibration.status is CalibrationStatus.INCONCLUSIVE:
                    state = AutonomousDemoState.INCONCLUSIVE
                    message = "Calibration is inconclusive; no automatic count was started."
                elif calibration.status is CalibrationStatus.FAILED:
                    state = AutonomousDemoState.FAILED
                    message = "Autonomous calibration failed; review the bounded diagnostics."
                else:
                    state = AutonomousDemoState.COMPLETE
                    message = "Autonomous demo complete; live count is technical evidence only."
                safe_failures = tuple(
                    value
                    if isinstance(value, str)
                    and fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value)
                    else "bounded_runtime_failure"
                    for value in result.failures
                )
                self._snapshot = replace(
                    self._snapshot,
                    state=state,
                    demo_id=result.demo_id,
                    calibration=calibration,
                    primary_count=result.primary_count,
                    observed_count_min=calibration.line_count_min,
                    observed_count_max=calibration.line_count_max,
                    live_count=result.primary_count,
                    frames_processed=max(self._snapshot.frames_processed, result.counting_frames),
                    crossing_events=max(
                        self._snapshot.crossing_events, result.counting_crossing_events
                    ),
                    message=message,
                    worker_alive=False,
                    failures=safe_failures,
                    failure_category=(
                        "bounded_runtime_failure" if state is AutonomousDemoState.FAILED else None
                    ),
                )
                if state is AutonomousDemoState.CANCELLED:
                    self._preview.clear()
                    self._snapshot = replace(self._snapshot, latest_preview=None)
        except Exception:
            with self._lock:
                current = self._snapshot
                self._snapshot = replace(
                    current,
                    state=AutonomousDemoState.FAILED,
                    message="Autonomous demo failed; no business count was changed.",
                    worker_alive=False,
                    failures=("bounded_runtime_failure",),
                    failure_category="bounded_runtime_failure",
                )


__all__ = [
    "AutonomousDemoController",
    "AutonomousDemoSnapshot",
    "AutonomousDemoState",
    "EXPECTED_V2_ARTIFACT_FINGERPRINT",
]
