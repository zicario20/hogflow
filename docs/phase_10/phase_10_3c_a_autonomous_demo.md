# Phase 10.3C-A — Autonomous Counting Calibration & AI Consistency Validation

Status: **PARTIAL — AUTONOMOUS DEMO EXECUTED; FORMAL HUMAN VALIDATION REMAINS BLOCKED**

**AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED**

This is a bounded development demonstration under Phase 10.3. It does not
replace or weaken the formal Phase 10.3C workflow in
`phase_10_3c_independent_validation.md`. That document remains blocked on the
A/B manual crossing worksheet and a separately authorized, annotated Video C.

## Frozen runtime

- Detector identity: `hogflow_pig_demo_v2`
- Artifact SHA-256: `892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c`
- Detector: YOLO11n / Ultralytics 8.4.135
- Target: class `0`, `pig`
- Inference: 640, confidence `0.25`, NMS IoU `0.50`, maximum detections `300`
- Runtime: Python 3.12.14, Torch 2.11.0+cu128, CUDA 12.8, RTX 5070 Ti Laptop
- ByteTrack fingerprint: `a7dff46135c238a62d7658d9878e85909ddb63ce30ae53344bf133fef6594c89`
- Detector configuration fingerprint: `611a4b66efe97b38ef1aa07f5cace4d57aa366ccf1d9b4e4f50a703fc11191c0`

No detector, tracker, crossing, or counter architecture was duplicated. The
executed chain was:

`Frozen detector → ByteTrack → bounded trajectories → existing virtual line → existing LifecycleDirectionalCounter → LIVE COUNT`

## Evidence semantics

The first pass inferred a dominant motion direction and a finite line from
bounded tracker trajectories. Candidate lines were compared only with
directional purity, neighbor-line stability, continuity, detector-threshold
stability, and related self-consistency indicators. The second pass reset the
source, detector, tracker, crossing lifecycle, and counter before counting.

The reported scores are **AUTONOMOUS CONSISTENCY SCORES**, not exactitud, recall,
precision, F1, ground truth, or a human-equivalent count. No manual crossing
total was supplied for any run.

## Development videos A and B

Video B was the historical independent V1 holdout, but it was consumed during
Phase 10.3B diagnosis. It is therefore development evidence here, not an
independent holdout for this autonomous path.

| ID | Status | Confidence | Eligible tracks | Direction purity | Consistency score | Primary count | Crossing events | Frames | Count FPS |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `demo_video_a` | READY | MEDIUM | 50 | 0.9847 | 0.9451 | 31 | 31 | 539 | 8.49 |
| `demo_video_b` | READY | HIGH | 47 | 0.9926 | 0.9759 | 29 | 31 | 575 | 7.47 |

Calibration FPS was 7.62 for A and 7.71 for B. Mean detector latency was
72.70 ms for A and 73.50 ms for B. Threshold diagnostics were stable but not
an external validation: A produced counts 14 and 12 at confidences 0.20 and
0.30; B produced 19 and 19. Neighbor-line counts were `(16, 16, 13, 13)` for
A and `(18, 18, 16, 17)` for B.

The inferred motion was predominantly top-to-bottom in both development
videos. The selected lines were horizontal/near-horizontal finite normalized
segments, with positive direction `negative_to_positive`.

## Deterministic autonomous candidate

The local approved root contained 11 unclassified candidates after excluding
A, B, and the three historical stress videos. Candidates were ordered by the
SHA-256 of their case-folded basename. Suitability probing was bounded and
performed before any result comparison; five candidates were rejected for
insufficient probe evidence. The first suitable candidate in that order was
assigned the sanitized ID `autonomous_demo_video_1` at selection rank 6.

Sanitized metadata: 848 × 384, 45.262 FPS, 894 frames, 19.752 seconds.
Selection key:
`a9a4fd422074ddf362e0334116cd1786a733daf5b0cb72dc55cecca7c4f77d32`.

The candidate was run exactly once after selection. It was not selected because
of its count or consistency result.

## Autonomous demo result

| Field | Result |
| --- | --- |
| Calibration status | READY |
| Calibration confidence | MEDIUM |
| Eligible tracks | 37 |
| Direction purity | 0.6650 |
| Autonomous consistency score | 0.8727 |
| Neighbor-line counts | `(2, 3, 3, 2)` |
| Detector-threshold diagnostics | `(0.20 → 6, 0.30 → 6)` |
| Primary count | 7 |
| Crossing events | 9 |
| Frames | 894 calibration + 894 count |
| Calibration FPS | 14.56 |
| Count-pass FPS | 9.33 |
| Mean detector latency | 86.99 ms |
| Geometry fingerprint | `3b3bd48107614161aaf25339a3bdada4736e23aa843a9698b427dbb85457568c` |

The live path reached `LIVE COUNT`. Calibration itself emitted zero business
crossing events. The count pass began again at frame sequence zero after the
explicit lifecycle reset.

## Ground truth and formal validation

The following values remain unknown and must not be inferred from the
autonomous count:

```text
demo_video_a → manual crossing count: ___
demo_video_b → manual crossing count: ___
```

Consequently, no count difference or percentage result is reported. A new
Video C is still required for an independent detector evaluation. Until C is
authorized, annotated, and evaluated once with the frozen configuration, the
formal Phase 10.3C verdict remains blocked.

## Safety and governance

- All processing remained local; no video or frame was uploaded.
- Videos, frames, labels, model weights, and aggregate local outputs remain
  ignored and untracked.
