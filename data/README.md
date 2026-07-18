# HogFlow Local Data Workspace

This directory is a local-only workspace for Phase 3 video inventory. It must contain
only public, synthetic, or explicitly authorized data.

## Directory policy

- `raw/` contains original video files. HogFlow inventory tools read but never modify them.
- `interim/` is reserved for local intermediate artifacts, such as manually cut clips.
- `processed/` contains generated inventories and other local outputs.
- `annotations/` contains local raw, interim, and processed annotation work.
- `models/` contains local checkpoints and model weights.
- `runs/` contains local inference outputs.
- `evaluation/` contains local detector-evaluation reports and derived records.
- Video files, frames, thumbnails, generated media, and model weights are ignored by Git.

Before placing a clip here, confirm that its license or authorization permits project use.
Public visibility alone does not establish reuse rights. Do not add employer media,
confidential facility information, credentials, or personally identifying review notes.

## Suggested clip naming

Use lowercase descriptive names without private source details:

`source-category_scene_yyyymmdd_clip-001.ext`

Example: `authorized-research_alley_20260718_clip-001.mp4`.

Place a review sidecar beside each source clip using the full video filename plus
`.review.json`, for example:

`authorized-research_alley_20260718_clip-001.mp4.review.json`

Copy [review_sidecar.example.json](review_sidecar.example.json) and record only
authorization, license/source reference, scene confirmations, intended use, and non-private
notes. An optional [clip_manifest.example.json](clip_manifest.example.json) records the
boundaries of clips manually cut from longer sources; HogFlow does not cut videos in Phase 3.

Generate a local inventory with:

```bash
python -m hogflow.data.inventory --input data/raw --output data/processed/inventory
```

The command writes JSON, CSV, and Markdown metadata reports. It does not create frames or
thumbnails.

Prepare a metadata-only Phase 4.1 detection-selection plan with:

```bash
python -m hogflow.evaluation.dataset_selection \
  --inventory data/processed/inventory/inventory.json \
  --output data/processed/phase_4/detection_selection.json
```

The plan contains opaque clip IDs rather than private filenames or paths. Phase 4.1 does not
extract frames, create annotations, download weights, run detector inference, or train a model.
All real annotation files, manifests, dataset exports, weights, runs, and evaluation reports
remain local and ignored. Only the documented examples and `.gitkeep` placeholders may be
tracked.

## Phase 4.2 local preparation workflow

After Phase 4.1 selection:

1. Create a source-level split plan with `hogflow.data.dataset_splitting`.
2. Create an ignored local source map that resolves opaque clip IDs to authorized files.
3. Plan timestamps with `hogflow.data.frame_selection`; planning does not decode video.
4. Explicitly extract frames with `hogflow.data.frame_extraction`.
5. Annotate pigs manually using the finalized `0 = pig` policy and YOLO text format.
6. Mark every frame `annotated`, `verified_empty`, `needs_manual_review`, or `excluded`.
7. Build the sanitized manifest with `hogflow.annotation.manifest`.
8. Validate the local dataset with `hogflow.annotation.validation`.

Frames from one original source must remain in one split. Empty labels are created only after
human confirmation of `verified_empty`; extraction never creates labels. Source maps, split
plans, frame plans, images, labels, status maps, manifests, annotation-tool projects, and
reports are local-only and Git-ignored.

See [the Phase 4.2 workflow](../docs/phase_4/phase_4_2_local_annotation_dataset.md) and
[the finalized annotation policy](../docs/phase_4/phase_4_annotation_policy.md).
