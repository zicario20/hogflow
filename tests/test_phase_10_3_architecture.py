from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "hogflow"
VALIDATION = SOURCE / "validation"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def test_validation_package_is_framework_ui_worker_and_storage_independent() -> None:
    forbidden = (
        "cv2",
        "numpy",
        "supervision",
        "torch",
        "ultralytics",
        "tkinter",
        "threading",
        "asyncio",
        "sqlite3",
    )
    violations = []
    for path in VALIDATION.glob("*.py"):
        imported = _imports(path)
        for name in forbidden:
            if name in imported:
                violations.append(f"{path.name}: {name}")
    assert not violations


def test_validation_models_are_path_free() -> None:
    source = (VALIDATION / "models.py").read_text(encoding="utf-8").lower()
    for token in ("from pathlib", "import pathlib", "path:", "video_path", "model_path"):
        assert token not in source


def test_phase_10_3_does_not_modify_counting_or_phase_8_rules() -> None:
    validation_sources = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in VALIDATION.glob("*.py")
    )
    for token in (
        "counted_tracker_ids.add",
        "lifecycle_directional_count +=",
        "actual_count =",
        "truckoperation(",
        "sharecountinglane(",
    ):
        assert token not in validation_sources


def test_validation_state_has_no_unbounded_result_or_frame_history() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in VALIDATION.glob("*.py")
    )
    for token in (
        "deque(",
        "frame_history",
        "detection_history",
        "tracking_history",
        "crossing_history",
        "error_history",
        "raw_frames",
    ):
        assert token not in sources
    assert "_discover_at_most_two_models" in sources


def test_validation_package_import_is_lazy_and_opens_no_cv_framework() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import hogflow.validation; "
                "blocked = {'cv2', 'numpy', 'torch', 'ultralytics'} & set(sys.modules); "
                "raise SystemExit(1 if blocked else 0)"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_phase_10_3_cli_is_the_only_local_composition_boundary() -> None:
    cli = (SOURCE / "video" / "real_world_validation_cli.py").read_text(encoding="utf-8")
    assert "hogflow.video.metadata" in cli
    assert "hogflow.validation" in cli
    assert "tkinter" not in cli.lower()
    assert "threading" not in cli.lower()
    assert "asyncio" not in cli.lower()


def test_local_outputs_models_and_media_remain_ignored() -> None:
    candidates = (
        "data/evaluation/phase10_3/report.json",
        "data/runs/phase10_3/run.json",
        "data/metrics/phase10_3/metrics.json",
        "data/models/local.pt",
        "models/local.onnx",
        "weights/local.engine",
        "data/raw/local.mp4",
    )
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "check-ignore", *candidates],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert set(result.stdout.splitlines()) == set(candidates)


def test_no_model_or_media_artifact_is_tracked() -> None:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    forbidden = (".pt", ".onnx", ".engine", ".mp4", ".mov", ".avi", ".mkv")
    assert not any(path.casefold().endswith(forbidden) for path in result.stdout.splitlines())
