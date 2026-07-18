import json
from pathlib import Path

import cv2
import numpy as np

from hogflow.data.inventory import (
    build_parser,
    create_inventory,
    main,
    write_inventory_outputs,
)
from hogflow.data.models import (
    CameraStabilityLabel,
    SuitabilityLabel,
    SuitabilitySettings,
    VideoFileMetadata,
    VideoInspectionSettings,
)


def _write_synthetic_video(path: Path, *, frame_count: int = 20, fps: float = 10.0) -> None:
    width, height = 96, 64
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(8, height, 12):
        for x in range(8, width, 12):
            cv2.circle(frame, (x, y), 2, (200, 200, 200), -1)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height),
    )
    assert writer.isOpened()
    try:
        for _ in range(frame_count):
            writer.write(frame)
    finally:
        writer.release()


def _write_review_sidecar(video: Path, *, all_scene_confirmations: bool = True) -> None:
    value = True if all_scene_confirmations else None
    sidecar = video.with_name(video.name + ".review.json")
    sidecar.write_text(
        json.dumps(
            {
                "authorized_for_project": True,
                "source_type": "synthetic",
                "source_reference": "test-generated clip",
                "license_or_permission_notes": "created locally by the test suite",
                "camera_static_confirmed": True,
                "clear_passage_confirmed": value,
                "predominant_direction_confirmed": value,
                "counting_line_possible": value,
                "intended_use": ["detection", "tracking", "counting"],
                "reviewer_notes": "synthetic metadata test",
            }
        ),
        encoding="utf-8",
    )


def test_empty_inventory_writes_json_csv_and_markdown(tmp_path: Path) -> None:
    input_root = tmp_path / "raw"
    output = tmp_path / "inventory"
    input_root.mkdir()

    inventory = create_inventory(input_root)
    write_inventory_outputs(inventory, output)

    assert inventory.summary.total_files == 0
    payload = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    assert payload["files"] == []
    assert payload["summary"]["total_files"] == 0
    assert (output / "inventory.csv").read_text(encoding="utf-8").startswith("relative_path,")
    markdown = (output / "inventory.md").read_text(encoding="utf-8")
    assert "Clips: 0" in markdown
    assert "publicly viewable" in markdown


def test_synthetic_inventory_reports_metadata_and_manual_counting_candidate(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "raw"
    output = tmp_path / "inventory"
    input_root.mkdir()
    video = input_root / "synthetic.avi"
    _write_synthetic_video(video)
    _write_review_sidecar(video)

    inventory = create_inventory(
        input_root,
        inspection_settings=VideoInspectionSettings(
            sample_frame_count=5,
            minimum_motion_pairs=2,
        ),
        suitability_settings=SuitabilitySettings(
            minimum_detection_duration_seconds=1.0,
            minimum_tracking_duration_seconds=2.0,
        ),
    )
    write_inventory_outputs(inventory, output)

    assert inventory.summary.total_files == 1
    assert inventory.summary.readable_files == 1
    assert inventory.files[0].stability_label is CameraStabilityLabel.LIKELY_STATIC
    assert SuitabilityLabel.COUNTING_CANDIDATE in inventory.files[0].suitability_labels
    payload = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    assert payload["files"][0]["relative_path"] == "synthetic.avi"
    assert payload["files"][0]["stability_label"] == "likely_static"
    assert "counting_candidate" in payload["files"][0]["suitability_labels"]
    assert "synthetic.avi" in (output / "inventory.csv").read_text(encoding="utf-8")
    assert "Counting candidacy is never granted" in (output / "inventory.md").read_text(
        encoding="utf-8"
    )


def test_missing_sidecar_requires_manual_review(tmp_path: Path) -> None:
    input_root = tmp_path / "raw"
    input_root.mkdir()
    video = input_root / "synthetic.avi"
    _write_synthetic_video(video)

    item = create_inventory(input_root).files[0]

    assert "authorization_not_confirmed" in item.validation_errors
    assert item.suitability_labels == (SuitabilityLabel.NEEDS_MANUAL_REVIEW,)


def test_invalid_sidecar_is_reported_without_stopping_other_inventory(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "raw"
    input_root.mkdir()
    video = input_root / "synthetic.avi"
    _write_synthetic_video(video)
    video.with_name(video.name + ".review.json").write_text("{}", encoding="utf-8")

    item = create_inventory(input_root).files[0]

    assert "invalid_review_sidecar" in item.validation_errors
    assert "authorization_not_confirmed" in item.validation_errors


def test_inventory_uses_deterministic_relative_paths_with_fake_reader(tmp_path: Path) -> None:
    input_root = tmp_path / "raw"
    input_root.mkdir()
    (input_root / "b.avi").write_bytes(b"b")
    (input_root / "a.avi").write_bytes(b"a")

    class FakeReader:
        def inspect(self, _path: Path, *, relative_path: Path) -> VideoFileMetadata:
            return VideoFileMetadata(
                relative_path=relative_path.as_posix(),
                file_size_bytes=1,
                container_extension=".avi",
                duration_seconds=10,
                fps=10,
                frame_count=100,
                width=10,
                height=10,
                codec="FAKE",
                readable=True,
            )

    inventory = create_inventory(input_root, metadata_reader=FakeReader())  # type: ignore[arg-type]

    assert tuple(item.relative_path for item in inventory.files) == ("a.avi", "b.avi")


def test_cli_parser_defaults_and_empty_inventory_execution(tmp_path: Path) -> None:
    args = build_parser().parse_args([])
    assert args.input == Path("data/raw")
    assert args.output == Path("data/processed/inventory")

    input_root = tmp_path / "raw"
    output = tmp_path / "output"
    input_root.mkdir()
    result = main(["--input", str(input_root), "--output", str(output)])

    assert result == 0
    assert (output / "inventory.json").exists()
