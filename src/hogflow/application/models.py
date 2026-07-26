"""Immutable commands used by the Phase 9.1 operator workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hogflow.application.errors import OperatorInputError
from hogflow.domain import DockId, PigType, TruckOperation, UnloadingSession


@dataclass(frozen=True, slots=True)
class PlannedSession:
    """Operator-entered definition for one planned unloading session."""

    session_id: str
    sequence_number: int
    pig_type: PigType
    expected_count: int | None = None

    def __post_init__(self) -> None:
        self.to_domain()

    def to_domain(self) -> UnloadingSession:
        """Build the validated immutable Phase 8.1 session value."""

        return UnloadingSession(
            session_id=self.session_id,
            sequence_number=self.sequence_number,
            pig_type=self.pig_type,
            expected_count=self.expected_count,
        )


@dataclass(frozen=True, slots=True)
class RegisterTruckCommand:
    """Complete planned truck definition submitted by the operator UI."""

    dock_id: DockId
    operation_id: str
    sessions: tuple[PlannedSession, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.dock_id, DockId):
            DockId.parse(self.dock_id)
        if not isinstance(self.sessions, tuple) or not self.sessions:
            raise OperatorInputError("Operator truck registration requires at least one session.")
        if not all(isinstance(item, PlannedSession) for item in self.sessions):
            raise OperatorInputError(
                "Operator session definitions must be immutable PlannedSession values."
            )
        self.to_operation()

    def to_operation(self) -> TruckOperation:
        """Build one validated Phase 8.1 aggregate without retaining a mutable mirror."""

        operation = TruckOperation(self.operation_id, self.dock_id)
        for session in self.sessions:
            operation = operation.add_session(session.to_domain())
        return operation


class VideoSourceKind(str, Enum):
    """Operator-selectable local source categories."""

    CAMERA = "camera"
    VIDEO_FILE = "video_file"


@dataclass(frozen=True, slots=True, repr=False)
class VideoSourceRequest:
    """Validated operator request whose local file path stays out of repr."""

    kind: VideoSourceKind
    camera_index: int | None = None
    local_file: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, VideoSourceKind):
            raise OperatorInputError("Video source kind must be camera or video file.")
        if self.kind is VideoSourceKind.CAMERA:
            if (
                not isinstance(self.camera_index, int)
                or isinstance(self.camera_index, bool)
                or self.camera_index < 0
                or self.local_file is not None
            ):
                raise OperatorInputError("Camera source requires one non-negative device index.")
        elif (
            self.camera_index is not None
            or not isinstance(self.local_file, Path)
            or not self.local_file.is_file()
        ):
            raise OperatorInputError("Local video source must identify an existing file.")

    @classmethod
    def camera(cls, camera_index: int) -> VideoSourceRequest:
        """Create one local camera request."""

        return cls(VideoSourceKind.CAMERA, camera_index=camera_index)

    @classmethod
    def video_file(cls, path: str | Path) -> VideoSourceRequest:
        """Create one local-file request without retaining it in public output."""

        if not isinstance(path, (str, Path)):
            raise OperatorInputError("Local video source must be a file path.")
        return cls(VideoSourceKind.VIDEO_FILE, local_file=Path(path))

    def __repr__(self) -> str:
        detail = (
            f"camera_index={self.camera_index}"
            if self.kind is VideoSourceKind.CAMERA
            else "local_file=<protected>"
        )
        return f"VideoSourceRequest(kind={self.kind.value!r}, {detail})"


__all__ = [
    "PlannedSession",
    "RegisterTruckCommand",
    "VideoSourceKind",
    "VideoSourceRequest",
]
