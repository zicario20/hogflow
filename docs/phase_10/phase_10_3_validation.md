# Phase 10.3 — Validation Record

## Baseline

- Repository branch: `main`.
- Baseline local and remote SHA:
  `e14bf5b5d73b886ff9834b606787ca58872c65b2`.
- Working tree before implementation: clean.
- `.agents/`: ignored through `.git/info/exclude`.
- `data/raw/**`: ignored; `data/raw/.gitkeep`: tracked.
- Model extensions and approved model roots: ignored.
- Python: 3.12.13 in the isolated Phase 10.2 test environment.
- Baseline suite: 941 passed in 119.61 seconds.
- Inherited warning: one Supervision ByteTrack deprecation warning.

## Authorized local metadata evidence

Metadata was read with `OpenCVVideoMetadataReader` using at most 12 sampled
frames per file. No frame, screenshot, derivative, or recording was retained.

| ID | Container | Duration | Nominal FPS | Frames | Resolution | Local size | Readable | Stability aid |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- | --- |
| `video_1` | MP4 | 16.178333 s | 60.018543 | 971 | 848×384 | 3,364,500 bytes | yes | likely static |
| `video_2` | MP4 | 12.183333 s | 27.332421 | 333 | 1248×576 | 2,553,907 bytes | yes | likely static |
| `video_3` | MP4 | 9.601667 s | 59.885437 | 575 | 848×384 | 1,949,196 bytes | yes | low motion |

These are metadata observations, not detection or count results. The nominal
FPS values were not treated as measured processing throughput.

## Sidecar and model gates

- Sidecars found: 0 of 3.
- Compatible `.pt`, `.onnx`, or `.engine` artifacts found in approved roots: 0.
- Tracked compatible model artifacts: 0.
- Real detector inference attempted: no.
- Tracker/crossing/counting execution attempted: no.
- Manual count ground truth found: no.
- Frame/event detection annotations found: no.

The generated local report correctly sets runtime metrics to `UNKNOWN` and
Video 3 counting metrics to `NOT_APPLICABLE`. It does not replace missing
evidence with zero.

## Synthetic deterministic coverage

Tests cover:

- immutable evidence and report models;
- deterministic fingerprints and JSON;
- path/basename/framework redaction;
- exact authorized filename selection and unauthorized rejection;
- missing, ignored, untracked, tracked, ambiguous, and approved model states;
- manual total derivation without detector metric fabrication;
- per-video calibration plans and Phase 6 no-recommendation conversion;
- missing-model hard gate with zero backend calls;
- model-present fake backend in exact video order;
- Video 2 blocked after incomplete Video 1;
- Video 3 count ineligibility;
- backend provenance mismatch rejection;
- incomplete detector/tracker/crossing cases without false counts;
- atomic JSON/Markdown output;
- framework/UI/storage/thread/queue dependency boundaries;
- ignored output/media/model governance.

CI uses no real media, model, GPU, CUDA, or internet. Local real-video tests are
not committed and do not run in CI.

## Local CLI evidence

The offline CLI completed metadata and gate processing and wrote ignored local
reports. Its sanitized result was:

```text
model_gate=missing
video_1=blocked
video_2=blocked
video_3=blocked
empirical_verdict=REAL DETECTOR VALIDATION COULD NOT BE COMPLETED
```

A privacy scan found no absolute path, username, authorized filename, raw-media
path, model filename, or framework token in either local report.

## Final local quality evidence

- Focused Phase 10.3 suite: 64 passed in 74.71 seconds.
- Focused detector/camera/pipeline/runtime/architecture regression selection:
  216 passed in 89.53 seconds.
- Full regression suite: 985 passed in 110.14 seconds on the final source tree.
- Warnings: one inherited Supervision `ByteTrack` deprecation warning; no tests
  were skipped to obtain a passing result.
- A separate 26-test regression selection covering architecture, the existing
  detector import smoke boundary, and the Supervision adapter passed with the
  same inherited warning.

The remaining static, packaging, CLI, and diff gates are recorded in the final
implementation report and must pass before publication.

## Interpretation

Passing tests establish deterministic validation mechanics and governance.
They do not establish pig detector quality, real tracking quality, count
accuracy, calibrated line placement, runtime FPS, or production readiness.
