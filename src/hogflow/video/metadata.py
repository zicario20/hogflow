"""OpenCV-backed bounded metadata and camera-motion inspection for local videos."""

from __future__ import annotations

import importlib
from math import atan2, hypot, isfinite
from pathlib import Path
from statistics import median
from typing import Any

from hogflow.core import DependencyUnavailableError, InputDataError, get_logger
from hogflow.data.models import (
    CameraStabilityLabel,
    VideoFileMetadata,
    VideoInspectionSettings,
)
from hogflow.data.validation import SUPPORTED_VIDEO_EXTENSIONS

LOGGER = get_logger(__name__)


def _load_runtime() -> tuple[Any, Any]:
    """Load optional video-inspection dependencies only when inspection is requested."""

    try:
        return importlib.import_module("cv2"), importlib.import_module("numpy")
    except ImportError as exc:
        raise DependencyUnavailableError(
            "Phase 3 video inspection requires OpenCV and NumPy. "
            'Install the project dependencies with python -m pip install -e ".[dev]".'
        ) from exc


class OpenCVVideoMetadataReader:
    """Inspect one local video using bounded OpenCV decoding.

    The reader samples at most ``VideoInspectionSettings.sample_frame_count``
    positions and never decodes an entire video by default. Camera motion is
    estimated from robust feature correspondences and a global affine transform,
    not from raw pixel differences. The resulting label is a conservative
    inventory aid, not proof that a camera is fixed.
    """

    def __init__(self, settings: VideoInspectionSettings | None = None) -> None:
        self._settings = settings or VideoInspectionSettings()

    @property
    def settings(self) -> VideoInspectionSettings:
        """Return immutable inspection settings."""

        return self._settings

    def inspect(self, path: str | Path, *, relative_path: str | Path) -> VideoFileMetadata:
        """Return bounded metadata and stability evidence for one local file."""

        video_path = Path(path)
        if not video_path.exists():
            raise InputDataError(f"Video file does not exist: {video_path}")
        if not video_path.is_file():
            raise InputDataError(f"Video path is not a file: {video_path}")

        relative = Path(relative_path).as_posix()
        extension = video_path.suffix.lower()
        try:
            file_size = video_path.stat().st_size
        except OSError as exc:
            raise InputDataError(f"Unable to read video file metadata: {video_path}") from exc

        if extension not in SUPPORTED_VIDEO_EXTENSIONS:
            return VideoFileMetadata(
                relative_path=relative,
                file_size_bytes=file_size,
                container_extension=extension or ".unknown",
                duration_seconds=None,
                fps=None,
                frame_count=None,
                width=None,
                height=None,
                codec=None,
                readable=False,
                validation_errors=("unsupported_extension",),
            )

        cv2, np = _load_runtime()
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            capture.release()
            return VideoFileMetadata(
                relative_path=relative,
                file_size_bytes=file_size,
                container_extension=extension,
                duration_seconds=None,
                fps=None,
                frame_count=None,
                width=None,
                height=None,
                codec=None,
                readable=False,
                validation_errors=("file_cannot_be_opened",),
            )

        errors: list[str] = []
        sampled_frames: list[Any] = []
        try:
            width = _positive_int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = _positive_int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            raw_fps = capture.get(cv2.CAP_PROP_FPS)
            raw_frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = _positive_float(raw_fps)
            frame_count = _positive_int(raw_frame_count)
            codec = _decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC))

            if width is None or height is None:
                errors.append("invalid_dimensions")
            if fps is None:
                errors.append("invalid_fps")
            if frame_count is None:
                errors.append("invalid_frame_count")

            duration = frame_count / fps if frame_count is not None and fps is not None else None
            if _is_zero_numeric(raw_frame_count):
                errors.append("zero_duration")
            if duration is not None and (not isfinite(duration) or duration <= 0):
                duration = None
                errors.append("zero_duration")

            sampled_frames, decoding_failed = self._sample_frames(
                capture,
                frame_count=frame_count,
                cv2=cv2,
            )
            if decoding_failed:
                errors.append("bounded_decode_failure")
            dimensions_changed = bool(sampled_frames) and _dimensions_change(sampled_frames)
            if dimensions_changed:
                errors.append("dimensions_changed_during_decoding")
            if sampled_frames and _dimensions_mismatch(
                sampled_frames,
                width=width,
                height=height,
            ):
                errors.append("decoded_dimensions_mismatch")

            if dimensions_changed:
                score, stability = None, CameraStabilityLabel.UNKNOWN
            else:
                score, stability = self._estimate_stability(sampled_frames, cv2=cv2, np=np)
            readable = bool(sampled_frames)
            if not readable and "bounded_decode_failure" not in errors:
                errors.append("bounded_decode_failure")
        finally:
            capture.release()

        return VideoFileMetadata(
            relative_path=relative,
            file_size_bytes=file_size,
            container_extension=extension,
            duration_seconds=duration,
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
            codec=codec,
            readable=readable,
            validation_errors=tuple(dict.fromkeys(errors)),
            sampled_frame_count=len(sampled_frames),
            stability_score_percent=score,
            stability_label=stability,
        )

    def _sample_frames(
        self,
        capture: Any,
        *,
        frame_count: int | None,
        cv2: Any,
    ) -> tuple[list[Any], bool]:
        """Decode a deterministic bounded sample and report any sampled read failure."""

        sample_limit = self._settings.sample_frame_count
        frames: list[Any] = []
        failed = False
        if frame_count is None:
            for _ in range(sample_limit):
                ok, frame = capture.read()
                if not ok or frame is None:
                    failed = True
                    break
                frames.append(frame)
            return frames, failed

        indices = _sample_indices(frame_count, sample_limit)
        for index in indices:
            if not capture.set(cv2.CAP_PROP_POS_FRAMES, index):
                LOGGER.debug("Video backend did not confirm seek to frame %s", index)
            ok, frame = capture.read()
            if not ok or frame is None:
                failed = True
                continue
            frames.append(frame)
        return frames, failed

    def _estimate_stability(
        self,
        frames: list[Any],
        *,
        cv2: Any,
        np: Any,
    ) -> tuple[float | None, CameraStabilityLabel]:
        if len(frames) < 2:
            return None, CameraStabilityLabel.UNKNOWN

        prepared = [self._prepare_grayscale(frame, cv2=cv2) for frame in frames]
        motion_scores: list[float] = []
        for previous, current in zip(prepared, prepared[1:]):
            score = self._global_motion_score(previous, current, cv2=cv2, np=np)
            if score is not None:
                motion_scores.append(score)

        if len(motion_scores) < self._settings.minimum_motion_pairs:
            return None, CameraStabilityLabel.UNKNOWN

        score = float(median(motion_scores))
        if score <= self._settings.static_threshold_percent:
            label = CameraStabilityLabel.LIKELY_STATIC
        elif score >= self._settings.moving_threshold_percent:
            label = CameraStabilityLabel.MOVING_CAMERA
        else:
            label = CameraStabilityLabel.LOW_MOTION
        return score, label

    def _prepare_grayscale(self, frame: Any, *, cv2: Any) -> Any:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]
        largest_dimension = max(height, width)
        if largest_dimension <= self._settings.max_sample_dimension:
            return gray
        scale = self._settings.max_sample_dimension / largest_dimension
        return cv2.resize(
            gray,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    def _global_motion_score(
        self,
        previous: Any,
        current: Any,
        *,
        cv2: Any,
        np: Any,
    ) -> float | None:
        points = cv2.goodFeaturesToTrack(
            previous,
            maxCorners=250,
            qualityLevel=0.01,
            minDistance=7,
            blockSize=7,
        )
        if points is None or len(points) < self._settings.minimum_motion_features:
            return None

        next_points, status, _errors = cv2.calcOpticalFlowPyrLK(
            previous,
            current,
            points,
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        if next_points is None or status is None:
            return None
        valid = status.reshape(-1).astype(bool)
        previous_points = points.reshape(-1, 2)[valid]
        current_points = next_points.reshape(-1, 2)[valid]
        if len(previous_points) < self._settings.minimum_motion_features:
            return None

        affine, inliers = cv2.estimateAffinePartial2D(
            previous_points,
            current_points,
            method=cv2.RANSAC,
            ransacReprojThreshold=2.0,
        )
        if affine is None or inliers is None:
            return None
        inlier_count = int(np.count_nonzero(inliers))
        if inlier_count < self._settings.minimum_motion_features:
            return None

        height, width = previous.shape[:2]
        diagonal = hypot(width, height)
        if diagonal <= 0:
            return None
        translation = hypot(float(affine[0, 2]), float(affine[1, 2]))
        rotation_radians = abs(atan2(float(affine[1, 0]), float(affine[0, 0])))
        rotational_displacement = rotation_radians * diagonal / 2.0
        return 100.0 * (translation + rotational_displacement) / diagonal


def _positive_float(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if isfinite(numeric) and numeric > 0 else None


def _positive_int(value: object) -> int | None:
    numeric = _positive_float(value)
    if numeric is None:
        return None
    rounded = int(round(numeric))
    return rounded if rounded > 0 else None


def _is_zero_numeric(value: object) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(numeric) and numeric == 0


def _decode_fourcc(value: object) -> str | None:
    numeric = _positive_int(value)
    if numeric is None:
        return None
    decoded = "".join(chr((numeric >> (8 * offset)) & 0xFF) for offset in range(4))
    cleaned = "".join(character for character in decoded if character.isprintable()).strip()
    return cleaned or None


def _sample_indices(frame_count: int, sample_limit: int) -> tuple[int, ...]:
    sample_count = min(frame_count, sample_limit)
    if sample_count <= 1:
        return (0,)
    last_index = frame_count - 1
    return tuple(
        sorted(
            {round(position * last_index / (sample_count - 1)) for position in range(sample_count)}
        )
    )


def _dimensions_change(frames: list[Any]) -> bool:
    observed = {(int(frame.shape[1]), int(frame.shape[0])) for frame in frames}
    return len(observed) > 1


def _dimensions_mismatch(
    frames: list[Any],
    *,
    width: int | None,
    height: int | None,
) -> bool:
    if width is None or height is None:
        return False
    observed = {(int(frame.shape[1]), int(frame.shape[0])) for frame in frames}
    return len(observed) == 1 and observed != {(width, height)}
