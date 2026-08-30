from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "annotate_pigs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("annotate_pigs", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load annotate_pigs module specification.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_drag_coordinates_are_normalized_against_native_dimensions() -> None:
    annotate_pigs = _load_module()

    box = annotate_pigs.normalized_box(
        native_width=1320,
        native_height=2868,
        x0=132,
        y0=286,
        x1=660,
        y1=1434,
    )

    assert box == pytest.approx((0.3, 0.299861, 0.4, 0.400279), abs=1e-6)


def test_save_and_delete_round_trip_uses_class_zero_only(tmp_path: Path) -> None:
    annotate_pigs = _load_module()
    label = tmp_path / "frame.txt"

    annotate_pigs.save_boxes(label, [(0.5, 0.5, 0.2, 0.3)])
    assert annotate_pigs.load_boxes(label) == [(0.5, 0.5, 0.2, 0.3)]

    annotate_pigs.save_boxes(label, [])
    assert label.read_text(encoding="utf-8") == ""
    assert annotate_pigs.load_boxes(label) == []


def test_invalid_class_lines_are_rejected(tmp_path: Path) -> None:
    annotate_pigs = _load_module()
    label = tmp_path / "frame.txt"
    label.write_text("1 0.5 0.5 0.2 0.3\n", encoding="utf-8")

    with pytest.raises(ValueError, match="class 0"):
        annotate_pigs.load_boxes(label)


def test_navigation_and_status_map_resume_are_deterministic(tmp_path: Path) -> None:
    annotate_pigs = _load_module()
    extraction_report = tmp_path / "extraction_report.json"
    status_map = tmp_path / "status_map.json"
    image_root = tmp_path / "dataset"
    records = [
        {
            "frame_id": "a" * 24,
            "clip_id": "1" * 24,
            "split": "train",
            "image_relative_path": "images/train/aaaaaaaaaaaaaaaaaaaaaaaa.jpg",
            "width": 1320,
            "height": 2868,
            "checksum_sha256": "f" * 64,
        },
        {
            "frame_id": "b" * 24,
            "clip_id": "1" * 24,
            "split": "train",
            "image_relative_path": "images/train/bbbbbbbbbbbbbbbbbbbbbbbb.jpg",
            "width": 1320,
            "height": 2868,
            "checksum_sha256": "e" * 64,
        },
    ]
    extraction_report.write_text(
        json.dumps({"dataset_id": "phase10-3a-demo", "records": records}),
        encoding="utf-8",
    )
    for record in records:
        image_path = image_root / Path(record["image_relative_path"])
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"synthetic-image")

    workspace = annotate_pigs.AnnotationWorkspace.load(
        dataset_root=image_root,
        extraction_report_path=extraction_report,
        status_map_path=status_map,
    )
    session = annotate_pigs.AnnotationSession(workspace)

    assert session.current_record.frame_id == "a" * 24
    assert session.progress.completed_frames == 0

    session.set_boxes([(0.5, 0.5, 0.3, 0.2)])
    session.save_current(status="annotated")
    session.go_to_next()
    session.save_current(status="verified_empty")

    reloaded = annotate_pigs.AnnotationWorkspace.load(
        dataset_root=image_root,
        extraction_report_path=extraction_report,
        status_map_path=status_map,
    )
    resumed = annotate_pigs.AnnotationSession(reloaded)

    assert resumed.current_record.frame_id == "b" * 24
    assert resumed.progress.completed_frames == 2
    assert resumed.workspace.status_map["frames"]["a" * 24]["bounding_box_count"] == 1
    assert resumed.workspace.status_map["frames"]["b" * 24]["status"] == "verified_empty"


def test_annotation_script_stays_local_to_annotation_dependencies() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8").lower()

    for forbidden in (
        "hogflow.application",
        "hogflow.sessions",
        "hogflow.camera",
        "hogflow.tracking",
        "hogflow.counting",
    ):
        assert forbidden not in source


def test_widget_constructors_use_scalar_internal_padding() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"Frame", "Label", "Button", "Canvas"}:
            continue
        for keyword in node.keywords:
            if keyword.arg not in {"padx", "pady"}:
                continue
            if isinstance(keyword.value, ast.Tuple):
                violations.append(f"{node.func.attr}:{keyword.arg}:{node.lineno}")

    assert not violations
