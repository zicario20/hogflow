# Phase 4.2 — Pig Detection Annotation Policy

## Status and scope

This is the finalized Phase 4.2 local annotation policy, version
`phase-4.2-v1`. It defines how future authorized frames must be labeled for
pig detection. It does not state that real annotation is complete and provides
no detector-performance evidence.

The single detection class is:

```text
0 = pig
```

Humans and all non-pig objects are excluded from this class.

## Bounding-box rules

1. Create one bounding box for each visible pig.
2. Enclose the visible extent of the pig tightly and consistently.
3. Do not annotate humans.
4. Do not annotate trucks, gates, shadows, equipment, markings, or other objects.
5. Do not infer or hallucinate the hidden full body of an occluded pig.
6. Annotate a partial pig at an image boundary only when its visible portion is
   clearly identifiable. Clip the box to the image boundary; coordinates must
   never extend outside the image.
7. Annotate an occluded pig only when its visible portion is clearly
   identifiable and can be localized. Do not annotate ambiguous identity or
   location.
8. For heavily overlapping pigs, create separate boxes only when individuals
   can be distinguished. Otherwise mark the frame `needs_manual_review` or
   `excluded`.
9. Annotate tiny or distant pigs only when clearly identifiable. Do not label
   ambiguous shapes.
10. Reflections, screens, posters, and other images of pigs are not real pigs
    and must not be annotated.
11. A pig crossing an image edge may be annotated when clearly identifiable,
    using a box clipped to the image.
12. Apply the same decision rules across every source and split. Uncertainty
    must be recorded, not silently guessed away.

## Frame-level annotation status

Every extracted frame requires exactly one explicit status:

- `annotated`: a human confirmed one or more pig boxes;
- `verified_empty`: a human confirmed that no pig is present;
- `needs_manual_review`: the frame is unresolved and must not enter training;
- `excluded`: the frame is intentionally omitted and must not enter training.

A frame with no boxes is not automatically annotated or empty. Only a human
confirmation may assign `verified_empty`. Empty frames are useful intentional
negative examples, but they must be reviewed and represented by an empty label
only after that status is recorded.

`needs_manual_review` and `excluded` frames must not have YOLO label files.

## Operational YOLO format

Phase 4.2 uses local YOLO object-detection text as its operational interchange
format. YOLO is a serialization choice, not an Ultralytics dependency.

Each non-empty line is:

```text
<class_id> <x_center> <y_center> <width> <height>
```

Rules:

- class ID is exactly `0`;
- coordinates are finite and normalized to `[0.0, 1.0]`;
- width and height are greater than zero;
- the box remains within image boundaries;
- one UTF-8 label file matches one image stem;
- lines use deterministic geometric ordering;
- duplicate boxes are forbidden;
- malformed, non-finite, or out-of-range values are errors; and
- an empty label is valid only for an explicitly `verified_empty` frame.

## Review and leakage controls

Train, validation, and test separation occurs at original source-video level.
All frames and derived clips from one source inherit the same split. Frames
from one source must never be distributed across splits.

Real images, labels, status maps, manifests, source maps, reports, and tool
projects remain local and Git-ignored. CI uses synthetic fixtures only.
