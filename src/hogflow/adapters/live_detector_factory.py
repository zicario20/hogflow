"""Infrastructure composition for the configured local detector and tracker."""

from __future__ import annotations

from hogflow.adapters.supervision_bytetrack import SupervisionByteTrackAdapter
from hogflow.adapters.ultralytics_live_detector import UltralyticsLiveDetector
from hogflow.detection import DetectorBackend, EmptyDetector, LiveDetector, PigDetectorConfiguration
from hogflow.tracking import ByteTrackConfiguration, EmptyTracker, LiveTracker


def create_live_detector_and_tracker(
    configuration: PigDetectorConfiguration,
) -> tuple[LiveDetector, LiveTracker]:
    """Create exactly one detector/tracker pair for one pipeline lifecycle."""

    if not isinstance(configuration, PigDetectorConfiguration):
        raise TypeError("Detector/tracker composition requires detector configuration.")
    if configuration.backend is DetectorBackend.EMPTY:
        return EmptyDetector(), EmptyTracker()
    return (
        UltralyticsLiveDetector.from_configuration(configuration),
        SupervisionByteTrackAdapter(ByteTrackConfiguration()),
    )


__all__ = ["create_live_detector_and_tracker"]
