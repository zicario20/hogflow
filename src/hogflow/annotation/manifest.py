"""Sanitized annotation-manifest construction and deterministic serialization."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    PIG_CLASS_ID,
    PIG_CLASS_NAME,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationSplitPolicy,
    AnnotationStatus,
    DatasetSplit,
    ManifestValidationStatus,
    TemporalBlock,
    validate_opaque_identifier,
)
from hogflow.core import HogFlowError, InputDataError, configure_logging, get_logger

LOGGER = get_logger(__name__)


def build_annotation_manifest(
    extraction_report: Mapping[str, Any],
    status_map: Mapping[str, Any],
    *,
    split_policy: AnnotationSplitPolicy = AnnotationSplitPolicy.SOURCE_ISOLATED,
    temporal_blocks: Sequence[TemporalBlock] = (),
) -> AnnotationDatasetManifest:
    """Build one path-private manifest from sanitized extraction and status data."""

    records_payload = extraction_report.get("records")
    status_payload = status_map.get("frames")
    if not isinstance(records_payload, list):
        raise InputDataError("Extraction report must contain a records array.")
    if not isinstance(status_payload, dict):
        raise InputDataError("Annotation status map must contain a frames object.")
    dataset_id = status_map.get("dataset_id")
    frame_records: list[AnnotationFrameRecord] = []
    extraction_ids: set[str] = set()
    for item in records_payload:
        if not isinstance(item, dict):
            raise InputDataError("Extraction report records must be JSON objects.")
        frame_id = item.get("frame_id")
        if not isinstance(frame_id, str):
            raise InputDataError("Extraction report contains an invalid opaque frame ID.")
        if frame_id in extraction_ids:
            raise InputDataError("Extraction report contains duplicate frame IDs.")
        extraction_ids.add(frame_id)
        frame_status = status_payload.get(frame_id)
        if not isinstance(frame_status, dict):
            raise InputDataError(f"Annotation status is missing for opaque frame {frame_id!r}.")
        try:
            frame_records.append(
                AnnotationFrameRecord(
                    frame_id=frame_id,
                    clip_id=item["clip_id"],
                    split=DatasetSplit(item["split"]),
                    image_relative_path=item["image_relative_path"],
                    width=item["width"],
                    height=item["height"],
                    annotation_status=AnnotationStatus(frame_status["status"]),
                    bounding_box_count=frame_status.get("bounding_box_count", 0),
                    checksum_sha256=item["checksum_sha256"],
                    source_timestamp_seconds=item.get(
                        "actual_timestamp_seconds", item.get("planned_timestamp_seconds")
                    ),
                    temporal_block_id=item.get("temporal_block_id"),
                    validation_status=ManifestValidationStatus.PENDING,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InputDataError(
                f"Manifest input is invalid for opaque frame {frame_id!r}."
            ) from exc
    unexpected_statuses = sorted(set(status_payload) - extraction_ids)
    if unexpected_statuses:
        raise InputDataError(
            "Annotation status map contains unknown opaque frame IDs: "
            + ", ".join(unexpected_statuses)
        )
    block_tuple = tuple(sorted(temporal_blocks, key=lambda block: block.block_id))
    if split_policy is AnnotationSplitPolicy.SOURCE_ISOLATED:
        _enforce_source_split_isolation(frame_records)
    return AnnotationDatasetManifest(
        schema_version=1 if split_policy is AnnotationSplitPolicy.SOURCE_ISOLATED else 2,
        dataset_id=dataset_id,
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((PIG_CLASS_ID, PIG_CLASS_NAME),),
        frames=tuple(sorted(frame_records, key=lambda frame: frame.frame_id)),
        split_policy=split_policy,
        temporal_blocks=block_tuple,
    )


def manifest_to_dict(manifest: AnnotationDatasetManifest) -> dict[str, Any]:
    """Return a stable JSON-compatible representation of a manifest."""

    if not isinstance(manifest, AnnotationDatasetManifest):
        raise InputDataError("manifest must be AnnotationDatasetManifest.")
    return {
        "annotation_policy_version": manifest.annotation_policy_version,
        "class_map": [
            {"class_id": class_id, "class_name": class_name}
            for class_id, class_name in manifest.class_map
        ],
        "dataset_id": manifest.dataset_id,
        "frames": [
            {
                "annotation_status": frame.annotation_status.value,
                "bounding_box_count": frame.bounding_box_count,
                "checksum_sha256": frame.checksum_sha256,
                "clip_id": frame.clip_id,
                "frame_id": frame.frame_id,
                "height": frame.height,
                "image_relative_path": frame.image_relative_path,
                "split": frame.split.value,
                "validation_status": frame.validation_status.value,
                "width": frame.width,
                **(
                    {"source_timestamp_seconds": frame.source_timestamp_seconds}
                    if frame.source_timestamp_seconds is not None
                    else {}
                ),
                **(
                    {"temporal_block_id": frame.temporal_block_id}
                    if frame.temporal_block_id is not None
                    else {}
                ),
            }
            for frame in manifest.frames
        ],
        "schema_version": manifest.schema_version,
        **(
            {
                "split_policy": manifest.split_policy.value,
                "temporal_blocks": [
                    {
                        "block_id": block.block_id,
                        "clip_id": block.clip_id,
                        "split": block.split.value,
                        "start_seconds": block.start_seconds,
                        "end_seconds": block.end_seconds,
                    }
                    for block in manifest.temporal_blocks
                ],
            }
            if manifest.split_policy is AnnotationSplitPolicy.TEMPORAL_BLOCKED
            else {}
        ),
    }


def write_annotation_manifest(
    manifest: AnnotationDatasetManifest,
    path: str | Path,
) -> None:
    """Atomically write a deterministic sanitized local manifest."""

    _atomic_write_json(
        Path(path),
        manifest_to_dict(manifest),
        description="annotation dataset manifest",
    )


def load_annotation_manifest(path: str | Path) -> AnnotationDatasetManifest:
    """Load a sanitized annotation manifest without accepting source paths."""

    payload = _load_json_object(path, description="annotation dataset manifest")
    try:
        class_payload = payload["class_map"]
        frame_payload = payload["frames"]
        if not isinstance(class_payload, list) or not isinstance(frame_payload, list):
            raise TypeError
        class_map = tuple((item["class_id"], item["class_name"]) for item in class_payload)
        frames = tuple(
            AnnotationFrameRecord(
                frame_id=item["frame_id"],
                clip_id=item["clip_id"],
                split=DatasetSplit(item["split"]),
                image_relative_path=item["image_relative_path"],
                width=item["width"],
                height=item["height"],
                annotation_status=AnnotationStatus(item["annotation_status"]),
                bounding_box_count=item["bounding_box_count"],
                checksum_sha256=item["checksum_sha256"],
                source_timestamp_seconds=item.get("source_timestamp_seconds"),
                temporal_block_id=item.get("temporal_block_id"),
                validation_status=ManifestValidationStatus(item["validation_status"]),
            )
            for item in frame_payload
        )
        split_policy = AnnotationSplitPolicy(
            payload.get("split_policy", AnnotationSplitPolicy.SOURCE_ISOLATED.value)
        )
        temporal_blocks = tuple(
            TemporalBlock(
                block_id=item["block_id"],
                clip_id=item["clip_id"],
                split=DatasetSplit(item["split"]),
                start_seconds=item["start_seconds"],
                end_seconds=item["end_seconds"],
            )
            for item in payload.get("temporal_blocks", [])
        )
        return AnnotationDatasetManifest(
            schema_version=payload["schema_version"],
            dataset_id=payload["dataset_id"],
            annotation_policy_version=payload["annotation_policy_version"],
            class_map=class_map,
            frames=frames,
            split_policy=split_policy,
            temporal_blocks=temporal_blocks,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InputDataError("Annotation dataset manifest has an invalid structure.") from exc


def prepare_manifest(
    *,
    extraction_report_path: str | Path,
    status_map_path: str | Path,
    frame_plan_path: str | Path | None = None,
    temporal_block_ids: Sequence[str] | None = None,
    output_path: str | Path,
) -> AnnotationDatasetManifest:
    """Load local sanitized inputs, build a manifest, and write it."""

    if temporal_block_ids is not None:
        requested_block_ids = _normalize_temporal_block_ids(temporal_block_ids)
        if frame_plan_path is None:
            raise InputDataError("Temporal block scope requires an explicit local frame plan.")
    else:
        requested_block_ids = None

    extraction_report = _load_json_object(extraction_report_path, description="extraction report")
    status_map = _load_json_object(status_map_path, description="annotation status map")
    split_policy = AnnotationSplitPolicy.SOURCE_ISOLATED
    temporal_blocks: tuple[TemporalBlock, ...] = ()
    if frame_plan_path is not None:
        all_temporal_blocks = _load_temporal_blocks_from_frame_plan(frame_plan_path)
        temporal_blocks = all_temporal_blocks
        if requested_block_ids is not None:
            blocks_by_id = {block.block_id: block for block in all_temporal_blocks}
            unknown_block_ids = sorted(set(requested_block_ids) - set(blocks_by_id))
            if unknown_block_ids:
                raise InputDataError(
                    "Requested scope contains an unknown temporal block: "
                    + ", ".join(unknown_block_ids)
                )
            temporal_blocks = tuple(
                block for block in all_temporal_blocks if block.block_id in requested_block_ids
            )
            extraction_report, status_map = _scope_manifest_inputs(
                extraction_report,
                status_map,
                block_ids=set(requested_block_ids),
            )
            if any(block.split is DatasetSplit.TEST for block in temporal_blocks):
                if len(temporal_blocks) != 1 or temporal_blocks[0].split is not DatasetSplit.TEST:
                    raise InputDataError(
                        "A test temporal block must be prepared as its own holdout manifest."
                    )
                split_policy = AnnotationSplitPolicy.SOURCE_ISOLATED
                temporal_blocks = ()
            else:
                split_policy = AnnotationSplitPolicy.TEMPORAL_BLOCKED
        else:
            split_policy = AnnotationSplitPolicy.TEMPORAL_BLOCKED
    manifest = build_annotation_manifest(
        extraction_report,
        status_map,
        split_policy=split_policy,
        temporal_blocks=temporal_blocks,
    )
    write_annotation_manifest(manifest, output_path)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    """Create the sanitized annotation-manifest CLI parser."""

    parser = argparse.ArgumentParser(
        description="Build a sanitized local annotation dataset manifest."
    )
    parser.add_argument("--extraction-report", type=Path, required=True)
    parser.add_argument("--status-map", type=Path, required=True)
    parser.add_argument("--frame-plan", type=Path)
    parser.add_argument(
        "--block-id",
        dest="temporal_block_ids",
        action="append",
        metavar="BLOCK_ID",
        help="Limit a frame plan to one or more explicit temporal block IDs.",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build one local manifest and return a process status code."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        manifest = prepare_manifest(
            extraction_report_path=arguments.extraction_report,
            status_map_path=arguments.status_map,
            frame_plan_path=arguments.frame_plan,
            temporal_block_ids=arguments.temporal_block_ids,
            output_path=arguments.output,
        )
    except HogFlowError as exc:
        parser.error(str(exc))
    LOGGER.info("Annotation manifest complete: %d opaque frames", len(manifest.frames))
    return 0


def _normalize_temporal_block_ids(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise InputDataError("Temporal block scope must contain one or more block IDs.")
    block_ids = tuple(value)
    if not block_ids:
        raise InputDataError("Temporal block scope must contain one or more block IDs.")
    for block_id in block_ids:
        validate_opaque_identifier(block_id, field_name="temporal_block_id")
    if len(set(block_ids)) != len(block_ids):
        raise InputDataError("Temporal block scope must not contain duplicate block IDs.")
    return block_ids


def _scope_manifest_inputs(
    extraction_report: Mapping[str, Any],
    status_map: Mapping[str, Any],
    *,
    block_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = extraction_report.get("records")
    statuses = status_map.get("frames")
    if not isinstance(records, list) or not isinstance(statuses, dict):
        raise InputDataError("Manifest scope inputs have an invalid structure.")
    scoped_records = [
        record
        for record in records
        if isinstance(record, dict) and record.get("temporal_block_id") in block_ids
    ]
    if not scoped_records:
        raise InputDataError("Requested temporal block scope contains no extracted frames.")
    scoped_frame_ids: set[str] = set()
    for record in scoped_records:
        frame_id = record.get("frame_id")
        if not isinstance(frame_id, str):
            raise InputDataError("Manifest scope contains a record with an invalid frame ID.")
        scoped_frame_ids.add(frame_id)
    scoped_statuses = {
        frame_id: status for frame_id, status in statuses.items() if frame_id in scoped_frame_ids
    }
    return (
        {**extraction_report, "records": scoped_records},
        {**status_map, "frames": scoped_statuses},
    )


def _enforce_source_split_isolation(frames: Sequence[AnnotationFrameRecord]) -> None:
    split_by_clip: dict[str, DatasetSplit] = {}
    for frame in frames:
        previous = split_by_clip.setdefault(frame.clip_id, frame.split)
        if previous is not frame.split:
            raise InputDataError(
                f"Opaque source clip {frame.clip_id!r} appears in more than one dataset split."
            )


def _load_json_object(path: str | Path, *, description: str) -> dict[str, Any]:
    input_path = Path(path)
    if not input_path.is_file():
        raise InputDataError(f"The local {description} is missing or is not a file.")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError(f"The local {description} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise InputDataError(f"The local {description} must contain one JSON object.")
    return payload


def _load_temporal_blocks_from_frame_plan(path: str | Path) -> tuple[TemporalBlock, ...]:
    payload = _load_json_object(path, description="frame plan")
    block_plan = payload.get("phase10_3a_block_plan")
    if not isinstance(block_plan, dict):
        raise InputDataError("The local frame plan must contain phase10_3a_block_plan.blocks.")
    blocks_payload = block_plan.get("blocks")
    if not isinstance(blocks_payload, list) or not blocks_payload:
        raise InputDataError("The local frame plan must contain phase10_3a_block_plan.blocks.")
    temporal_blocks: list[TemporalBlock] = []
    for item in blocks_payload:
        if not isinstance(item, dict):
            raise InputDataError(
                "The local frame plan contains an invalid phase10_3a_block_plan.blocks entry."
            )
        try:
            temporal_blocks.append(
                TemporalBlock(
                    block_id=item["block_id"],
                    clip_id=item["clip_id"],
                    split=DatasetSplit(item["split"]),
                    start_seconds=item["start_seconds"],
                    end_seconds=item["end_seconds"],
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InputDataError(
                "The local frame plan contains an invalid phase10_3a_block_plan.blocks entry."
            ) from exc
    return tuple(temporal_blocks)


def _atomic_write_json(path: Path, payload: Mapping[str, Any], *, description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary_path: Path | None = None
    try:
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
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise InputDataError(f"Unable to write the sanitized {description}.") from exc


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_annotation_manifest",
    "load_annotation_manifest",
    "manifest_to_dict",
    "prepare_manifest",
    "write_annotation_manifest",
]
