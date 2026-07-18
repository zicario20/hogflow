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
        "data/annotations/raw/frame-001.jpg",
        "data/annotations/interim/labels.txt",
        "data/annotations/processed/instances.json",
        "data/models/model.ckpt",
        "data/runs/inference.json",
        "data/evaluation/report.json",
        "data/yolo/dataset.yaml",
        "data/coco/instances.json",
        "data/raw/clip.mp4.review.json",
        "runs/predict/frame.jpg",
        "weights/checkpoint.safetensors",
        "data/yolo/labels.cache",
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
        "data/annotations/raw/.gitkeep",
        "data/annotations/interim/.gitkeep",
        "data/annotations/processed/.gitkeep",
        "data/models/.gitkeep",
        "data/runs/.gitkeep",
        "data/evaluation/.gitkeep",
    )

    assert result.returncode == 1
    assert result.stdout == ""


def test_repository_tracks_no_video_or_generated_data_artifacts() -> None:
    result = _git("ls-files")
    assert result.returncode == 0, result.stderr
    tracked = tuple(line.lower() for line in result.stdout.splitlines())
    forbidden_extensions = (
        ".avi",
        ".ckpt",
        ".cache",
        ".engine",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".onnx",
        ".npy",
        ".npz",
        ".pb",
        ".pt",
        ".pth",
        ".safetensors",
        ".tflite",
        ".webm",
    )

    assert not any(path.endswith(forbidden_extensions) for path in tracked)
    assert not any(
        path.startswith(
            (
                "data/annotations/",
                "data/evaluation/",
                "data/interim/",
                "data/models/",
                "data/processed/",
                "data/raw/",
                "data/runs/",
            )
        )
        and not path.endswith(".gitkeep")
        for path in tracked
    )
