# Phase 4.2 — Local Annotation Dataset Preparation

## Status

Phase 4.2 tooling implemented. Real annotation may still be incomplete; no pig
detector has been downloaded, trained, fine-tuned, or validated, no accuracy
has been measured, and Phase 4.3 has not started.

## Local-only workflow

1. Run the Phase 3 authorized-video inventory.
2. Run Phase 4.1 metadata-only detection selection.
3. Create an ignored local source map from opaque clip IDs to authorized video
   paths.
4. Create a deterministic source-video split plan.
5. Create a deterministic timestamp/frame-selection plan.
6. Explicitly extract selected frames locally.
7. Manually annotate clearly visible pigs under the finalized policy.
8. Assign an explicit status to every frame; intentionally reviewed negative
   frames use `verified_empty`.
9. Validate images, YOLO labels, status consistency, source split isolation,
   dimensions, checksums, and duplicates.
10. Generate and retain the sanitized local dataset manifest and validation
    reports.

No import, installation, test, or CI job performs real extraction.

## Workspace

```text
data/annotations/raw/
  images/{train,validation,test,preparation}/
  labels/{train,validation,test,preparation}/
  metadata/
```

All actual contents are ignored. Only repository placeholders are tracked.

## Sanitized manifest

The manifest records schema/policy versions, class map, opaque frame and clip
IDs, split, workspace-relative image path, dimensions, human annotation status,
box count, checksum, and validation state. It rejects source filenames,
absolute paths, reviewer identity, authorization notes, and private notes.

Create a manifest from the sanitized extraction report and a local status map:

```bash
python -m hogflow.annotation.manifest \
  --extraction-report data/annotations/raw/metadata/extraction_report.json \
  --status-map data/annotations/raw/metadata/annotation_status.local.json \
  --output data/annotations/raw/metadata/dataset_manifest.json
```

## Validation

```bash
python -m hogflow.annotation.validation \
  --dataset data/annotations/raw \
  --manifest data/annotations/raw/metadata/dataset_manifest.json \
  --output data/evaluation/annotation_validation.json
```

Validation emits ignored JSON, CSV, and Markdown reports. Fatal conditions
include source split leakage, invalid or malformed YOLO labels, unreadable
images, missing explicit empty status, dimension/checksum mismatch, and
cross-split duplicate content. Findings identify only opaque IDs and controlled
workspace-relative paths.

## Evidence boundary

Synthetic tests validate preparation mechanics, not pig annotation quality or
detector accuracy. Human review remains required, and a passing structural
report is not a model-quality result.