- The existing replay guard and lifecycle semantics remain authoritative.
- The autonomous layer stores bounded scalar summaries only; it does not retain
  frames, tensors, or private paths.
- The default `run` command and the formal human-ground-truth report were not
  weakened.

**DEMO MODEL — NOT PRODUCTION VALIDATED.**

## Phase 10.3C-A.2 — Manager Demo Runtime Polish

The autonomous demo now uses the existing `LatestPreviewFrameChannel` as a
single replaceable slot shared with the normal preview path. During both
passes, the worker publishes only the newest immutable `PreviewFrame`; the Tk
thread consumes it on the existing bounded refresh cadence. Calibration keeps
candidate geometry hidden. After a READY or LOW lock, exactly the selected
finite line is rendered.

PASS 2 emits bounded `AutonomousDemoProgress` values for each processed frame.
The application snapshot carries the current technical `live_count`, frame
progress, crossing-event total, and latest preview. The manager therefore sees
the video restart and the LIVE COUNT advance during COUNTING; the value never
mutates Phase 8 lane, dock, truck, or session totals.

`AutonomousDemoController` owns a cooperative `threading.Event`. `CANCEL AUTO
DEMO` and application shutdown request the stop, the orchestration checks it
between frames and passes, and the non-daemon worker is joined with a bounded
timeout. Cancellation is represented as `CANCELLED`, not `FAILED`; stale
autonomous preview is cleared before normal mode resumes.

The Auto Demo action is gated on an explicit local frozen V2 configuration:
`pig` class 0, confidence 0.25, IoU 0.50, image size 640, `max_det` 300, no
half precision, and the expected V2 artifact fingerprint. Empty or mismatched
detector configuration remains unavailable. The pipeline panel shows a compact
`DEMO MODEL LOADED`/`NOT LOADED` status and keeps the informational LIVE MODE
badge blue.

The HMI states are `CALIBRATING`, `AUTO CALIBRATION READY`, `COUNTING`,
`COMPLETE`, `LOW CONSISTENCY`, `AUTOCALIBRATION INCONCLUSIVE`, and
`CANCELLED`. LOW remains an amber warning through completion; INCONCLUSIVE
never starts PASS 2. The runtime remains a technical self-consistency demo:

**AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED**

**DEMO MODEL — NOT PRODUCTION VALIDATED.**

The result is useful as an operator/demo consistency check and as evidence that
the frozen detector can feed HogFlow's existing tracker, crossing, counter, and
HMI path. It is not a deployment approval, certification, or a measured human
count comparison.

## Consistency Hardening — Phase 10.3C-A.1

The original A/B/demo values above are preserved as pre-hardening historical
evidence. They are not overwritten or reinterpreted. The hardening algorithm is
versioned as `phase_10_3c_a_v2` and includes the primary count in both line-band
and detector-perturbation families, robust median/range aggregates, finite-line
corridor coverage, track-loss-near-line ratio, and crossing-local continuity.

Post-hardening reruns used the same frozen V2 detector and the same three local
videos only. No formal Video C was inspected, selected, or evaluated.

| Source ID | Status | Consistency | Eligible | Primary | Line range / median | Detector range / median | Score | Corridor | Lost-near-line | Local continuity | Reason codes |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| `demo_video_a` | READY | HIGH | 50 | 32 | 30–33 / 32 | 32–32 / 32 | 0.9566 | 1.0000 | 0.0976 | 0.8750 | `CONSISTENT_INTERNAL_EVIDENCE`, `HIGH_DIRECTION_PURITY` |
| `demo_video_b` | READY | HIGH | 47 | 30 | 28–30 / 29 | 29–30 / 29 | 0.9538 | 1.0000 | 0.0000 | 0.8667 | `CONSISTENT_INTERNAL_EVIDENCE`, `HIGH_DIRECTION_PURITY` |
| `autonomous_demo_video_1` | READY | LOW | 37 | 6 | 3–6 / 4 | 4–5 / 4 | 0.7846 | 1.0000 | 0.1429 | 1.0000 | `LOW_LINE_STABILITY`, `LOW_DETECTOR_PERTURBATION_STABILITY`, `TRACK_LOSS_NEAR_LINE` |

The A and B post-hardening counts are technical autonomous counts and are not
human-count comparisons. The selected demo remained eligible to run its clean
second pass despite LOW consistency, with a warning state; an INCONCLUSIVE
calibration would have blocked automatic counting.

**AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED**

The desktop HMI now exposes a bounded local-file `AUTO CALIBRATE & COUNT`
workflow, renders `CALIBRATING`, `AUTO CALIBRATION READY`, LOW or INCONCLUSIVE
states, shows only the selected line after lock, and keeps the existing shared
lane/business count separate from calibration evidence. The bridge uses one
controlled non-daemon application worker and no frame/history store or second
counter architecture.

**DEMO MODEL — NOT PRODUCTION VALIDATED.**

### Local A.2 verification

The existing selected autonomous demo video was replayed through the frozen
V2 CLI after the runtime changes. It completed with the historical technical
result `primary_count=6`, `confidence=low`, and `hmi_state=LIVE COUNT`; no
model, threshold, or calibration mathematics changed. A real application
composition smoke then requested cancellation during calibration and shut
down cleanly with `CANCELLED` and `worker_alive=false`. Synthetic HMI/layout
regression tests cover the 1920 and 1366 target widths, bounded latest-frame
replacement, hidden pre-lock geometry, selected-line lock, intermediate live
count, LOW persistence, and INCONCLUSIVE behavior. No screenshots or media
were retained.
