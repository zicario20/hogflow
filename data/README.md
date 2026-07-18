# HogFlow Local Data Workspace

This directory is a local-only workspace for Phase 3 video inventory. It must contain
only public, synthetic, or explicitly authorized data.

## Directory policy

- `raw/` contains original video files. HogFlow inventory tools read but never modify them.
- `interim/` is reserved for local intermediate artifacts, such as manually cut clips.
- `processed/` contains generated inventories and other local outputs.
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
