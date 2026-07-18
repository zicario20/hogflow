# Phase 4.2 — Frame Planning and Local Extraction

## Plan before decoding

`hogflow.data.frame_selection` combines the Phase 4.1 selected opaque IDs, the
source-level split plan, and Phase 3 duration metadata. It does not open video.

Supported deterministic strategies are:

- `fixed_interval`: select timestamps at a configured interval;
- `target_count`: distribute a requested number across the usable duration;
- `bounded_uniform`: distribute an interval-derived count while respecting the
  per-clip maximum.

All strategies support start/end exclusion margins and a maximum frame count.
When margins consume a short clip, one midpoint is planned and an explicit
warning is recorded. Frame IDs are hash-derived from opaque clip ID, strategy,
and timestamp.

```bash
python -m hogflow.data.frame_selection \
  --selection data/processed/phase_4/detection_selection.json \
  --split-plan data/processed/phase_4/source_split_plan.json \
  --inventory data/processed/inventory/inventory.json \
  --output data/processed/phase_4/frame_selection_plan.json \
  --strategy fixed_interval \
  --interval-seconds 1.0 \
  --maximum-frames 100
```

The sanitized plan contains only opaque clip/frame IDs, split, timestamp,
strategy, and the `planned` extraction placeholder.

## Local source map

Extraction uses a separate ignored JSON source map:

```json
{
  "format_version": 1,
  "sources": {
    "000000000000000000000001": "<local-authorized-video-path>"
  }
}
```

The map is local-only. It must never be printed, committed, uploaded, included
in an exception, attached to CI, or copied into a sanitized manifest.

## Extraction command

```bash
python -m hogflow.data.frame_extraction \
  --plan data/processed/phase_4/frame_selection_plan.json \
  --source-map data/processed/phase_4/local_source_map.json \
  --output data/annotations/raw \
  --format jpg
```

Extraction:

- reads source videos without modifying them;
- performs bounded timestamp seeking;
- writes JPEG or PNG using opaque frame names;
- preserves source-level split directories;
- records planned/actual timestamps, dimensions, and checksums;
- atomically creates new image files;
- verifies matching existing files on rerun;
- refuses to overwrite mismatched existing content; and
- never creates annotation labels automatically.

The extraction report is sanitized and local. Empty labels are created later
only after a human assigns `verified_empty`.
