"""Strict JSON input and deterministic report output for Phase 6."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from hogflow.counting import LiveCrossingDirection, NormalizedLine, NormalizedPoint, TrackAnchor
from hogflow.evaluation.line_errors import (
    LineEvaluationOutputError,
    LineEvaluationSchemaError,
)
from hogflow.evaluation.line_evaluator import mark_report_written
from hogflow.evaluation.line_models import (
    LINE_EVALUATION_SCHEMA_VERSION,
    CandidateEvaluationResult,
    CrossingEventMetrics,
    EvidenceLevel,
    GroundTruthCrossingEvent,
    LineCandidate,
    LineEvaluationPlan,
    LineEvaluationReport,
    LineRankingMethod,
    TrackingReplay,
)
from hogflow.models import BoundingBox, Detection, Track
from hogflow.tracking import TrackedObject, TrackingResult, TrackState


def _expect_object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise LineEvaluationSchemaError(f"{name} must be a JSON object.")
    return value


def _expect_array(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise LineEvaluationSchemaError(f"{name} must be a JSON array.")
    return value


def _expect_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    name: str,
) -> None:
    optional = optional or set()
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise LineEvaluationSchemaError(f"{name} is missing required fields: {missing}.")
    if unknown:
        raise LineEvaluationSchemaError(f"{name} contains unknown fields: {unknown}.")


def _enum_value(enum_type: type[Any], value: object, name: str) -> Any:
    if not isinstance(value, str):
        raise LineEvaluationSchemaError(f"{name} must be text.")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise LineEvaluationSchemaError(f"{name} contains an unsupported value.") from exc


def _datetime_value(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise LineEvaluationSchemaError(f"{name} must be an ISO 8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LineEvaluationSchemaError(f"{name} must be a valid ISO 8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise LineEvaluationSchemaError(f"{name} must include a timezone.")
    return parsed


def _metadata_value(value: object, name: str) -> tuple[tuple[str, str], ...]:
    mapping = _expect_object(value, name)
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in mapping.items()):
        raise LineEvaluationSchemaError(f"{name} must contain text keys and values.")
    return tuple(sorted(mapping.items()))


def _load_json_document(path: str | Path, document_name: str) -> Mapping[str, Any]:
    input_path = Path(path)
    if not input_path.exists() or not input_path.is_file():
        raise LineEvaluationSchemaError(f"{document_name} input is not an existing file.")
    try:
        text = input_path.read_text(encoding="utf-8")
        payload = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LineEvaluationSchemaError(
            f"{document_name} file {input_path.name!r} is not valid UTF-8 JSON."
        ) from exc
    return _expect_object(payload, document_name)


def _point_from_dict(value: object, name: str) -> NormalizedPoint:
    mapping = _expect_object(value, name)
    _expect_keys(mapping, required={"x", "y"}, name=name)
    try:
        return NormalizedPoint(mapping["x"], mapping["y"])
    except Exception as exc:
        if isinstance(exc, LineEvaluationSchemaError):
            raise
        raise LineEvaluationSchemaError(f"{name} is not a valid normalized point.") from exc


def _candidate_from_dict(value: object, index: int) -> LineCandidate:
    name = f"Line candidate {index}"
    mapping = _expect_object(value, name)
    _expect_keys(
        mapping,
        required={
            "absent_track_retention_updates",
            "anchor",
            "candidate_id",
            "epsilon",
            "line",
            "tags",
        },
        optional={"description"},
        name=name,
    )
    line_mapping = _expect_object(mapping["line"], f"{name} line")
    _expect_keys(line_mapping, required={"start", "end"}, name=f"{name} line")
    tags = _expect_array(mapping["tags"], f"{name} tags")
    try:
        return LineCandidate(
            candidate_id=mapping["candidate_id"],
            line=NormalizedLine(
                start=_point_from_dict(line_mapping["start"], f"{name} line start"),
                end=_point_from_dict(line_mapping["end"], f"{name} line end"),
            ),
            anchor=_enum_value(TrackAnchor, mapping["anchor"], f"{name} anchor"),
            epsilon=mapping["epsilon"],
            absent_track_retention_updates=mapping["absent_track_retention_updates"],
            description=mapping.get("description"),
            tags=tuple(tags),
        )
    except LineEvaluationSchemaError:
        raise
    except Exception as exc:
        raise LineEvaluationSchemaError(f"{name} is invalid.") from exc


def line_evaluation_plan_to_dict(plan: LineEvaluationPlan) -> dict[str, object]:
    """Return the strict sanitized JSON representation of one plan."""

    return {
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "ranking_method": plan.ranking_method.value,
        "matching_window_frames": plan.matching_window_frames,
        "require_direction_match": plan.require_direction_match,
        "near_endpoint_distance": plan.near_endpoint_distance,
        "large_gap_threshold": plan.large_gap_threshold,
        "metadata": dict(plan.metadata),
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "line": {
                    "start": {
                        "x": candidate.line.start.x,
                        "y": candidate.line.start.y,
                    },
                    "end": {
                        "x": candidate.line.end.x,
                        "y": candidate.line.end.y,
                    },
                },
                "anchor": candidate.anchor.value,
                "epsilon": candidate.epsilon,
                "absent_track_retention_updates": (candidate.absent_track_retention_updates),
                "description": candidate.description,
                "tags": list(candidate.tags),
            }
            for candidate in plan.candidates
        ],
    }


def load_line_evaluation_plan(path: str | Path) -> LineEvaluationPlan:
    """Load and validate a versioned candidate plan without executing content."""

    payload = _load_json_document(path, "Line evaluation plan")
    _expect_keys(
        payload,
        required={
            "candidates",
            "large_gap_threshold",
            "matching_window_frames",
            "metadata",
            "near_endpoint_distance",
            "plan_id",
            "ranking_method",
            "require_direction_match",
            "schema_version",
        },
        name="Line evaluation plan",
    )
    if payload["schema_version"] != LINE_EVALUATION_SCHEMA_VERSION:
        raise LineEvaluationSchemaError("Line evaluation plan schema version is unsupported.")
    candidates = _expect_array(payload["candidates"], "Line evaluation candidates")
    try:
        return LineEvaluationPlan(
            plan_id=payload["plan_id"],
            candidates=tuple(
                _candidate_from_dict(candidate, index) for index, candidate in enumerate(candidates)
            ),
            ranking_method=_enum_value(
                LineRankingMethod,
                payload["ranking_method"],
                "Line ranking method",
            ),
            matching_window_frames=payload["matching_window_frames"],
            require_direction_match=payload["require_direction_match"],
            near_endpoint_distance=payload["near_endpoint_distance"],
            large_gap_threshold=payload["large_gap_threshold"],
            schema_version=payload["schema_version"],
            metadata=_metadata_value(payload["metadata"], "Plan metadata"),
        )
    except LineEvaluationSchemaError:
        raise
    except Exception as exc:
        raise LineEvaluationSchemaError("Line evaluation plan is invalid.") from exc


def _tracked_object_to_dict(item: TrackedObject) -> dict[str, object]:
    box = item.track.detection.bounding_box
    return {
        "tracker_id": item.track.tracker_id,
        "bounding_box": {
            "x_min": box.x_min,
            "y_min": box.y_min,
            "x_max": box.x_max,
            "y_max": box.y_max,
        },
        "confidence": item.track.detection.confidence,
        "class_id": item.track.detection.class_id,
        "class_name": item.track.detection.class_name,
        "source_detection_index": item.source_detection_index,
        "state": item.state.value,
        "age_frames": item.age_frames,
        "hits": item.hits,
        "missed_frames": item.missed_frames,
    }


def _tracking_result_to_dict(result: TrackingResult) -> dict[str, object]:
    return {
        "frame_sequence": result.frame_sequence,
        "captured_at": result.captured_at.isoformat(),
        "frame_width": result.frame_width,
        "frame_height": result.frame_height,
        "tracked_objects": [_tracked_object_to_dict(item) for item in result.tracked_objects],
        "tracker_id": result.tracker_id,
        "tracker_version": result.tracker_version,
        "configuration_fingerprint": result.configuration_fingerprint,
        "processing_started_at": result.processing_started_at.isoformat(),
        "processing_finished_at": result.processing_finished_at.isoformat(),
        "tracking_latency_ms": result.tracking_latency_ms,
    }


def tracking_replay_to_dict(replay: TrackingReplay) -> dict[str, object]:
    """Return a path-free replay document containing no frame payloads."""

    return {
        "schema_version": replay.schema_version,
        "source_id": replay.source_id,
        "replay_id": replay.replay_id,
        "tracker_lifecycle_id": replay.tracker_lifecycle_id,
        "evidence_level": replay.evidence_level.value,
        "provenance": replay.provenance,
        "metadata": dict(replay.metadata),
        "tracking_results": [
            _tracking_result_to_dict(result) for result in replay.tracking_results
        ],
        "ground_truth_events": [
            {
                "event_id": event.event_id,
                "frame_start": event.frame_start,
                "frame_end": event.frame_end,
                "direction": None if event.direction is None else event.direction.value,
                "timestamp": None if event.timestamp is None else event.timestamp.isoformat(),
                "annotation_quality": event.annotation_quality,
                "notes": event.notes,
                "provenance": event.provenance,
            }
            for event in replay.ground_truth_events
        ],
    }


def _tracked_object_from_dict(value: object, frame_index: int, object_index: int) -> TrackedObject:
    name = f"Replay frame {frame_index} tracked object {object_index}"
    mapping = _expect_object(value, name)
    _expect_keys(
        mapping,
        required={
            "age_frames",
            "bounding_box",
            "class_id",
            "class_name",
            "confidence",
            "hits",
            "missed_frames",
            "source_detection_index",
            "state",
            "tracker_id",
        },
        name=name,
    )
    box = _expect_object(mapping["bounding_box"], f"{name} bounding box")
    _expect_keys(
        box,
        required={"x_min", "y_min", "x_max", "y_max"},
        name=f"{name} bounding box",
    )
    try:
        detection = Detection(
            bounding_box=BoundingBox(
                box["x_min"],
                box["y_min"],
                box["x_max"],
                box["y_max"],
            ),
            confidence=mapping["confidence"],
            class_id=mapping["class_id"],
            class_name=mapping["class_name"],
        )
        return TrackedObject(
            track=Track(tracker_id=mapping["tracker_id"], detection=detection),
            source_detection_index=mapping["source_detection_index"],
            state=_enum_value(TrackState, mapping["state"], f"{name} state"),
            age_frames=mapping["age_frames"],
            hits=mapping["hits"],
            missed_frames=mapping["missed_frames"],
        )
    except LineEvaluationSchemaError:
        raise
    except Exception as exc:
        raise LineEvaluationSchemaError(f"{name} is invalid.") from exc


def _tracking_result_from_dict(
    value: object,
    index: int,
    source_id: str,
) -> TrackingResult:
    name = f"Replay frame {index}"
    mapping = _expect_object(value, name)
    _expect_keys(
        mapping,
        required={
            "captured_at",
            "configuration_fingerprint",
            "frame_height",
            "frame_sequence",
            "frame_width",
            "processing_finished_at",
            "processing_started_at",
            "tracked_objects",
            "tracker_id",
            "tracker_version",
            "tracking_latency_ms",
        },
        name=name,
    )
    tracked_objects = _expect_array(mapping["tracked_objects"], f"{name} tracked objects")
    try:
        return TrackingResult(
            source_id=source_id,
            frame_sequence=mapping["frame_sequence"],
            captured_at=_datetime_value(mapping["captured_at"], f"{name} capture time"),
            frame_width=mapping["frame_width"],
            frame_height=mapping["frame_height"],
            tracked_objects=tuple(
                _tracked_object_from_dict(item, index, object_index)
                for object_index, item in enumerate(tracked_objects)
            ),
            tracker_id=mapping["tracker_id"],
            tracker_version=mapping["tracker_version"],
            configuration_fingerprint=mapping["configuration_fingerprint"],
            processing_started_at=_datetime_value(
                mapping["processing_started_at"],
                f"{name} processing start",
            ),
            processing_finished_at=_datetime_value(
                mapping["processing_finished_at"],
                f"{name} processing finish",
            ),
            tracking_latency_ms=mapping["tracking_latency_ms"],
        )
    except LineEvaluationSchemaError:
        raise
    except Exception as exc:
        raise LineEvaluationSchemaError(f"{name} is invalid.") from exc


def _ground_truth_from_dict(value: object, index: int) -> GroundTruthCrossingEvent:
    name = f"Ground-truth crossing {index}"
    mapping = _expect_object(value, name)
    _expect_keys(
        mapping,
        required={
            "annotation_quality",
            "direction",
            "event_id",
            "frame_end",
            "frame_start",
            "notes",
            "provenance",
            "timestamp",
        },
        name=name,
    )
    try:
        direction = (
            None
            if mapping["direction"] is None
            else _enum_value(
                LiveCrossingDirection,
                mapping["direction"],
                f"{name} direction",
            )
        )
        timestamp = (
            None
            if mapping["timestamp"] is None
            else _datetime_value(mapping["timestamp"], f"{name} timestamp")
        )
        return GroundTruthCrossingEvent(
            event_id=mapping["event_id"],
            frame_start=mapping["frame_start"],
            frame_end=mapping["frame_end"],
            direction=direction,
            timestamp=timestamp,
            annotation_quality=mapping["annotation_quality"],
            notes=mapping["notes"],
            provenance=mapping["provenance"],
        )
    except LineEvaluationSchemaError:
        raise
    except Exception as exc:
        raise LineEvaluationSchemaError(f"{name} is invalid.") from exc


def load_tracking_replay(path: str | Path) -> TrackingReplay:
    """Load a strict versioned replay without decoding media or executing code."""

    payload = _load_json_document(path, "Tracking replay")
    _expect_keys(
        payload,
        required={
            "evidence_level",
            "ground_truth_events",
            "metadata",
            "provenance",
            "replay_id",
            "schema_version",
            "source_id",
            "tracker_lifecycle_id",
            "tracking_results",
        },
        name="Tracking replay",
    )
    if payload["schema_version"] != LINE_EVALUATION_SCHEMA_VERSION:
        raise LineEvaluationSchemaError("Tracking replay schema version is unsupported.")
    if not isinstance(payload["source_id"], str):
        raise LineEvaluationSchemaError("Tracking replay source ID must be text.")
    tracking_results = _expect_array(payload["tracking_results"], "Tracking replay frames")
    ground_truth = _expect_array(
        payload["ground_truth_events"],
        "Tracking replay ground truth",
    )
    try:
        return TrackingReplay(
            source_id=payload["source_id"],
            replay_id=payload["replay_id"],
            tracker_lifecycle_id=payload["tracker_lifecycle_id"],
            tracking_results=tuple(
                _tracking_result_from_dict(item, index, payload["source_id"])
                for index, item in enumerate(tracking_results)
            ),
            evidence_level=_enum_value(
                EvidenceLevel,
                payload["evidence_level"],
                "Tracking replay evidence level",
            ),
            provenance=payload["provenance"],
            ground_truth_events=tuple(
                _ground_truth_from_dict(item, index) for index, item in enumerate(ground_truth)
            ),
            metadata=_metadata_value(payload["metadata"], "Replay metadata"),
            schema_version=payload["schema_version"],
        )
    except LineEvaluationSchemaError:
        raise
    except Exception as exc:
        raise LineEvaluationSchemaError("Tracking replay is invalid.") from exc


def _ground_truth_metrics_to_dict(
    metrics: CrossingEventMetrics | None,
) -> dict[str, object] | None:
    if metrics is None:
        return None
    return {
        "true_positives": metrics.true_positives,
        "false_positives": metrics.false_positives,
        "false_negatives": metrics.false_negatives,
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1_score": metrics.f1_score,
        "mean_absolute_frame_offset": metrics.mean_absolute_frame_offset,
        "median_absolute_frame_offset": metrics.median_absolute_frame_offset,
        "direction_correct_count": metrics.direction_correct_count,
        "direction_error_count": metrics.direction_error_count,
        "exact_event_total_difference": metrics.exact_event_total_difference,
        "absolute_event_count_error": metrics.absolute_event_count_error,
        "matching_operations": metrics.matching_operations,
        "matches": [
            {
                "ground_truth_event_id": match.ground_truth_event_id,
                "predicted_frame_sequence": match.predicted_frame_sequence,
                "predicted_tracker_lifecycle_id": (match.predicted_tracker_lifecycle_id),
                "predicted_tracker_id": match.predicted_tracker_id,
                "absolute_frame_offset": match.absolute_frame_offset,
                "direction_correct": match.direction_correct,
            }
            for match in metrics.matches
        ],
    }


def _candidate_result_to_dict(result: CandidateEvaluationResult) -> dict[str, object]:
    return {
        "candidate_id": result.candidate_id,
        "candidate_fingerprint": result.candidate_fingerprint,
        "tracking_results_processed": result.tracking_results_processed,
        "tracks_observed": result.tracks_observed,
        "events_total": result.events_total,
        "negative_to_positive_events": result.negative_to_positive_events,
        "positive_to_negative_events": result.positive_to_negative_events,
        "frames_with_events": result.frames_with_events,
        "events_near_endpoints": result.events_near_endpoints,
        "events_after_gaps": result.events_after_gaps,
        "events_after_large_gaps": result.events_after_large_gaps,
        "events_by_lifecycle": [
            {
                "tracker_lifecycle_id": item.tracker_lifecycle_id,
                "events_total": item.events_total,
            }
            for item in result.events_by_lifecycle
        ],
        "states_expired": result.states_expired,
        "replay_duration_seconds": result.replay_duration_seconds,
        "event_density_per_second": result.event_density_per_second,
        "events_per_track_ratio": result.events_per_track_ratio,
        "gap_count": result.gap_count,
        "maximum_gap": result.maximum_gap,
        "event_after_gap_ratio": result.event_after_gap_ratio,
        "evaluation_latency_ms": result.evaluation_latency_ms,
        "deterministic_event_fingerprint": result.deterministic_event_fingerprint,
        "ground_truth_metrics": _ground_truth_metrics_to_dict(result.ground_truth_metrics),
        "errors": list(result.errors),
        "limitations": list(result.limitations),
    }


def line_evaluation_report_to_dict(report: LineEvaluationReport) -> dict[str, object]:
    """Return deterministic sanitized report data without replay observations."""

    return {
        "schema_version": report.schema_version,
        "evaluator_version": report.evaluator_version,
        "generated_at": report.generated_at.isoformat(),
        "plan": line_evaluation_plan_to_dict(report.plan),
        "plan_fingerprint": report.plan.fingerprint,
        "replay": {
            "replay_id": report.replay_id,
            "replay_fingerprint": report.replay_fingerprint,
            "provenance": report.replay_provenance,
            "evidence_level": report.evidence_level.value,
            "ground_truth_available": report.ground_truth_available,
        },
        "candidate_results": [
            _candidate_result_to_dict(result) for result in report.candidate_results
        ],
        "ranking": {
            "method": report.ranking_method.value,
            "ranked_candidate_ids": list(report.ranked_candidate_ids),
            "recommended_candidate_id": report.recommended_candidate_id,
            "explanation": report.recommendation_explanation,
        },
        "warnings": list(report.warnings),
        "limitations": list(report.limitations),
        "statistics": {
            "candidates_requested": report.statistics.candidates_requested,
            "candidates_completed": report.statistics.candidates_completed,
            "frames_replayed": report.statistics.frames_replayed,
            "total_crossing_updates": report.statistics.total_crossing_updates,
            "total_events_evaluated": report.statistics.total_events_evaluated,
            "matching_operations": report.statistics.matching_operations,
            "evaluation_duration_ms": report.statistics.evaluation_duration_ms,
            "report_written": report.statistics.report_written,
            "failures": report.statistics.failures,
            "last_error_category": report.statistics.last_error_category.value,
        },
    }


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = (
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise LineEvaluationOutputError(
            f"Unable to write sanitized evaluation file {path.name!r}."
        ) from exc


def write_line_evaluation_plan(plan: LineEvaluationPlan, path: str | Path) -> None:
    """Atomically write a sanitized candidate plan."""

    if not isinstance(plan, LineEvaluationPlan):
        raise LineEvaluationOutputError("Only a validated line evaluation plan can be written.")
    _atomic_write_json(Path(path), line_evaluation_plan_to_dict(plan))


def write_tracking_replay(replay: TrackingReplay, path: str | Path) -> None:
    """Atomically write a payload-free tracking replay."""

    if not isinstance(replay, TrackingReplay):
        raise LineEvaluationOutputError("Only a validated tracking replay can be written.")
    _atomic_write_json(Path(path), tracking_replay_to_dict(replay))


def write_line_evaluation_report(
    report: LineEvaluationReport,
    path: str | Path,
) -> LineEvaluationReport:
    """Atomically write the report and return its immutable written-state copy."""

    if not isinstance(report, LineEvaluationReport):
        raise LineEvaluationOutputError("Only a validated line evaluation report can be written.")
    written_report = mark_report_written(report)
    _atomic_write_json(Path(path), line_evaluation_report_to_dict(written_report))
    return written_report


def override_plan_options(
    plan: LineEvaluationPlan,
    *,
    ranking_method: LineRankingMethod | None,
    matching_window_frames: int | None,
) -> LineEvaluationPlan:
    """Return a validated immutable plan with explicit CLI overrides."""

    return replace(
        plan,
        ranking_method=ranking_method or plan.ranking_method,
        matching_window_frames=(
            plan.matching_window_frames
            if matching_window_frames is None
            else matching_window_frames
        ),
    )


__all__ = [
    "line_evaluation_plan_to_dict",
    "line_evaluation_report_to_dict",
    "load_line_evaluation_plan",
    "load_tracking_replay",
    "override_plan_options",
    "tracking_replay_to_dict",
    "write_line_evaluation_plan",
    "write_line_evaluation_report",
    "write_tracking_replay",
]
