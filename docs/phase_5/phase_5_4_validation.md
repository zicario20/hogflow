# Phase 5.4 — Validation

## Validation strategy

Phase 5.4 validation is synthetic, deterministic, headless, and independent
from webcam hardware, network access, GPU, model downloads, model weights, and
real pig media.

The focused tests cover:

- immutable normalized models and configuration;
- finite horizontal, vertical, and diagonal geometry;
- epsilon, boundary coordinates, endpoint reversal, and finite extensions;
- bottom-center and center anchor conversion;
- both neutral crossing directions;
- `ON_LINE` state preservation and near-line oscillation;
- empty, one-track, multi-track, and multi-event results;
- state expiry, reset, reused IDs, source isolation, stale sequences, and gaps;
- optional serial pipeline composition;
- tracker temporary failure isolation;
- reconnect reset alignment;
- crossing error cleanup;
- preview failure isolation and cooperative stop;
- CLI configuration and sanitized event-only JSON;
- architecture and import boundaries.

The implementation does not use real pig detections and these tests do not
measure crossing accuracy on representative footage.

## Required commands

```powershell
python -m pytest
python -m ruff check --no-cache .
python -m ruff format --check --no-cache .
python -m compileall -q src
python -m pip check
git diff --check
```

The focused Phase 5.4 command is:

```powershell
python -m pytest -q `
  tests/test_live_crossing_models.py `
  tests/test_live_crossing_detector.py `
  tests/test_live_crossing_pipeline.py `
  tests/test_opencv_crossing_preview.py `
  tests/test_live_detection_cli.py `
  tests/test_live_tracking_pipeline.py `
  tests/test_architecture_boundaries.py
```

An import smoke test covers the crossing models, detector port,
implementation, pipeline, preview adapter, and CLI. A deterministic CLI smoke
test uses a synthetic source, empty detector, empty tracker, and normalized
line; it creates no media and makes no detection or accuracy claim.

## Baseline evidence

Before implementation:

- branch: `main`;
- baseline: `79c0c71da0574226292c81444dcb01ec199bf4b7`;
- working tree: clean;
- full suite: 465 passed;
- warning: one known `FutureWarning` because Supervision 0.29.1 deprecates its
  bundled `ByteTrack`.

Final local and remote results are recorded in
`phase_5_4_summary.md` and the final implementation report. The focused suite
passed 86 tests; the complete suite passed 524 tests with the one known
Supervision ByteTrack deprecation warning.

## Empirical boundary

No real pig model, real pig tracking result, representative line placement,
ground truth, ID-switch evaluation, event-accuracy evaluation, or count
evaluation is part of this validation. No media, weights, credentials, or
private camera data are committed.
