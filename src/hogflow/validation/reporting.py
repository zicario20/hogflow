"""Deterministic path-free JSON and Markdown validation reporting."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from hogflow.validation.errors import ValidationOutputError
from hogflow.validation.models import RealWorldValidationReport, to_primitive


def validation_report_to_dict(report: RealWorldValidationReport) -> dict[str, object]:
    """Return one deterministic JSON-safe report payload."""

    if not isinstance(report, RealWorldValidationReport):
        raise ValidationOutputError("Validation report is invalid.")
    payload = to_primitive(report)
    if not isinstance(payload, dict):
        raise ValidationOutputError("Validation report payload is invalid.")
    payload["report_fingerprint"] = report.report_fingerprint
    for result_payload, result in zip(payload["results"], report.results, strict=True):
        result_payload["run_fingerprint"] = result.run_fingerprint
    return payload


def validation_report_json(report: RealWorldValidationReport) -> str:
    """Serialize with stable key and tuple ordering."""

    return (
        json.dumps(
            validation_report_to_dict(report),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
        )
        + "\n"
    )


def validation_report_markdown(report: RealWorldValidationReport) -> str:
    """Render a bounded human summary without paths or raw media evidence."""

    lines = [
        "# HogFlow Phase 10.3 local validation",
        "",
        f"- Report fingerprint: `{report.report_fingerprint}`",
        f"- Model gate: `{report.model_availability.state.value}`",
        f"- Empirical verdict: **{report.empirical_verdict}**",
        "",
    ]
    for result in report.results:
        lines.extend(
            [
                f"## {result.video.video_id}",
                "",
                f"- Role: `{result.video.role.value}`",
                f"- Status: `{result.status.value}`",
                f"- Evidence: `{result.evidence_level.value}`",
                f"- Structurally complete: `{str(result.structurally_complete).lower()}`",
                f"- Frames processed: `{_metric(result.performance.frames_processed)}`",
                f"- System count: `{_metric(result.crossing_counting.system_count)}`",
                f"- Manual total: `{_metric(result.ground_truth.manual_total)}`",
                f"- Conclusion: `{result.conclusion}`",
                "- Limitations:",
            ]
        )
        lines.extend(f"  - {item}" for item in result.limitations)
        lines.append("")
    return "\n".join(lines)


def write_validation_report(
    report: RealWorldValidationReport,
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    """Atomically write both local report formats."""

    _atomic_write(Path(json_path), validation_report_json(report))
    _atomic_write(Path(markdown_path), validation_report_markdown(report))


def _metric(metric: object) -> str:
    state = getattr(metric, "state").value
    value = getattr(metric, "value")
    unit = getattr(metric, "unit")
    if value is None:
        return state
    return f"{state}: {value}{' ' + unit if unit else ''}"


def _atomic_write(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        os.replace(temporary, path)
    except OSError as exc:
        raise ValidationOutputError("Sanitized validation report could not be written.") from exc


__all__ = [
    "validation_report_json",
    "validation_report_markdown",
    "validation_report_to_dict",
    "write_validation_report",
]
