"""Framework-independent discovery, sidecar, manifest, and suitability validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hogflow.core import InputDataError
from hogflow.data.models import (
    CameraStabilityLabel,
    ClipManifestEntry,
    ManualReviewMetadata,
    SuitabilityLabel,
    SuitabilitySettings,
    VideoFileMetadata,
)

SUPPORTED_VIDEO_EXTENSIONS = frozenset({".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"})
REVIEW_SIDECAR_SUFFIX = ".review.json"

_GENERATED_DIRECTORY_NAMES = frozenset({"frames", "interim", "processed", "thumbnails"})
_GENERATED_NAME_MARKERS = (".partial.", ".thumbnail.", ".tmp.")
_SIDECAR_FIELDS = frozenset(
    {
        "authorized_for_project",
        "source_type",
        "source_reference",
        "license_or_permission_notes",
        "camera_static_confirmed",
        "clear_passage_confirmed",
        "predominant_direction_confirmed",
        "counting_line_possible",
        "intended_use",
        "reviewer_notes",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "original_source_reference",
        "clip_filename",
        "start_time_seconds",
        "end_time_seconds",
        "reason_selected",
        "camera_appears_static",
        "notes",
    }
)


def discover_video_files(
    root: str | Path,
    *,
    supported_extensions: frozenset[str] = SUPPORTED_VIDEO_EXTENSIONS,
) -> tuple[Path, ...]:
    """Return deterministic relative video paths beneath ``root``.

    Hidden paths, generated-data directories, partial files, and unsupported
    extensions are ignored. An existing empty directory returns an empty tuple.
    """

    root_path = Path(root)
    if not root_path.exists():
        raise InputDataError(f"Dataset root does not exist: {root_path}")
    if not root_path.is_dir():
        raise InputDataError(f"Dataset root is not a directory: {root_path}")

    normalized_extensions = frozenset(extension.lower() for extension in supported_extensions)
    discovered: list[Path] = []
    for candidate in root_path.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root_path)
        lowered_parts = tuple(part.lower() for part in relative.parts)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if any(part in _GENERATED_DIRECTORY_NAMES for part in lowered_parts[:-1]):
            continue
        lowered_name = candidate.name.lower()
        if candidate.name.startswith("~") or any(
            marker in lowered_name for marker in _GENERATED_NAME_MARKERS
        ):
            continue
        if candidate.suffix.lower() not in normalized_extensions:
            continue
        discovered.append(relative)

    return tuple(
        sorted(
            discovered,
            key=lambda path: (path.as_posix().casefold(), path.as_posix()),
        )
    )


def review_sidecar_path(video_path: str | Path) -> Path:
    """Return the adjacent Phase 3 JSON review-sidecar path for a video."""

    path = Path(video_path)
    return path.with_name(path.name + REVIEW_SIDECAR_SUFFIX)


def load_review_sidecar(path: str | Path) -> ManualReviewMetadata:
    """Parse and validate a local manual-review JSON sidecar."""

    payload = _load_json_object(Path(path), description="Review sidecar")
    missing = _SIDECAR_FIELDS - payload.keys()
    extra = payload.keys() - _SIDECAR_FIELDS
    if missing:
        raise InputDataError("Review sidecar is missing fields: " + ", ".join(sorted(missing)))
    if extra:
        raise InputDataError("Review sidecar has unsupported fields: " + ", ".join(sorted(extra)))
    intended_use = payload["intended_use"]
    if not isinstance(intended_use, list):
        raise InputDataError("Review sidecar intended_use must be a JSON array.")
    return ManualReviewMetadata(
        authorized_for_project=payload["authorized_for_project"],
        source_type=payload["source_type"],
        source_reference=payload["source_reference"],
        license_or_permission_notes=payload["license_or_permission_notes"],
        camera_static_confirmed=payload["camera_static_confirmed"],
        clear_passage_confirmed=payload["clear_passage_confirmed"],
        predominant_direction_confirmed=payload["predominant_direction_confirmed"],
        counting_line_possible=payload["counting_line_possible"],
        intended_use=tuple(intended_use),
        reviewer_notes=payload["reviewer_notes"],
    )


def load_clip_manifest(path: str | Path) -> tuple[ClipManifestEntry, ...]:
    """Parse an optional JSON manifest describing manually cut clip boundaries."""

    payload = _load_json_object(Path(path), description="Clip manifest")
    if set(payload) != {"clips"}:
        raise InputDataError("Clip manifest must contain exactly one top-level 'clips' field.")
    clips = payload["clips"]
    if not isinstance(clips, list):
        raise InputDataError("Clip manifest clips must be a JSON array.")
    entries: list[ClipManifestEntry] = []
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict):
            raise InputDataError(f"Clip manifest entry {index} must be a JSON object.")
        missing = _MANIFEST_FIELDS - clip.keys()
        extra = clip.keys() - _MANIFEST_FIELDS
        if missing:
            raise InputDataError(
                f"Clip manifest entry {index} is missing fields: " + ", ".join(sorted(missing))
            )
        if extra:
            raise InputDataError(
                f"Clip manifest entry {index} has unsupported fields: " + ", ".join(sorted(extra))
            )
        entries.append(
            ClipManifestEntry(
                original_source_reference=clip["original_source_reference"],
                clip_filename=clip["clip_filename"],
                start_time_seconds=clip["start_time_seconds"],
                end_time_seconds=clip["end_time_seconds"],
                reason_selected=clip["reason_selected"],
                camera_appears_static=clip["camera_appears_static"],
                notes=clip["notes"],
            )
        )
    return tuple(entries)


def classify_suitability(
    metadata: VideoFileMetadata,
    review: ManualReviewMetadata | None,
    settings: SuitabilitySettings,
) -> tuple[SuitabilityLabel, ...]:
    """Return conservative inventory labels without making quality claims.

    Authorization is required before any use-candidate label is granted.
    Counting candidacy additionally requires all four human scene confirmations;
    metadata and automatic stability estimation alone can never grant it.
    """

    labels: list[SuitabilityLabel] = []
    authorized = review is not None and review.authorized_for_project
    valid_technical_metadata = (
        metadata.readable
        and not metadata.validation_errors
        and metadata.width is not None
        and metadata.width > 0
        and metadata.height is not None
        and metadata.height > 0
        and metadata.fps is not None
        and metadata.fps > 0
        and metadata.frame_count is not None
        and metadata.frame_count > 0
        and metadata.duration_seconds is not None
        and metadata.duration_seconds >= settings.minimum_detection_duration_seconds
    )
    detection_candidate = authorized and valid_technical_metadata
    if detection_candidate:
        labels.append(SuitabilityLabel.DETECTION_CANDIDATE)

    manually_static = review.camera_static_confirmed if review is not None else None
    stability_allows_tracking = manually_static is True or (
        manually_static is not False
        and metadata.stability_label is not CameraStabilityLabel.MOVING_CAMERA
    )
    tracking_candidate = (
        detection_candidate
        and metadata.duration_seconds is not None
        and metadata.duration_seconds >= settings.minimum_tracking_duration_seconds
        and stability_allows_tracking
    )
    if tracking_candidate:
        labels.append(SuitabilityLabel.TRACKING_CANDIDATE)

    counting_confirmations = (
        review is not None
        and review.camera_static_confirmed is True
        and review.clear_passage_confirmed is True
        and review.predominant_direction_confirmed is True
        and review.counting_line_possible is True
    )
    if tracking_candidate and counting_confirmations:
        labels.append(SuitabilityLabel.COUNTING_CANDIDATE)

    difficult_camera_condition = metadata.stability_label is CameraStabilityLabel.MOVING_CAMERA or (
        review is not None and review.camera_static_confirmed is False
    )
    if authorized and metadata.readable and difficult_camera_condition:
        labels.append(SuitabilityLabel.STRESS_TEST_CANDIDATE)

    needs_review = (
        not authorized
        or not metadata.readable
        or not detection_candidate
        or bool(metadata.validation_errors)
        or not counting_confirmations
        or metadata.stability_label is CameraStabilityLabel.UNKNOWN
    )
    if needs_review:
        labels.append(SuitabilityLabel.NEEDS_MANUAL_REVIEW)
    return tuple(labels)


def _load_json_object(path: Path, *, description: str) -> dict[str, Any]:
    if not path.exists():
        raise InputDataError(f"{description} does not exist: {path}")
    if not path.is_file():
        raise InputDataError(f"{description} path is not a file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError(f"{description} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise InputDataError(f"{description} must contain one JSON object.")
    return payload
