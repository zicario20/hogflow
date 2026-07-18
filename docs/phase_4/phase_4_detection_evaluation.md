# Phase 4 — Detection Evaluation Foundation

## Purpose

This document defines the Phase 4.1 evaluation language and deterministic basic metrics for a
future pig detector. It contains infrastructure, not experimental results.

## Evaluation models

`EvaluationBoundingBox` wraps the canonical immutable `hogflow.models.BoundingBox` and adds an
explicit coordinate space:

- `pixel`: non-negative frame coordinates, checked against frame width and height; or
- `normalized`: coordinates constrained to `[0, 1]`.

Pixel and normalized boxes cannot be compared directly. Invalid, non-finite, negative,
zero-area, reversed, out-of-frame, or out-of-range boxes are rejected.

The evaluation domain also defines:

- `GroundTruthDetection`: one human reference box and class label;
- `PredictedDetection`: one box, class label, and confidence in `[0, 1]`;
- `DetectionFrame`: immutable ground truth and predictions for an opaque source-video/frame ID;
- `DetectionMatch`: one one-to-one match and its IoU;
- `DetectionEvaluationResult`: aggregate TP, FP, FN, precision, recall, and F1;
- `DetectionClassSummary`: per-class structural counts; and
- `DetectionDatasetSummary`: source, frame, ground-truth, prediction, and class totals.

The initial class label is `pig`, while non-empty framework-neutral class labels remain
representable for diagnostic false-class tests. Humans must never be represented as pigs in
ground truth.

Source IDs are opaque identifiers rather than filenames or paths. Keeping source-video ID
explicit supports future leakage-safe dataset splitting.

## Geometry

For two compatible boxes:

```text
intersection = overlapping area
union = area(A) + area(B) - intersection
IoU = intersection / union
```

Non-overlapping boxes have IoU 0. Identical boxes have IoU 1. Coordinate-space mismatches are
input errors.

## Deterministic one-to-one matching

Evaluation processes frames by `(source_video_id, frame_id)`. Within each frame:

1. predictions are ordered by descending confidence;
2. equal-confidence predictions are ordered by prediction ID;
3. only ground truth with the same class is considered;
4. each prediction chooses the unmatched ground truth with greatest IoU at or above the
   configured threshold;
5. equal-IoU ground truths are ordered by ground-truth ID; and
6. matched predictions and ground truth are removed from further matching.

Therefore each prediction and ground-truth box can participate in at most one match. Duplicate
predictions become false positives after the highest-priority prediction receives the match.

The threshold must be greater than 0 and at most 1. Phase 4.1 defaults to 0.5 but makes no
claim that this is the final experimental threshold.

## Metrics

```text
TP = matched predictions
FP = unmatched predictions
FN = unmatched ground truth
precision = TP / (TP + FP)
recall = TP / (TP + FN)
F1 = 2 * precision * recall / (precision + recall)
```

When a denominator is zero, the corresponding metric is explicitly defined as `0.0`. Result
models validate consistency between counts, matches, thresholds, and metric values.

## Deliberate exclusions

Phase 4.1 does not implement mAP, precision-recall integration, confidence sweeps, detector
inference, annotation conversion, model loading, training, tracking metrics, or counting
metrics. No mAP claim should be made until a complete, independently verified implementation
or accepted evaluation library is approved in a future subphase.

Detection precision, recall, and F1 will remain diagnostic. They cannot by themselves validate
HogFlow as a counting system.
