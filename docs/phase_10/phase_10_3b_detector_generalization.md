# Phase 10.3B — Detector V1 Error Analysis and Generalization Improvement

Status: **PARTIAL — NEW INDEPENDENT HOLDOUT REQUIRED**

This is a bounded empirical subphase under Phase 10.3. It preserves the
Phase 10.3A record, improves the provisional detector using consumed
development evidence, and does not make a production claim.

## Baseline and V1 historical evidence

- Baseline SHA: `995897b32ebe3e8034fd980ac36fb6ab69ee70b1`
- Branch: `main`
- Working tree at start: clean; the baseline suite was `1061 passed, 1 warning`
  (the inherited ByteTrack deprecation warning).
- V1 artifact: `hogflow_pig_demo`, SHA-256
  `93416e3c0d00fa9b588547f6fa3e92e3afbdecbb836ebca3ad69f5199865144a`.
- V1 model/configuration/dataset provenance and the Phase 10.3A report remain
  unchanged. V1 B was a valid independent holdout for V1.

Historical V1 results at confidence `0.25`, IoU `0.5`, and image size `640`:

| Evidence | Frames | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A development calibration | 16 | 22 | 14 | 0 | 0.6111 | 1.0000 | 0.7586 |
| B original independent holdout | 36 | 15 | 20 | 499 | 0.4286 | 0.0292 | 0.0546 |

The B row is immutable historical evidence. It is not replaced by later
diagnostic or V2 results.

## B failure analysis

### Integrity audit

The exact 36 B images and labels were rechecked. Image/label mismatch, invalid
checksums, dimension mismatch, unreadable raw frames, raw-dimension mismatch,
and orientation/frame-ID defects were all `0`. Timestamp extraction error was
bounded below `0.1 s`, and decoded-image/raw-frame histogram correlation had a
minimum of `0.99705`. No evaluation or coordinate-space defect was found.

### Visual review and root cause

Six bounded overlays were reviewed locally (ground truth green, V1 prediction
red). Five of six were dense multi-pig scenes with severe under-detection; two
also contained a person/gate obstruction. These qualitative categories are
non-exclusive and are not stored as a frame history.

Measured differences support a **MIXED** root cause:

- **Primary:** scene/domain and illumination/composition shift plus training
  coverage bias. A training pigs' median normalized vertical center was `0.753`
  versus `0.538` in B; B was materially brighter (median frame gray mean
  `61.97` versus `41.91` in A training) and distributed pigs across more of the
  image. A calibration was sparse (median `1` pig/frame), so its strong score
  overstated generalization.
- **Secondary:** B was more crowded. Pairwise GT box pairs with IoU `>0.1`
  were `84/4167` (`2.0%`) versus `53/8510` (`0.6%`) in A training.
- **Not supported as primary:** B objects were not smaller than A training
  objects. Using project bins (small `<32²` resized pixels, medium `<96²`,
  large `>=96²`), B had 266 small and 248 medium boxes, while A training had
  783 small and 122 medium. No max-detection cap or evaluator defect was found.

### Confidence, IoU, and resolution diagnostics

The raw B V1 output at confidence `0.05` contained 417 candidates (median
confidence `0.1072`, p90 `0.2301`); matched TPs had median `0.1305`. The
post-hoc confidence sweep was diagnostic only:

| Confidence | TP | FP | FN | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 67 | 350 | 447 | 0.1607 | 0.1304 | 0.1439 |
| 0.10 | 45 | 188 | 469 | 0.1931 | 0.0875 | 0.1205 |
| 0.15 | 30 | 97 | 484 | 0.2362 | 0.0584 | 0.0936 |
| 0.20 | 21 | 48 | 493 | 0.3043 | 0.0409 | 0.0720 |
| **0.25 (historical)** | **15** | **20** | **499** | **0.4286** | **0.0292** | **0.0546** |
| 0.30 | 9 | 12 | 505 | 0.4286 | 0.0175 | 0.0336 |
| 0.40 | 1 | 5 | 513 | 0.1667 | 0.0019 | 0.0038 |
| 0.50 | 0 | 0 | 514 | 0.0000 | 0.0000 | 0.0000 |

Fixed-output IoU sensitivity at the historical threshold gave TP `26/20/15/9/4`
for IoU `0.30/0.40/0.50/0.60/0.70`; predictions were mostly absent rather than
merely poorly localized. V1 resolution diagnostics were also negative:

| Image size | TP | FP | FN | Precision | Recall | F1 | FPS |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 640 | 15 | 20 | 499 | 0.4286 | 0.0292 | 0.0546 | 18.67 |
| 960 | 1 | 26 | 513 | 0.0370 | 0.0019 | 0.0037 | 14.65 |
| 1280 | 0 | 92 | 514 | 0.0000 | 0.0000 | 0.0000 | 11.17 |

Ultralytics used class filter `[0]`, confidence `0.25`, NMS IoU `0.5`, and
`max_det=300`. B's maximum V1 predictions/frame was `3` (not a suspicious
constant cap); a controlled max-det comparison did not change the output.

The complete bounded diagnostic data and local overlays remain ignored under
the local evaluation workspace; no media or predictions are committed.

## B evidence role for V2

**V1 independent holdout = yes. V2 independent holdout = no.**

After inspection, B is consumed hard-development evidence for V2. It may be
used for V2 development and calibration, but it must never be described as an
unseen V2 holdout.

## V2 development dataset

The existing 100 human-reviewed A/B frames and all 1,441 class-0 `pig` boxes
were reused. There were 8 natural negative frames and 0 invalid annotations.
No new labels or pseudo-labels were fabricated.

