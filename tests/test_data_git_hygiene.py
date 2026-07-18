import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={REPOSITORY_ROOT.as_posix()}",
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_local_data_artifacts_and_common_video_formats_are_ignored() -> None:
    candidates = (
        "data/raw/authorized.mp4",
        "data/interim/frame.jpg",
        "data/processed/inventory.json",
        "sample.mov",
        "sample.avi",
        "sample.mkv",
        "sample.m4v",
        "sample.webm",
    )

    result = _git("check-ignore", *candidates)

    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == set(candidates)


def test_data_documentation_and_keep_files_are_not_ignored() -> None:
    result = _git(
        "check-ignore",
        "data/README.md",
        "data/review_sidecar.example.json",
        "data/raw/.gitkeep",
    )

    assert result.returncode == 1
    assert result.stdout == ""


def test_repository_tracks_no_video_or_generated_data_artifacts() -> None:
    result = _git("ls-files")
    assert result.returncode == 0, result.stderr
    tracked = tuple(line.lower() for line in result.stdout.splitlines())
    video_extensions = (".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm")

    assert not any(path.endswith(video_extensions) for path in tracked)
    assert not any(
        path.startswith(("data/raw/", "data/interim/", "data/processed/"))
        and not path.endswith(".gitkeep")
        for path in tracked
    )
