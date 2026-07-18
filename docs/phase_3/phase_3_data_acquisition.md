# Phase 3 — Pig Video Data Acquisition

## Purpose

Phase 3 establishes a safe, repeatable local workflow for collecting and reviewing pig-video
clips that may later support detection, tracking, and counting research. It does not train a
model, evaluate tracking, measure count accuracy, or prove that any clip is suitable for a
later experiment.

Phase 3 infrastructure can be used with an empty dataset. Real authorized dataset collection
and review may continue after the infrastructure is installed.

## Authorization boundary

Use only clips that are:

- created by the project owner for this project;
- explicitly authorized by the rights holder;
- distributed under a license that permits the intended project use; or
- public-domain material whose status has been verified.

Public visibility is not permission to copy or reuse media. Do not download videos from
YouTube or another website as part of this workflow. Record the source category, a non-secret
source reference, and permission or license notes in the adjacent review sidecar before using
a clip as a candidate. Do not put credentials, personally identifying information,
confidential facility details, or employer information in a sidecar.

## Local data layout

```text
data/
├── raw/        # original source videos; read-only to HogFlow tools
├── interim/    # local intermediate artifacts or manually cut clips
├── processed/  # generated local inventories
└── README.md
```

Originals belong only in `data/raw/` and must not be modified. Video content under all three
working directories is ignored by Git. Generated frames, thumbnails, media, and model weights
must not be committed.

## Recommended clip characteristics

The inventory benefits from clips with:

- enough duration to observe consecutive movement rather than one isolated frame;
- valid dimensions, frame rate, and decoding;
- a camera that appears stationary for tracking-oriented review;
- visible animals at useful scale and lighting for later detection research;
- a clear constrained passage, predominant movement direction, and plausible virtual-line
  location for later counting research; and
- limited edits that preserve temporal continuity.

These are review characteristics, not guarantees. Dense groups, occlusion, changing light,
moving cameras, compression damage, and difficult angles can be retained as stress-test
material when authorization permits.

## Candidate categories

- `detection_candidate`: authorized, readable, technically valid, and long enough for basic
  frame-level research.
- `tracking_candidate`: a detection candidate with sufficient consecutive duration and no
  clear moving-camera evidence.
- `counting_candidate`: a tracking candidate whose sidecar manually confirms a static camera,
  clear passage or gate, predominant direction, and usable line location.
- `stress_test_candidate`: authorized difficult material, including a moving camera, that may
  be useful for robustness testing rather than normal counting.
- `needs_manual_review`: authorization, scene evidence, stability evidence, or technical
  validity is incomplete.

These labels organize an inventory. They do not claim detector quality, tracker quality,
counting accuracy, legal advice, or commercial validation.

## Manually selecting static sections

When an authorized long source contains camera movement, inspect it with a local editor and
manually identify intervals where the camera appears stationary. Preserve the original in
`data/raw/`. Export any selected clip to `data/interim/` or place a separately authorized
already-cut clip in the appropriate local workspace. Do not overwrite or transcode the raw
source in place.

Record each selected interval in the optional clip manifest:

- original source reference;
- clip filename;
- start and end time;
- reason selected;
- whether the camera appears static; and
- notes.

Phase 3 records boundaries but does not implement video cutting. Human confirmation remains
necessary because foreground animal motion can confuse automatic camera-motion estimates.

## File naming

Use lowercase, descriptive filenames without confidential source details:

`source-category_scene_yyyymmdd_clip-001.ext`

Keep the same base filename when adding the `.review.json` suffix, for example:

`authorized-research_alley_20260718_clip-001.mp4.review.json`

## Phase boundary

Phase 3 does not include pig-detector training, fine-tuning, pig tracking validation,
count-error evaluation, sessions, persistence, UI, analytics, or a pilot. Those remain in
their approved later roadmap phases.
