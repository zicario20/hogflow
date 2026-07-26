from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
CAMERA_ROOT = ROOT / "src" / "hogflow" / "camera"
PRESENTATION_ROOT = ROOT / "src" / "hogflow" / "presentation"


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_camera_orchestration_has_no_tkinter_opencv_or_framework_imports() -> None:
    for path in CAMERA_ROOT.glob("*.py"):
        imports = imported_roots(path)
        assert "cv2" not in imports
        assert "tkinter" not in imports
        assert "supervision" not in imports
        assert "ultralytics" not in imports


def test_presentation_does_not_import_camera_adapters_or_opencv() -> None:
    for path in PRESENTATION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        imports = imported_roots(path)
        assert "cv2" not in imports
        assert "hogflow.adapters" not in source
        assert "hogflow.camera" not in source
        assert "opencv" not in source.lower()


def test_camera_package_import_does_not_load_opencv_or_open_resources() -> None:
    sys.modules.pop("cv2", None)
    module = importlib.reload(importlib.import_module("hogflow.camera"))

    assert module is not None
    assert "cv2" not in sys.modules


def test_one_controller_worker_is_shared_and_no_dock_camera_registry_exists() -> None:
    source = (CAMERA_ROOT / "controller.py").read_text(encoding="utf-8")

    assert 'name="hogflow-shared-counting-pipeline"' in source
    assert "for dock" not in source.lower()
    assert "ThreadPool" not in source
    assert "asyncio" not in source
    assert "multiprocessing" not in source


def test_phase_8_and_phase_7_do_not_import_camera_or_presentation() -> None:
    roots = (
        ROOT / "src" / "hogflow" / "counting",
        ROOT / "src" / "hogflow" / "domain",
        ROOT / "src" / "hogflow" / "sessions",
    )
    for root in roots:
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "hogflow.camera" not in source
            assert "hogflow.presentation" not in source
