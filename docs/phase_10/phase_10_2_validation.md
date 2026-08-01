# Phase 10.2 validation

## Evidence level

The evidence is synthetic and structural. Fake model backends exercise the
installed adapter API without a real model, GPU, internet, or pig video. No
detector or counting accuracy result is produced.

## Baseline

- Branch: `main`.
- Baseline `HEAD` and `origin/main`:
  `8c2cf4950a14ba4ae03cbc25338f8ee60c2fc35e`.
- Baseline working tree: clean; `.agents/` ignored through
  `.git/info/exclude`; `data/raw/**` ignored with `.gitkeep` preserved.
- Baseline suite: `909 passed`, one inherited Supervision ByteTrack
  deprecation warning.
- The repository `.venv` lacked required binary dependencies. Validation used
  a temporary Windows Python 3.12 environment with the exact declared
  `.[dev]` dependencies; no dependency declaration changed.

## Installed framework verification

The validation environment installed Ultralytics `8.4.114`. Inspection of the
installed `YOLO.predict` signature and default configuration confirmed the
supported keyword API used by the adapter: `classes`, `conf`, `iou`, `imgsz`,
`device`, `half`, `max_det`, `save`, `stream`, and `verbose`.

## Deterministic test coverage

Focused Phase 10.2 tests cover:

- frozen configuration, path redaction, thresholds, image size, device,
  output capacity, target IDs, supported formats, missing artifacts, and
  deterministic fingerprints;
- safe immutable provenance and detector snapshots;
- empty, one-detection, and multiple-detection output;
- target-class filtering and conflicting normalized class maps;
- invalid boxes, scores, non-finite values, output lengths, container count,
  and maximum detections;
- backend timeout versus fatal inference failure;
- invalid input and lifecycle misuse;
- deterministic `auto` device resolution, unavailable CUDA, CPU/half rejection;
- one model load per detector lifecycle;
- processor-to-tracker integration and zero false counts;
- detector failure telemetry and Phase 10.1 health diagnostics;
- explicit restart with a fresh detector lifecycle;
- CLI validation before composition and path-safe snapshots;
- framework isolation, lazy imports, bounded telemetry, and Git artifact rules.

Latest focused command before final gates:

```text
python -m pytest -q \
  tests/test_pig_detector_runtime.py \
  tests/test_ultralytics_live_detector.py \
  tests/test_phase_10_2_detector_integration.py \
  tests/test_phase_10_2_architecture.py
```

Result: `43 passed`.

## Full quality gates

Final results are recorded after the complete post-documentation validation:

| Check | Result |
| --- | --- |
| Full `pytest` | `941 passed`, one inherited ByteTrack deprecation warning |
| Detector/camera/runtime/architecture focused suites | `213 passed` |
| `ruff check --no-cache .` | Passed |
| `ruff format --check --no-cache .` | Passed; 352 files formatted |
| `python -m compileall -q src` | Passed |
| `python -m pip check` | Passed; no broken requirements |
| `git diff --check` | Passed in the final pre-commit audit |
| Import smoke | Passed for config, snapshot, adapter, camera processor/controller, and bootstrap |
| `python -m hogflow --help` | Passed without source/model initialization |
| `hogflow --help` | Passed without source/model initialization |
| Empty composition smoke | Passed; composed/snapshotted/shut down without camera or model |
| Artifact/governance audit | Passed; only intended source, tests, and docs selected for commit |
| GitHub Actions | Verified after push and reported in the delivery report; the commit cannot self-record its future run |

## Optional local inference smoke

The ignored workspaces contained no compatible `.pt`, `.onnx`, or `.engine`
artifact. The optional real-model smoke test was not run. Existing ignored
media was not inspected beyond a bounded extension count and was not opened or
modified.

## Governance audit

- No model was downloaded or trained.
- No dataset was created.
- No local video or image was opened for inference or added to Git.
- No model weight or generated inference output was added.
- No absolute local model path is present in detector snapshots, telemetry,
  CLI JSON, docs examples, or test fixtures.
- Tests use temporary synthetic artifacts and fake backend outputs only.
- No Phase 10.3 code exists.

## Interpretation

Passing tests demonstrate contract, lifecycle, conversion, error-policy,
composition, and bounded-state behavior. They do not demonstrate real pig
detection quality, tracking quality, count accuracy, hardware throughput, or
production readiness.
