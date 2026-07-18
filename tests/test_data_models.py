import ast
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from hogflow.core import ConfigurationError, InputDataError
from hogflow.data.models import (
    CameraStabilityLabel,
    DatasetInventorySummary,
    ManualReviewMetadata,
    SuitabilityLabel,
    SuitabilitySettings,
    VideoFileMetadata,
    VideoInspectionSettings,
)

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"


def _review() -> ManualReviewMetadata:
    return ManualReviewMetadata(
        authorized_for_project=True,
        source_type="synthetic",
        source_reference="local synthetic fixture",
        license_or_permission_notes="created by the test suite",
        camera_static_confirmed=True,
        clear_passage_confirmed=True,
        predominant_direction_confirmed=True,
        counting_line_possible=True,
        intended_use=("detection", "tracking", "counting"),
        reviewer_notes="",
    )


def test_video_metadata_is_frozen_and_slotted() -> None:
    metadata = VideoFileMetadata(
        relative_path="nested/clip.avi",
        file_size_bytes=12,
        container_extension=".avi",
        duration_seconds=4.0,
        fps=10.0,
        frame_count=40,
        width=64,
        height=48,
        codec="MJPG",
        readable=True,
        stability_label=CameraStabilityLabel.LIKELY_STATIC,
        suitability_labels=(SuitabilityLabel.DETECTION_CANDIDATE,),
        review_metadata=_review(),
    )

    with pytest.raises(FrozenInstanceError):
        metadata.width = 100  # type: ignore[misc]

    assert not hasattr(metadata, "__dict__")


def test_video_metadata_rejects_absolute_or_parent_paths() -> None:
    common = {
        "file_size_bytes": 0,
        "container_extension": ".avi",
        "duration_seconds": None,
        "fps": None,
        "frame_count": None,
        "width": None,
        "height": None,
        "codec": None,
        "readable": False,
    }
    with pytest.raises(InputDataError):
        VideoFileMetadata(relative_path="../clip.avi", **common)
    with pytest.raises(InputDataError):
        VideoFileMetadata(relative_path="C:/private/clip.avi", **common)


def test_summary_requires_readable_totals_to_match() -> None:
    with pytest.raises(InputDataError):
        DatasetInventorySummary(
            total_files=2,
            readable_files=2,
            unreadable_files=1,
            total_duration_seconds=0,
            total_size_bytes=0,
            resolution_distribution=(),
            stability_counts=(),
            suitability_counts=(),
        )


def test_inspection_and_suitability_settings_validate_thresholds() -> None:
    with pytest.raises(ConfigurationError):
        VideoInspectionSettings(static_threshold_percent=1.0, moving_threshold_percent=0.5)
    with pytest.raises(ConfigurationError):
        VideoInspectionSettings(sample_frame_count=0)
    with pytest.raises(ConfigurationError):
        SuitabilitySettings(
            minimum_detection_duration_seconds=10,
            minimum_tracking_duration_seconds=5,
        )


def test_public_data_models_have_no_cv_framework_imports() -> None:
    source = SOURCE_ROOT / "hogflow" / "data" / "models.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    forbidden = {"cv2", "numpy", "torch", "ultralytics", "supervision"}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", maxsplit=1)[0])

    assert imported.isdisjoint(forbidden)


def test_importing_data_models_does_not_import_opencv_or_numpy() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import hogflow.data.models; "
                "assert 'cv2' not in sys.modules; assert 'numpy' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
