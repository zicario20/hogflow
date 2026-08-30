"""Exact provisional authorization for the two local Phase 10.3A demo videos."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from hogflow.core import InputDataError

PROVISIONAL_MANIFEST_FORMAT_VERSION = 1
EXPECTED_VIDEO_IDS = ("demo_video_a", "demo_video_b")
_EXPECTED_ROLES = {
    "demo_video_a": "training_development",
    "demo_video_b": "independent_validation",
}


class ProvisionalVideoRole(str, Enum):
    """Authorized purpose for the provisional Phase 10.3A demo videos."""

    TRAINING_DEVELOPMENT = "training_development"
    INDEPENDENT_VALIDATION = "independent_validation"


@dataclass(frozen=True, slots=True)
class AuthorizedProvisionalVideo:
    """Sanitized identity for one explicitly authorized local video."""

    video_id: str
    basename: str
    role: ProvisionalVideoRole

    def __post_init__(self) -> None:
        if self.video_id not in EXPECTED_VIDEO_IDS:
            raise InputDataError("Provisional video identifier is not authorized.")
        if not isinstance(self.role, ProvisionalVideoRole):
            raise InputDataError("Provisional video role must be explicit.")
        if _EXPECTED_ROLES[self.video_id] != self.role.value:
            raise InputDataError("Provisional video role does not match the authorized identifier.")
        if not isinstance(self.basename, str) or not self.basename or self.basename != self.basename.strip():
            raise InputDataError("Provisional video basename must be non-empty sanitized text.")
        candidate = Path(self.basename)
        if (
            candidate.name != self.basename
            or candidate.suffix.lower() != ".mp4"
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise InputDataError("Provisional video basename must be one local .mp4 filename.")

    def resolve(self, raw_root: str | Path) -> Path:
        """Resolve the basename against one explicit raw-media root."""

        return Path(raw_root) / self.basename


@dataclass(frozen=True, slots=True)
class ProvisionalVideoManifest:
    """Exactly two explicitly authorized provisional videos."""

    videos: tuple[AuthorizedProvisionalVideo, AuthorizedProvisionalVideo]

    def __post_init__(self) -> None:
        if not isinstance(self.videos, tuple) or len(self.videos) != 2:
            raise InputDataError("Provisional authorization must contain exactly two videos.")
        if tuple(video.video_id for video in self.videos) != EXPECTED_VIDEO_IDS:
            raise InputDataError(
                "Provisional videos must be demo_video_a followed by demo_video_b."
            )
        if len({video.basename.casefold() for video in self.videos}) != 2:
            raise InputDataError("Provisional video basenames must be unique.")

    @classmethod
    def for_basenames(
        cls, training_basename: str, validation_basename: str
    ) -> ProvisionalVideoManifest:
        return cls(
            videos=(
                AuthorizedProvisionalVideo(
                    video_id="demo_video_a",
                    basename=training_basename,
                    role=ProvisionalVideoRole.TRAINING_DEVELOPMENT,
                ),
                AuthorizedProvisionalVideo(
                    video_id="demo_video_b",
                    basename=validation_basename,
                    role=ProvisionalVideoRole.INDEPENDENT_VALIDATION,
                ),
            )
        )


def load_provisional_video_manifest(
    path: str | Path, raw_root: str | Path
) -> ProvisionalVideoManifest:
    """Load the exact local two-video authorization without rediscovering media."""

    payload = _load_json_object(Path(path), description="Provisional authorization manifest")
    if set(payload) != {"format_version", "videos"}:
        raise InputDataError(
            "Provisional authorization manifest must contain exactly format_version and videos."
        )
    if payload["format_version"] != PROVISIONAL_MANIFEST_FORMAT_VERSION:
        raise InputDataError("Unsupported provisional authorization manifest format version.")
    records = payload.get("videos")
    if not isinstance(records, list) or len(records) != 2:
        raise InputDataError("Provisional authorization must contain exactly two videos.")
    root = Path(raw_root)
    videos = tuple(_parse_record(item, root) for item in records)
    manifest = ProvisionalVideoManifest(videos=videos)  # type: ignore[arg-type]
    _verify_local_media(manifest, root)
    return manifest


def write_provisional_video_manifest(manifest: ProvisionalVideoManifest, path: str | Path) -> Path:
    """Write one explicit local-only provisional authorization file."""

    if not isinstance(manifest, ProvisionalVideoManifest):
        raise InputDataError("manifest must be a ProvisionalVideoManifest.")
    destination = Path(path)
    repository_root = _repository_root(destination.parent)
    if repository_root is not None:
        _require_manifest_destination(destination, repository_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": PROVISIONAL_MANIFEST_FORMAT_VERSION,
        "videos": [
            {
                "video_id": video.video_id,
                "basename": video.basename,
                "role": video.role.value,
            }
            for video in manifest.videos
        ],
    }
    try:
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise InputDataError("Unable to write provisional authorization manifest.") from exc
    return destination


def _parse_record(record: object, raw_root: Path) -> AuthorizedProvisionalVideo:
    if not isinstance(record, dict):
        raise InputDataError("Provisional authorization records must be JSON objects.")
    if set(record) != {"video_id", "basename", "role"}:
        raise InputDataError(
            "Provisional authorization records must contain exactly video_id, basename, and role."
        )
    video = AuthorizedProvisionalVideo(
        video_id=record["video_id"],
        basename=record["basename"],
        role=ProvisionalVideoRole(record["role"]),
    )
    candidate = video.resolve(raw_root)
    try:
        candidate.relative_to(raw_root)
    except ValueError as exc:
        raise InputDataError("Provisional video basename escapes the approved raw root.") from exc
    return video


def _verify_local_media(manifest: ProvisionalVideoManifest, raw_root: Path) -> None:
    if not raw_root.exists():
        raise InputDataError("Approved raw-media root does not exist.")
    if not raw_root.is_dir():
        raise InputDataError("Approved raw-media root must be a directory.")
    repository_root = _repository_root(raw_root)
    for video in manifest.videos:
        candidate = video.resolve(raw_root)
        if not candidate.exists() or not candidate.is_file():
            raise InputDataError(f"Authorized provisional video {video.video_id} is missing.")
        if repository_root is not None:
            _require_ignored_untracked(candidate, repository_root)


def _require_ignored_untracked(path: Path, repository_root: Path) -> None:
    relative = path.relative_to(repository_root).as_posix()
    if not _git_status(repository_root, "check-ignore", relative):
        raise InputDataError("Authorized provisional videos must remain ignored and untracked.")
    if _git_status(repository_root, "ls-files", "--error-unmatch", relative):
        raise InputDataError("Authorized provisional videos must remain ignored and untracked.")


def _require_manifest_destination(path: Path, repository_root: Path) -> None:
    relative = path.relative_to(repository_root).as_posix()
    if not _git_status(repository_root, "check-ignore", relative):
        raise InputDataError(
            "Provisional authorization manifests must remain in an ignored and untracked local root."
        )
    if _git_status(repository_root, "ls-files", "--error-unmatch", relative):
        raise InputDataError(
            "Provisional authorization manifests must remain in an ignored and untracked local root."
        )


def _git_status(repository_root: Path, *arguments: str) -> bool:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repository_root.as_posix()}", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _repository_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


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


__all__ = [
    "AuthorizedProvisionalVideo",
    "EXPECTED_VIDEO_IDS",
    "PROVISIONAL_MANIFEST_FORMAT_VERSION",
    "ProvisionalVideoManifest",
    "ProvisionalVideoRole",
    "load_provisional_video_manifest",
    "write_provisional_video_manifest",
]
