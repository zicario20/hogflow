# Phase 4.1 — Summary

## Status

Phase 4.1 infrastructure implemented. Real pig annotation is not completed, no pig detector
has been trained or validated, no accuracy claim exists, and Phase 4.2 has not started.

## Delivered

- GitHub Actions CI for source-only quality gates on `main` pushes and pull requests;
- immutable framework-neutral pig-detection evaluation models;
- explicit pixel and normalized coordinate handling around the canonical bounding box;
- deterministic area, intersection, union, IoU, one-to-one matching, TP, FP, FN, precision,
  recall, and F1 utilities;
- explicit zero-denominator metric behavior;
- metadata-only Phase 3 inventory selection with opaque clip IDs and rejection reasons;
- atomic local JSON preparation-plan output;
- protected annotation, model, run, and evaluation workspaces;
- architecture and data-hygiene checks; and
- synthetic tests without real media, weights, inference, or annotations.

## Architecture result

Evaluation models and metrics remain independent of OpenCV, NumPy, Ultralytics, Supervision,
Torch, detector implementations, trackers, counting, sessions, storage, and UI code. Dataset
selection reads inventory JSON but never video content. The existing generic detector contract
and Phase 1/2 pipeline behavior remain unchanged.

## Evidence boundary

The tests validate deterministic geometry, matching, metrics, model invariants, metadata-only
selection, output privacy, CI configuration, and Git protections using synthetic values. They
do not validate pig detection, annotation quality, mAP, tracking, counting, generalization, or
operational value.

## Known limitations

- No real pig annotation has been completed.
- No annotation format has been finalized.
- No detector has been trained, fine-tuned, loaded, or evaluated.
- No mAP calculation is implemented.
- No frame extraction or annotation conversion exists.
- No tracking or counting evaluation is included.
- Confidence and IoU thresholds remain future experimental choices.

## Roadmap boundary

Phase 4 remains in progress. Phase 4.1 provides foundations only; Phase 4.2 has not started.