- Dataset ID: `phase10-3b-v2-development`
- Fingerprint: `948a43612c32d734cb27333b36ac00da5212645b78c4c9a3fe14cbceac24e47a`
- Training: 79 frames, 1,320 boxes (A: 48; B: 31)
- Internal calibration: 21 frames, 121 boxes (A: 16; B: 5)
- Split: source-aware temporal blocks with positive buffer gaps; no neighboring
  frame random mixing, frame duplication, or cross-split overlap.
- A and B are both development sources for V2. The old A/B role and V1
  fingerprints remain reproducible in the Phase 10.3A workspace.

## V2 experiment and selection

One controlled candidate was sufficient after diagnosis:

| Run | Model | Device | Size | Epochs | Batch | Threshold | Internal TP/FP/FN | Precision | Recall | F1 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| `phase10_3b_yolo11n_640_gpu` | YOLO11n fine-tuned from official `yolo11n.pt` | RTX 5070 Ti / CUDA | 640 | 75/75 | 8 | 0.25 | 86/31/35 | 0.7350 | 0.7107 | 0.7227 |

The internal result is over the frozen 21-frame A+B calibration split. The
framework reported mAP50 `0.7400`, mAP50-95 `0.2261`, precision `0.7610`, and
recall `0.6860`; these values are kept separate from HogFlow TP/FP/FN metrics.
The internal threshold sweep selected the existing `0.25` operating point by
F1 (0.7227 versus 0.7092 at 0.20 and 0.7168 at 0.30). No architecture search
was needed; resolution was not the diagnosed bottleneck.

Environment and effective settings: Python `3.12.14`, Ultralytics `8.4.135`,
Torch `2.11.0+cu128`, CUDA device `NVIDIA GeForce RTX 5070 Ti Laptop GPU`,
image size `640`, seed `42`, workers `0`, patience `20`, moderate augmentation,
NMS IoU `0.5`, and max detections `300`. A preliminary CPU attempt was stopped
before completion and is not an evidence result.

### Post-hoc B development comparison

With the selected V2 configuration, all 36 historical B frames yielded 474
predictions: TP `367`, FP `107`, FN `147`, precision `0.7743`, recall `0.7140`,
F1 `0.7429`, mean matched IoU `0.6931`, zero-prediction frames `0`, and
approximately `12.30 FPS` in this bounded batch. This is a **post-hoc
development comparison**, not independent V2 evidence. Three bounded V2
overlays were also reviewed: boxes follow the visible pigs in the sampled
frames, while overlap and occasional duplicate/shifted boxes remain.

## Selected artifact and gate

- Identity: `hogflow_pig_demo_v2`
- Format/backend: `.pt` / Ultralytics
- SHA-256: `892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c`
- Target: class ID `0`, class name `pig`
- Provenance: complete, path-free local JSON with framework, Torch/device,
  dataset/configuration fingerprints, thresholds, seed, run, and limitation.
- Phase 10.3 model gate: **AVAILABLE**, exactly one active compatible candidate.
  The V1 artifact and provenance were moved to ignored historical training
  storage with the original SHA unchanged; the generic pretrained checkpoints
  remain outside the approved validation model roots.

## HogFlow runtime integration

V2 was loaded through the existing `PigDetectorConfiguration` and
`UltralyticsLiveDetector` boundary, then exercised through the existing
`Supervision ByteTrack → crossing → SharedCountingLane → Operator Presenter/HMI`
composition. Full A smoke evidence: 539 frames acquired/processed, 539
successful inferences, 7,001 detections, 512 frames with detections, zero
detector/tracker/crossing failures, runtime device `cuda:0`, pipeline effective
FPS `23.39`, average latency `20.36 ms`, and maximum latency `1547 ms`.
The default vertical line produced a technical live count of `1`; because the
observed motion is top-to-bottom, the eventual line must be horizontal with
confirmation margin. This value is not count-accuracy evidence.

The active-session replay guard remains in force: replay is blocked while a
counting session is active and requires a fresh lifecycle after completion or
cancellation.

## New independent holdout C

**BLOCKED — NEW INDEPENDENT HOLDOUT REQUIRED.** No C was selected because the
raw workspace contains multiple additional candidates and none was explicitly
authorized for this subphase. V2 has not made an independent-generalization
claim. The next authorized input must be exactly one newly identified video,
assigned `demo_video_c`, not previously inspected for V2 decisions. It needs
30–60 representative frames with human `pig` boxes before one frozen C
evaluation.

## Counting ground truth

Manual full-video crossing totals remain unknown. No count error is calculated:

```text
demo_video_a → manual crossing count: ___
demo_video_b → manual crossing count: ___
```

The totals, when supplied, will support only system-count difference/absolute
error/percentage error under the existing crossing semantics; they cannot be
used as detector precision or recall ground truth.

## Limitations and scope lock

- A and B are short local development footage and do not represent a JBS
  deployment environment.
- B is consumed for V2; only a new unseen C can support an independent V2
  generalization statement.
- Tracking fragmentation, ID switches, calibrated line placement, and count
  accuracy still require controlled review with human crossing totals.
- No persistence, analytics dashboard, business-rule redesign, or future phase
  was started.

**DEMO MODEL — NOT PRODUCTION VALIDATED.**

## Source control and CI

Only the multi-source temporal manifest policy, its source-only tests, this
sanitized report, the execution plan, and the project-memory update are
eligible for source control. Videos, frames, labels, overlays, checkpoints,
local sidecars, and reports containing private paths remain ignored and
untracked. Final test, commit, push, and remote-CI results are recorded after
the quality gates complete.
