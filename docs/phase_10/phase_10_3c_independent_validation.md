# Phase 10.3C — Independent Detector + End-to-End Counting Validation

Status: **BLOCKED — HUMAN INPUT REQUIRED**

This empirical subphase remains under Phase 10.3. V2 is frozen. The work must
stop until A/B manual crossing truth is supplied and exactly one new Video C is
explicitly authorized. No production claim is made.

## Baseline

- Repository baseline: `3cd3a1ed878c614204aa3e88387c40008766fa44`
- Branch: `main`
- Working tree at audit: clean and synchronized with `origin/main`
- Baseline suite: `1063 passed, 1 warning` (inherited ByteTrack deprecation)
- Phase 10.4, persistence, and later roadmap phases: not started

## Frozen V2

V2 remains immutable after Phase 10.3B:

| Field | Frozen value |
| --- | --- |
| Identity | `hogflow_pig_demo_v2` |
| Artifact SHA-256 | `892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c` |
| Detector | YOLO11n / Ultralytics |
| Class | ID `0`, `pig` |
| Image size | `640` |
| Confidence | `0.25` |
| NMS IoU | `0.5` |
| Maximum detections | `300` |
| Detector configuration fingerprint | `611a4b66efe97b38ef1aa07f5cace4d57aa366ccf1d9b4e4f50a703fc11191c0` |
| C validation freeze fingerprint | `5f25e50e009de76496f4644d8aa4d4b5d1a24ae2f6f4a9b6049875f43dfb1ba0` |

The model gate remains **AVAILABLE** with exactly one active compatible
candidate. V1 remains archived with its original identity and SHA.

## Frozen Environment

The validated V2 stack is recorded in
`phase_10_3c_demo_environment.md`: Python `3.12.14`, Torch `2.11.0+cu128`,
CUDA `12.8`, Ultralytics `8.4.135`, OpenCV `4.14.0.94`, Supervision `0.29.1`,
and the RTX 5070 Ti Laptop GPU. ByteTrack remains unchanged through C.

## A/B Manual Crossing Truth

No review sidecars or human totals are present for the two development videos.
The values remain unknown:

```text
demo_video_a → manual crossing count: ___
demo_video_b → manual crossing count: ___
```

Therefore A/B counting calibration is **BLOCKED — A/B MANUAL CROSSING
GROUND TRUTH REQUIRED**. No line candidate has been selected and no count
error has been calculated.

## A/B Line Calibration

Not executed. The existing Phase 6 line evaluator will be reused after the
two human totals arrive. The observed motion is top-to-bottom, so the bounded
candidate family will be horizontal normalized two-point lines with visible
post-cross confirmation space. The current default vertical line is not final
evidence.

## Tracker Configuration

The current Supervision ByteTrack configuration is frozen and unchanged:

- track activation threshold: `0.25`
- lost-track buffer: `30`
- minimum matching threshold: `0.8`
- frame rate: `30.0`
- minimum consecutive frames: `1`
- tracker fingerprint: `a7dff46135c238a62d7658d9878e85909ddb63ce30ae53344bf133fef6594c89`

No evidence currently justifies tracker tuning. Temporary IDs are technical
identities, not biological identities.

## Counting Configuration

The final counting fingerprint cannot be created until A/B line calibration
has been measured against human crossing truth. The existing default camera
crossing fingerprint (`7ccb8cef63b77a59fdd097530939c99189d81b571b3cbde2b0ea89477efa4ab2`)
is retained only as historical technical configuration, not as calibrated
evidence.

## Video C Authorization

No Video C is authorized. The approved raw workspace contains A and B, three
known historical stress videos, and **11 additional unclassified MP4
candidates**. Because the specification forbids arbitrary discovery or
cherry-picking, none was inspected visually or assigned as C. One exact
candidate must be selected and explicitly authorized by the user, then
sanitized as `demo_video_c`.

## C Metadata

Not applicable until explicit authorization. No C metadata, frames, overlays,
or predictions have been created.

## C Annotation Dataset

Not created. After authorization, 30–60 representative frames must be selected
deterministically, marked as an independent test split, and human-annotated
with class `0 = pig`. C must never enter the A+B development manifest.

## Independent Detector Metrics

Not measured. A single frozen evaluation is permitted only after C labels pass
the existing validation gate with zero invalid boxes, zero image/label
mismatch, zero A/B/C duplicate content, and zero C training membership.

## Human C Count

Not available. The required worksheet is:

```text
demo_video_c → manual crossing count: ___
```

## End-to-End C Count

Not executed. It requires the frozen detector, calibrated A/B line and tracker
configuration, and an independently collected human C crossing count.

## Failure Analysis

No C failure layer can be assigned. The Phase 10.3B diagnosis remains the
historical context: V1's B failure was mixed scene/illumination/composition
shift with higher crowding, not an evaluation defect. V2's post-hoc B result
is development evidence, not independent validation.

## Runtime Performance

The frozen V2 A smoke remains the available runtime evidence: 539 frames
processed, 23.39 pipeline FPS, average latency `20.36 ms`, maximum latency
`1547 ms`, and zero detector/tracker/crossing failures. This does not establish
real-time deployment capability. C performance is pending.

## Limitations

- A/B count accuracy is blocked by missing manual crossing totals.
- Independent detector and end-to-end evidence are blocked by C authorization.
- C must not be used to tune V2, tracker, line, or thresholds.
- No production, JBS, certification, or accuracy claim is justified.
- Persistence, Phase 10.4, Phase 11, analytics, and later phases remain out of scope.

## Verdict

Detector generalization: **BLOCKED — NEW INDEPENDENT HOLDOUT REQUIRED**.

Counting: **BLOCKED — A/B MANUAL CROSSING GROUND TRUTH REQUIRED**.

**DEMO MODEL — NOT PRODUCTION VALIDATED.**
