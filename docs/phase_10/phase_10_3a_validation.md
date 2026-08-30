# Phase 10.3A — Provisional Pig Dataset and Demo Model Validation

Status: **PARTIALLY COMPLETE**

This is an empirical demo/validation record. The model is not production
validated and the two local videos remain ignored, untracked, and local-only.

## Baseline

- Initial SHA: `87037516ffc4ba2fa439a902bb9e45b69fe47c18`
- Branch: `main`
- Working tree at the start: clean
- Baseline suite: `1008 passed, 1 warning`
- Execution environment: Python 3.12.13 in the project-local Phase 10.3A
  environment; CPU-only Torch (`2.13.0+cpu`), Ultralytics `8.4.135`, OpenCV
  `4.14.0`, Supervision `0.29.1`.

The strict Phase 10.3 three-video catalog was not modified. A separate local
manifest authorizes exactly `demo_video_a` and `demo_video_b`.

## Videos and role assignment

| ID | Role | Size | FPS | Frames | Duration | Codec/readability | Suitability notes |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `demo_video_a` | Training + internal temporal calibration | 2868×1320 | 47.23 | 557 | 11.793 s | HEVC; readable | Stationary camera; top-to-bottom alley motion; people and pigs, variable scale/pose, moderate-to-high crowding. Selected as the development source because it provides the longer and more varied usable sequence. |
| `demo_video_b` | Independent holdout validation | 2868×1320 | 31.28 | 583 | 18.637 s | HEVC; readable | Stationary camera; top-to-bottom alley motion; dense groups and substantial overlap/occlusion. Kept unseen by training decisions. |

Both metadata inspections reported a bounded HEVC decode warning while the
files remained readable. The extraction fallback recovered all planned frames;
the maximum planned/actual timestamp difference was below 0.1 s.

The eventual counting geometry should be a horizontal line for this observed
top-to-bottom motion, with confirmation space after the line. The smoke test
used the existing default line only to exercise the pipeline; it is not a
calibrated counting result.

## Dataset and split isolation

- 100 selected frames total; deterministic sampling with explicit temporal
  blocks and no adjacent-frame random mixing.
- Development source (`demo_video_a`): 48 temporal training frames and 16
  separated calibration frames, with a temporal buffer between blocks.
- Independent source (`demo_video_b`): 36 holdout frames only.
- Human annotation: 1,441 pig boxes; 8 natural negative frames; 0 invalid
  annotation lines; class ID `0` maps exclusively to `pig`.
- Split box totals: training 905, calibration 22, holdout 514.
- Development dataset fingerprint:
  `7486f51fad461af63fcd82e22fe56a5a026b6782f28fb4c7a172a6f45ed4cee4`
- Holdout dataset fingerprint:
  `a5b8b9d67f9b9f6ebd33050ae7f92861ff389fd5c235a86d4de4da50737235e6`

The manifest and loader gates confirmed that no holdout frame is in training
or calibration and that the two source clip IDs are disjoint across the
development and holdout datasets.

## Annotation

Annotation was completed manually with the local-only Tkinter helper. The
status map records 92 `annotated` frames and 8 `verified_empty` frames. The
existing YOLO serializer and validation boundary were reused. Development and
holdout validation reports each completed with `0 errors, 0 warnings`.

## Training

- Checkpoint family: official Ultralytics `YOLO11n` pretrained detection
  checkpoint, downloaded once to the ignored training-only area.
- Device: CPU; no CUDA device was available.
- Image size: 640; batch: 4; seed: 42; workers: 0.
- Maximum/actual epochs: 75/75; patience: 20; early stopping enabled.
- Moderate augmentation only (brightness/color, scale/translation, mild
  horizontal flip, and bounded mosaic); no extreme transformations.
- Configuration fingerprint:
  `07713266ad4f645391161e3aaf16c0e6331b466941a6c885b192cf8755e7ea35`
- Training checkpoint selected from the single frozen experiment after the
  development/calibration review.

Framework training metrics (reported separately from HogFlow metrics):

- mAP50: `0.9810200668896323`
- mAP50-95: `0.372374877287457`
- framework precision: `0.9106152807186175`
- framework recall: `0.926621182809556`

## Detection results

HogFlow frame-level metrics use IoU 0.5 and confidence 0.25. They are not
interchangeable with framework mAP.

### Development calibration (`demo_video_a`)

- Frames: 16
- TP: 22; FP: 14; FN: 0
- Precision: `0.6111111111111112`
- Recall: `1.0`
- F1: `0.7586206896551725`

### Independent holdout (`demo_video_b`)

- Frames: 36
- Ground-truth boxes: 514; predicted boxes: 35
- TP: 15; FP: 20; FN: 499
- Precision: `0.42857142857142855`
- Recall: `0.029182879377431907`
- F1: `0.0546448087431694`
- Inference elapsed: 4.457 s (approximately 8.08 FPS)
- Framework mAP was not recomputed for the holdout boundary; the holdout
  result above is the frozen HogFlow evaluator evidence.

The independent result is poor and exposes strong domain/crowding
generalization limits. It is retained as evidence, not filtered out.

## Model artifact and provenance

- Sanitized identity: `hogflow_pig_demo`
- Format/backend: `.pt` / Ultralytics
- Target: class ID `0`, class name `pig`
- Artifact SHA-256:
  `93416e3c0d00fa9b588547f6fa3e92e3afbdecbb836ebca3ad69f5199865144a`
- Model gate: `AVAILABLE`, exactly one compatible candidate
- Provenance: complete, path-free JSON with framework, target class,
  fingerprints, training run, evaluation reference, and selection rationale.

The selected model and provenance remain in ignored local model storage and
are not committed.

## HogFlow integration and smoke test

The final artifact loaded through the Phase 10.2 `PigDetectorConfiguration`
and the existing Ultralytics adapter. A local HMI composition smoke test ran
`demo_video_a` through:

`Detector → Supervision ByteTrack → virtual-line crossing → shared lane counter → operator presenter`

Observed smoke evidence: 539 frames acquired and processed, 539 successful
inferences, 8,595 detections, 539 frames with detections, zero tracker or
crossing failures, and the operator snapshot reached `Lane Occupied` with a
live count of 1. This is an in-sample pipeline smoke test, not counting
accuracy evidence; the default line was not calibrated for this video.

## Counting ground truth

No manual full-video crossing totals have been supplied yet. Therefore:

**BLOCKED — MANUAL CROSSING GROUND TRUTH MISSING**

Detection training and frame-level evaluation are complete, but count error
must not be derived from the annotation boxes or from a human total that has
not been recorded. The required worksheet is:

```text
demo_video_a → manual crossing count: ___
demo_video_b → manual crossing count: ___
```

## Replay safety

An active shared counting lane now blocks both explicit `Restart Video` and
implicit exhausted-file replay through `Start Pipeline`. The presenter also
disables those actions while the lane is occupied. Replay after session
completion/cancellation remains available, and USB behavior is unchanged.

## Limitations

- CPU inference is slow and the current holdout generalization is inadequate.
- Both clips are small, local, and not representative deployment evidence.
- Camera motion, line geometry, track fragmentation, ID switches, and crossing
  accuracy require further controlled review with supplied human totals.
- The default HMI line is not a calibrated line for these videos.

**DEMO MODEL — NOT PRODUCTION VALIDATED.**

## Git and CI

Source/test/documentation changes are intended for one descriptive commit on
`main`; real media, labels, frames, weights, run outputs, and sidecars remain
ignored and untracked. Final commit, push, and remote CI status are recorded
after the last quality-gate run.
