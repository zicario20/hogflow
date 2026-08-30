from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hogflow.core import InputDataError
from hogflow.provisional import (
    ProvisionalVideoManifest,
    ProvisionalVideoRole,
    load_provisional_video_manifest,
    write_provisional_video_manifest,
)


def _write_manifest(root: Path, records: list[dict[str, str]]) -> Path:
    path = root / "authorization.json"
    path.write_text(json.dumps({"format_version": 1, "videos": records}), encoding="utf-8")
    return path


def test_manifest_accepts_exactly_two_explicit_roles(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            {
                "video_id": "demo_video_a",
                "basename": "a.mp4",
                "role": "training_development",
            },
            {
                "video_id": "demo_video_b",
                "basename": "b.mp4",
                "role": "independent_validation",
            },
        ],
    )
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "b.mp4").write_bytes(b"b")

    manifest = load_provisional_video_manifest(manifest_path, tmp_path)

    assert tuple(video.video_id for video in manifest.videos) == ("demo_video_a", "demo_video_b")
    assert manifest.videos[0].role is ProvisionalVideoRole.TRAINING_DEVELOPMENT
    assert manifest.videos[1].role is ProvisionalVideoRole.INDEPENDENT_VALIDATION


def test_manifest_rejects_extra_records_and_missing_media(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            {
                "video_id": "demo_video_a",
                "basename": "a.mp4",
                "role": "training_development",
            },
            {
                "video_id": "demo_video_b",
                "basename": "b.mp4",
                "role": "independent_validation",
            },
            {"video_id": "extra", "basename": "c.mp4", "role": "independent_validation"},
        ],
    )
    with pytest.raises(InputDataError, match="exactly two"):
        load_provisional_video_manifest(manifest_path, tmp_path)


def test_manifest_rejects_wrong_ids_or_order(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            {"video_id": "demo_video_b", "basename": "a.mp4", "role": "independent_validation"},
            {"video_id": "demo_video_a", "basename": "b.mp4", "role": "training_development"},
        ],
    )
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "b.mp4").write_bytes(b"b")

    with pytest.raises(InputDataError, match="demo_video_a followed by demo_video_b"):
        load_provisional_video_manifest(manifest_path, tmp_path)


def test_manifest_rejects_path_traversal_and_duplicate_basenames(tmp_path: Path) -> None:
    traversal_manifest = _write_manifest(
        tmp_path,
        [
            {
                "video_id": "demo_video_a",
                "basename": "../escape.mp4",
                "role": "training_development",
            },
            {
                "video_id": "demo_video_b",
                "basename": "b.mp4",
                "role": "independent_validation",
            },
        ],
    )
    (tmp_path / "b.mp4").write_bytes(b"b")
    with pytest.raises(InputDataError, match="basename"):
        load_provisional_video_manifest(traversal_manifest, tmp_path)

    duplicate_manifest = _write_manifest(
        tmp_path,
        [
            {
                "video_id": "demo_video_a",
                "basename": "same.mp4",
                "role": "training_development",
            },
            {
                "video_id": "demo_video_b",
                "basename": "same.mp4",
                "role": "independent_validation",
            },
        ],
    )
    (tmp_path / "same.mp4").write_bytes(b"x")
    with pytest.raises(InputDataError, match="unique"):
        load_provisional_video_manifest(duplicate_manifest, tmp_path)


def test_writer_round_trips_and_keeps_roles_explicit(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "b.mp4").write_bytes(b"b")
    manifest = ProvisionalVideoManifest.for_basenames("a.mp4", "b.mp4")
    path = tmp_path / "phase10_3a_authorization.local.json"

    write_provisional_video_manifest(manifest, path)

    loaded = load_provisional_video_manifest(path, tmp_path)
    assert loaded == manifest
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "format_version": 1,
        "videos": [
            {
                "video_id": "demo_video_a",
                "basename": "a.mp4",
                "role": "training_development",
            },
            {
                "video_id": "demo_video_b",
                "basename": "b.mp4",
                "role": "independent_validation",
            },
        ],
    }


def test_writer_rejects_non_ignored_repository_destination(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    (repository_root / ".git").write_text("gitdir: mock\n", encoding="utf-8")
    tracked_destination = repository_root / "docs" / "authorization.json"
    manifest = ProvisionalVideoManifest.for_basenames("a.mp4", "b.mp4")

    with pytest.raises(InputDataError, match="ignored and untracked"):
        write_provisional_video_manifest(manifest, tracked_destination)


def test_repository_rules_ignore_local_training_manifest_and_media() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    candidates = (
        "data/raw/video A.mp4",
        "data/raw/video B.mp4",
        "data/training/phase10_3a_authorization.local.json",
        "data/training/demo/frames/frame-001.jpg",
    )
    ignored = subprocess.run(
        ["git", "-c", f"safe.directory={repository_root.as_posix()}", "check-ignore", *candidates],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    tracked = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repository_root.as_posix()}",
            "ls-files",
            "--error-unmatch",
            "data/training/phase10_3a_authorization.local.json",
            "data/raw/video A.mp4",
            "data/raw/video B.mp4",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert ignored.returncode == 0, ignored.stderr
    assert set(ignored.stdout.splitlines()) == set(candidates)
    assert tracked.returncode != 0
    assert tracked.stdout == ""
