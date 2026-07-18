# Phase 4 — Annotation Policy Draft

## Status

This Phase 4.1 draft is retained as historical design context. It was
superseded by [the finalized Phase 4.2 annotation policy](phase_4_annotation_policy.md).
No claim is made that real annotation is complete.

## Local-only workspace

```text
data/
├── annotations/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── models/
├── runs/
└── evaluation/
```

All contents are Git-ignored except `.gitkeep` placeholders. Annotations, images, manifests,
dataset exports, weights, runs, and reports must never be committed, uploaded, placed in Git
LFS, attached to CI, copied into tests, or published.

## Candidate interoperable formats

Future annotation work may evaluate:

- YOLO text bounding boxes with explicit class mapping and normalized coordinates;
- COCO JSON with pixel-coordinate boxes and source-image metadata; or
- another documented interoperable format selected before annotation begins.

No format is approved merely by being listed. A later decision must document coordinate
conventions, class IDs, metadata requirements, conversion validation, and tool compatibility.

## Draft object policy

- One bounding box should contain one pig.
- Humans, equipment, truck structures, shadows, and markings must not be labeled as pigs.
- A partially visible pig may be annotated only under an explicit future visibility policy.
- Ambiguous, heavily occluded, or inseparable animals require a documented include/exclude or
  uncertainty policy; annotators must not guess silently.
- Box boundaries should follow one consistently documented visible-body or full-extent rule.
- Difficult examples must not be removed merely to improve detector results.
- Annotation revisions require traceable local version notes without exposing source details.

These rules are incomplete until an authorized annotation pilot establishes examples and
inter-reviewer guidance.

## Dataset leakage prevention

Train, validation, and test separation must occur at the original source-video level—not at
the extracted-frame level. Frames from one original video are highly correlated and must never
be distributed across multiple splits, even when filenames, clips, or frame timestamps differ.

Any future split manifest must use opaque source-video IDs and verify:

- each source appears in exactly one split;
- derived clips inherit the original source split;
- extracted frames inherit the original source split;
- near-duplicate exports do not cross splits; and
- no test source is used for training decisions or threshold tuning.

## Future review gates

Before real annotation begins, Phase 4.2 should explicitly approve:

1. authorized selected source videos;
2. one annotation format and class mapping;
3. visibility and occlusion rules;
4. frame-sampling strategy;
5. source-video-level split assignment;
6. quality-review procedure; and
7. local backup and deletion policy.

Phase 4.1 does not satisfy these evidence gates by itself.
