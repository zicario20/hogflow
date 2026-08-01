from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUNTIME_ROOT = ROOT / "src" / "hogflow" / "runtime"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_runtime_foundation_has_no_ui_cv_storage_network_or_async_dependency() -> None:
    forbidden = (
        "tkinter",
        "cv2",
        "supervision",
        "ultralytics",
        "hogflow.presentation",
        "hogflow.storage",
        "asyncio",
        "multiprocessing",
        "requests",
        "socket",
    )
    for path in RUNTIME_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        imported = imports(path)
        for name in forbidden:
            assert name not in imported
            assert f"from {name}" not in source
        assert "Thread(" not in source


def test_runtime_health_uses_one_bounded_warning_deque_and_no_frame_history() -> None:
    source = (RUNTIME_ROOT / "health.py").read_text(encoding="utf-8")

    assert "deque(" in source
    assert "maxlen=configuration.warning_capacity" in source
    assert "PreviewFrame" not in source
    assert "FramePacket" not in source
    assert "Queue(" not in source
    assert "self._history" not in source


def test_lower_layers_do_not_depend_on_production_runtime() -> None:
    for package in (
        "core",
        "counting",
        "domain",
        "sessions",
        "streaming",
        "detection",
        "tracking",
        "camera",
        "application",
        "presentation",
    ):
        for path in (ROOT / "src" / "hogflow" / package).glob("*.py"):
            assert "hogflow.runtime" not in path.read_text(encoding="utf-8")


def test_runtime_import_is_lazy_and_does_not_load_opencv_or_start_threads() -> None:
    before_threads = __import__("threading").active_count()
    sys.modules.pop("cv2", None)

    module = importlib.reload(importlib.import_module("hogflow.runtime"))

    assert module is not None
    assert "cv2" not in sys.modules
    assert __import__("threading").active_count() == before_threads


def test_phase_10_1_does_not_add_detector_storage_or_phase_10_2_code() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in RUNTIME_ROOT.glob("*.py"))

    assert "YOLO" not in source
    assert "sqlite3" not in source
    assert "Phase 10.2" not in source
    assert "model.train" not in source
