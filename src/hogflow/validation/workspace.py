"""Local-only artifact verification for the Phase 10.3 validation gate."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hogflow.data import VideoFileMetadata
from hogflow.data.validation import load_review_sidecar, review_sidecar_path
from hogflow.validation.catalog import AUTHORIZED_VIDEOS, exact_authorized_filenames
from hogflow.validation.errors import AuthorizedVideoError, ModelAvailabilityError
from hogflow.validation.models import (
    AuthorizedVideo,
    EvidenceValue,
    ModelAvailability,
    ModelGateState,
    SanitizedVideoMetadata,
)
from hogflow.validation.ports import VideoMetadataInspector

_MODEL_EXTENSIONS = frozenset({".pt", ".onnx", ".engine"})
_MODEL_ROOTS = ("data/models", "models", "weights")


@dataclass(frozen=True, slots=True)
class InspectedAuthorizedVideo:
    """Path-free inspection evidence; local paths remain inside the workspace."""

    video: AuthorizedVideo
    metadata: SanitizedVideoMetadata
    sidecar_present: bool
    sidecar_authorized: bool | None
    sidecar_intended_use: tuple[str, ...]
    classification_source: str


class GitRepositoryPolicy:
    """Query ignore/tracked status without changing repository state."""

    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root.resolve()

    def is_ignored(self, path: Path) -> bool:
        relative = self._relative(path)
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={self._root.as_posix()}",
                "check-ignore",
                "--quiet",
                "--",
                relative.as_posix(),
            ],
            cwd=self._root,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def is_tracked(self, path: Path) -> bool:
        relative = self._relative(path)
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={self._root.as_posix()}",
                "ls-files",
                "--error-unmatch",
                "--",
                relative.as_posix(),
            ],
            cwd=self._root,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def _relative(self, path: Path) -> Path:
        try:
            return path.resolve().relative_to(self._root)
        except ValueError as exc:
            raise ModelAvailabilityError(
                "Local validation artifacts must remain in the repository workspace."
            ) from exc


class LocalValidationWorkspace:
    """Verify only authorized media and approved ignored local model roots."""

    def __init__(
        self,
        repository_root: str | Path,
        metadata_inspector: VideoMetadataInspector,
        *,
        git_policy: GitRepositoryPolicy | None = None,
    ) -> None:
        self._root = Path(repository_root).resolve()
        self._raw = self._root / "data" / "raw"
        self._metadata_inspector = metadata_inspector
        self._git = git_policy or GitRepositoryPolicy(self._root)
        self._video_paths: dict[str, Path] = {}
        self._selected_model_path: Path | None = None

    def inspect_authorized_videos(self) -> tuple[InspectedAuthorizedVideo, ...]:
        """Inspect exact files in order and retain no decoded frame history."""

        inspected: list[InspectedAuthorizedVideo] = []
        for filename, video in zip(exact_authorized_filenames(), AUTHORIZED_VIDEOS, strict=True):
            path = self._raw / filename
            if not path.exists() or not path.is_file():
                raise AuthorizedVideoError(f"Authorized local video {video.video_id} is missing.")
            if self._git.is_tracked(path) or not self._git.is_ignored(path):
                raise AuthorizedVideoError(
                    f"Authorized local video {video.video_id} must remain ignored and untracked."
                )
            metadata = self._metadata_inspector.inspect(path, relative_path=f"data/raw/{filename}")
            sidecar = review_sidecar_path(path)
            sidecar_present = sidecar.exists() and sidecar.is_file()
            sidecar_authorized: bool | None = None
            sidecar_intended_use: tuple[str, ...] = ()
            classification_source = "phase_10_3_authorization"
            if sidecar_present:
                review = load_review_sidecar(sidecar)
                sidecar_authorized = review.authorized_for_project
                sidecar_intended_use = review.intended_use
                if not sidecar_authorized:
                    raise AuthorizedVideoError(
                        f"Review metadata does not authorize local video {video.video_id}."
                    )
                classification_source = "phase_3_review_sidecar"
            self._video_paths[video.video_id] = path
            inspected.append(
                InspectedAuthorizedVideo(
                    video=video,
                    metadata=_sanitize_metadata(metadata),
                    sidecar_present=sidecar_present,
                    sidecar_authorized=sidecar_authorized,
                    sidecar_intended_use=sidecar_intended_use,
                    classification_source=classification_source,
                )
            )
        return tuple(inspected)

    def locate_model(self, explicit_model_path: str | Path | None = None) -> ModelAvailability:
        """Apply the compatible-format, ignored, untracked, approved-root gate."""

        candidates: list[Path]
        if explicit_model_path is not None:
            candidate = (self._root / Path(explicit_model_path)).resolve()
            candidates = [candidate]
        else:
            candidates = _discover_at_most_two_models(self._root)
        if not candidates:
            self._selected_model_path = None
            return ModelAvailability(ModelGateState.MISSING, 0)
        approved: list[Path] = []
        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                raise ModelAvailabilityError(
                    "The explicitly configured local model artifact is missing."
                )
            if candidate.suffix.casefold() not in _MODEL_EXTENSIONS:
                raise ModelAvailabilityError("The local model artifact format is unsupported.")
            if not any(_is_within(candidate, self._root / root) for root in _MODEL_ROOTS):
                raise ModelAvailabilityError(
                    "The local model artifact is outside approved model locations."
                )
            if self._git.is_tracked(candidate) or not self._git.is_ignored(candidate):
                return ModelAvailability(
                    ModelGateState.REJECTED,
                    len(candidates),
                    reason_code="model_artifact_not_local_only",
                )
            approved.append(candidate)
        if len(approved) != 1:
            self._selected_model_path = None
            return ModelAvailability(
                ModelGateState.AMBIGUOUS,
                len(approved),
                reason_code="multiple_compatible_models_require_selection",
            )
        selected = approved[0]
        self._selected_model_path = selected
        digest = _bounded_sha256(selected)
        return ModelAvailability(
            state=ModelGateState.AVAILABLE,
            compatible_artifact_count=1,
            sanitized_model_identity=f"local_{selected.suffix.casefold().lstrip('.')}_model",
            model_format=selected.suffix.casefold().lstrip("."),
            artifact_fingerprint=digest,
            reason_code="compatible_local_model_available",
        )

    def video_path(self, video_id: str) -> Path:
        """Return an internal composition input after successful inspection."""

        try:
            return self._video_paths[video_id]
        except KeyError as exc:
            raise AuthorizedVideoError(
                "Authorized videos must be inspected before execution."
            ) from exc

    def model_path(self) -> Path:
        """Return the selected internal model path after an available gate."""

        if self._selected_model_path is None:
            raise ModelAvailabilityError("No compatible local model passed the artifact gate.")
        return self._selected_model_path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _bounded_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_at_most_two_models(root: Path) -> list[Path]:
    """Prove zero/one/multiple availability without retaining an unbounded list."""

    discovered: list[Path] = []
    for relative_root in _MODEL_ROOTS:
        model_root = root / relative_root
        if not model_root.is_dir():
            continue
        for current, directories, filenames in os.walk(model_root):
            directories.sort(key=str.casefold)
            for filename in sorted(filenames, key=str.casefold):
                candidate = Path(current) / filename
                if candidate.suffix.casefold() not in _MODEL_EXTENSIONS:
                    continue
                discovered.append(candidate)
                if len(discovered) == 2:
                    return discovered
    return discovered


def _value(value: object, unit: str | None = None) -> EvidenceValue:
    return EvidenceValue.measured(value, unit) if value is not None else EvidenceValue.unknown(unit)


def _sanitize_metadata(metadata: VideoFileMetadata) -> SanitizedVideoMetadata:
    return SanitizedVideoMetadata(
        container_format=_value(metadata.container_extension.removeprefix(".")),
        file_size_bytes=_value(metadata.file_size_bytes, "bytes"),
        duration_seconds=_value(metadata.duration_seconds, "seconds"),
        nominal_fps=_value(metadata.fps, "fps"),
        frame_count=_value(metadata.frame_count, "frames"),
        frame_width=_value(metadata.width, "pixels"),
        frame_height=_value(metadata.height, "pixels"),
        readable=_value(metadata.readable),
        stability_label=_value(metadata.stability_label.value),
    )


__all__ = [
    "GitRepositoryPolicy",
    "InspectedAuthorizedVideo",
    "LocalValidationWorkspace",
]
