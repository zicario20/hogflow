from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_runs_required_quality_gates_with_minimal_permissions() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    required_fragments = (
        "push:",
        "pull_request:",
        "contents: read",
        "runs-on: ubuntu-latest",
        'python-version: "3.12"',
        'python -m pip install -e ".[dev]"',
        "python -m ruff check --no-cache .",
        "python -m ruff format --check --no-cache .",
        "python -m pytest",
        "python -m compileall -q src",
        "python -m pip check",
    )
    for fragment in required_fragments:
        assert fragment in content


def test_ci_workflow_does_not_access_or_upload_local_dataset_artifacts() -> None:
    content = WORKFLOW.read_text(encoding="utf-8").lower()

    assert "data/raw" not in content
    assert "upload-artifact" not in content
    assert "git-lfs" not in content
    assert "youtube" not in content
