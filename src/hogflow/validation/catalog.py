"""Strict catalog for the three locally authorized Phase 10.3 videos."""

from __future__ import annotations

from pathlib import Path

from hogflow.validation.errors import AuthorizedVideoError
from hogflow.validation.models import AuthorizedVideo, ValidationVideoRole

_AUTHORIZED_FILENAMES = (
    "WhatsApp Video 2026-07-18 at 9.39.07 AM.mp4",
    "WhatsApp Video 2026-07-18 at 9.42.24 AM.mp4",
    "WhatsApp Video 2026-07-18 at 9.43.17 AM.mp4",
)

AUTHORIZED_VIDEOS = (
    AuthorizedVideo(
        video_id="video_1",
        role=ValidationVideoRole.PRIMARY_COUNTING_REFERENCE,
        candidate_classifications=(
            "counting_candidate",
            "detection_candidate",
            "tracking_candidate",
        ),
        counting_accuracy_eligible=True,
    ),
    AuthorizedVideo(
        video_id="video_2",
        role=ValidationVideoRole.SECONDARY_DIFFICULT_COUNTING,
        candidate_classifications=(
            "counting_candidate",
            "detection_candidate",
            "tracking_candidate",
        ),
        counting_accuracy_eligible=True,
    ),
    AuthorizedVideo(
        video_id="video_3",
        role=ValidationVideoRole.DETECTION_TRACKING_STRESS_ONLY,
        candidate_classifications=(
            "detection_candidate",
            "needs_manual_review",
            "tracking_candidate",
        ),
        counting_accuracy_eligible=False,
    ),
)

_BY_FILENAME = dict(zip(_AUTHORIZED_FILENAMES, AUTHORIZED_VIDEOS, strict=True))
_BY_ID = {item.video_id: item for item in AUTHORIZED_VIDEOS}


def exact_authorized_filenames() -> tuple[str, ...]:
    """Return the exact private local basenames in required processing order."""

    return _AUTHORIZED_FILENAMES


def authorized_video_for_path(path: str | Path) -> AuthorizedVideo:
    """Resolve only an exact authorized basename; never accept lookalikes."""

    candidate = Path(path)
    video = _BY_FILENAME.get(candidate.name)
    if video is None:
        raise AuthorizedVideoError("The requested local video is not authorized for Phase 10.3.")
    return video


def authorized_video_for_id(video_id: str) -> AuthorizedVideo:
    """Resolve one sanitized catalog identity."""

    try:
        return _BY_ID[video_id]
    except KeyError as exc:
        raise AuthorizedVideoError("The validation video identifier is not authorized.") from exc


__all__ = [
    "AUTHORIZED_VIDEOS",
    "authorized_video_for_id",
    "authorized_video_for_path",
    "exact_authorized_filenames",
]
