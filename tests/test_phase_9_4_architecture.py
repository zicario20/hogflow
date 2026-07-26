from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
CAMERA_ROOT = ROOT / "src" / "hogflow" / "camera"
PRESENTATION_ROOT = ROOT / "src" / "hogflow" / "presentation"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_preview_channel_is_framework_neutral_and_uses_one_slot() -> None:
    path = CAMERA_ROOT / "preview_channel.py"
    source = path.read_text(encoding="utf-8")
    imports = imported_modules(path)

    assert "cv2" not in imports
    assert "tkinter" not in imports
    assert "queue" not in imports
    assert "collections" not in imports
    assert "self._latest" in source
    assert "deque" not in source
    assert "history" not in source.lower().replace("frame history", "")


def test_camera_worker_cannot_call_tk_or_render_widgets() -> None:
    for path in CAMERA_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "tkinter" not in source.lower()
        assert ".after(" not in source
        assert "PhotoImage" not in source
        assert "Canvas" not in source


def test_presentation_uses_application_boundary_and_has_no_worker_thread() -> None:
    for path in PRESENTATION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        imports = imported_modules(path)
        assert "hogflow.camera" not in source
        assert "hogflow.adapters" not in source
        assert "cv2" not in imports
        assert "threading" not in imports
        assert "Thread(" not in source


def test_phase_7_and_phase_8_remain_independent_from_preview() -> None:
    for package in ("counting", "domain", "sessions"):
        for path in (ROOT / "src" / "hogflow" / package).glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "preview_channel" not in source
            assert "PreviewFrame" not in source
            assert "hogflow.presentation" not in source


def test_phase_9_4_adds_no_storage_network_database_or_media_output() -> None:
    phase_roots = (CAMERA_ROOT, PRESENTATION_ROOT)
    forbidden = (
        "sqlite3",
        "requests",
        "urllib",
        "socket",
        "VideoWriter",
        "imwrite",
        "write_bytes",
    )
    for root in phase_roots:
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                assert token not in source
