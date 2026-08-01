from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "hogflow"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def test_framework_types_remain_inside_the_ultralytics_adapter() -> None:
    forbidden = ("cv2", "numpy", "torch", "ultralytics")
    framework_neutral_roots = (
        SOURCE / "detection",
        SOURCE / "tracking",
        SOURCE / "counting",
        SOURCE / "domain",
        SOURCE / "sessions",
        SOURCE / "runtime",
        SOURCE / "presentation",
    )
    for root in framework_neutral_roots:
        for path in root.glob("*.py"):
            imported = _imports(path)
            for name in forbidden:
                assert name not in imported


def test_counting_domain_and_sessions_do_not_depend_on_detector_runtime() -> None:
    for package in ("counting", "domain", "sessions"):
        for path in (SOURCE / package).glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "hogflow.detection" not in source
            assert "PigDetectorConfiguration" not in source


def test_detector_import_is_lazy_and_opens_no_framework_or_artifact() -> None:
    for name in ("cv2", "torch", "ultralytics"):
        sys.modules.pop(name, None)

    module = importlib.reload(importlib.import_module("hogflow.detection"))

    assert module is not None
    assert "cv2" not in sys.modules
    assert "torch" not in sys.modules
    assert "ultralytics" not in sys.modules


def test_model_and_media_artifacts_are_ignored_and_untracked() -> None:
    candidates = (
        "data/models/local.pt",
        "models/local.pth",
        "weights/local.onnx",
        "weights/local.engine",
        "weights/local.ckpt",
        "weights/local.safetensors",
        "data/raw/local-smoke.mp4",
    )
    ignored = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "check-ignore", *candidates],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    tracked = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert ignored.returncode == 0
    assert set(ignored.stdout.splitlines()) == set(candidates)
    forbidden_suffixes = (".pt", ".pth", ".onnx", ".engine", ".ckpt", ".safetensors")
    assert not any(
        line.casefold().endswith(forbidden_suffixes) for line in tracked.stdout.splitlines()
    )


def test_detector_telemetry_retains_no_frame_result_or_error_history() -> None:
    source = (SOURCE / "detection" / "runtime.py").read_text(encoding="utf-8")

    assert "deque(" not in source
    assert "self._history" not in source
    assert "self._errors" not in source
    assert "self._results" not in source
    assert "list[FrameDetections]" not in source
