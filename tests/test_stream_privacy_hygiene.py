import re
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_CREDENTIAL_URL = re.compile(r"(?i)rtsps?://[^\s\"']+:[^@\s\"']+@")


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


def test_repository_source_candidates_contain_no_literal_rtsp_credentials() -> None:
    result = _git("ls-files", "--cached", "--others", "--exclude-standard")
    assert result.returncode == 0, result.stderr
    violations: list[str] = []
    for relative in result.stdout.splitlines():
        path = REPOSITORY_ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _CREDENTIAL_URL.search(text):
            violations.append(relative)

    assert not violations, f"Repository-source literal camera credentials: {violations}"


def test_camera_capture_and_debug_outputs_are_ignored() -> None:
    candidates = (
        "data/live/frame.jpg",
        "data/captures/frame.jpeg",
        "data/snapshots/frame.png",
        "recordings/stream.mp4",
        "camera_dumps/frame.jpg",
        "stream_debug/frame.png",
        "runs/live/result.json",
        "logs/camera/source.log",
        "camera.camera.local.json",
        "models/local-pig-detector.pt",
        "model_provenance/local-pig-detector.json",
        "inference_outputs/live-result.json",
        "preview_snapshots/frame.png",
    )
    result = _git("check-ignore", *candidates)

    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == set(candidates)


def test_repository_tracks_no_camera_media_or_private_configuration() -> None:
    result = _git("ls-files")
    assert result.returncode == 0, result.stderr
    tracked = tuple(path.lower() for path in result.stdout.splitlines())

    assert not any(
        path.startswith(("recordings/", "camera_dumps/", "stream_debug/", "logs/camera/"))
        for path in tracked
    )
    assert not any("camera.local" in path for path in tracked)
