# Phase 6 — Validation

## Evidence boundary

Phase 6 implementation validation uses only small synthetic tracking replays.
It verifies deterministic geometry reuse, isolation, metrics, matching,
ranking, serialization, privacy, and CLI behavior.

It does not validate a pig detector, real pig tracking, line placement,
crossing-event accuracy on representative footage, accumulated count accuracy,
or production readiness.

Official status language:

> Phase 6 evaluation infrastructure implemented; representative pig
> line-position evaluation remains pending.

## Synthetic scenarios

### Scenario A — clean pass

One temporary track moves horizontally through left, center, and right
vertical line candidates. A synthetic reference event at the center line
allows frame-offset and ranking checks.

### Scenario B — finite extension

One track crosses the supporting infinite line outside a short segment. The
short segment emits no event; a longer segment containing the movement
intersection emits one.

### Scenario C — jitter and gaps

Several tracks include near-epsilon jitter, missing frame sequences, one
non-crossing trajectory, and real side transitions. Tests verify no
interpolation, gap diagnostics, endpoint diagnostics, and independent IDs.

Reference fixtures additionally instantiate central, left, right, horizontal,
diagonal, short, and long finite lines. They are technical fixtures, not
recommended pig-camera configurations.

## Baseline

- branch: `main`;
- baseline SHA: `86ef52f92c92a0ca72007eab286c1f82698a43ce`;
- baseline message: `Implement Phase 5.4 live line crossing events`;
- working tree: clean;
- Python: 3.12.13 in `.venv/windows`;
- baseline suite: 524 passed;
- warning: one known Supervision ByteTrack deprecation `FutureWarning`.

The shell's unqualified `python` initially selected an unrelated MSYS runtime
without pytest. The legacy `.venv/bin` Python 3.11 environment also lacked
NumPy/OpenCV. The repository's configured complete Windows runtime was then
used for the recorded baseline and final validation.

## Focused validation

Focused tests cover:

- candidate, plan, replay, ground-truth, result, report, and telemetry models;
- immutability and stable fingerprints;
- source, sequence, timestamp, schema, and metadata validation;
- serial candidate isolation and order independence;
- finite line, endpoint, gap, anchor, and epsilon behavior;
- exact/windowed/directional one-to-one matching;
- zero-safe event metrics;
- ranking methods and deterministic tie-breaks;
- strict JSON round trips and atomic output;
- path/stack/media privacy;
- synthetic CLI end-to-end;
- architecture boundaries and Phase 5.4 regressions.

## Commands

```powershell
python -m pytest -q `
  tests/test_line_evaluation_models.py `
  tests/test_line_event_matching.py `
  tests/test_line_position_evaluator.py `
  tests/test_line_position_io_cli.py `
  tests/test_live_crossing_models.py `
  tests/test_live_crossing_detector.py `
  tests/test_architecture_boundaries.py

python -m pytest
python -m ruff check --no-cache .
python -m ruff format --check --no-cache .
python -m compileall -q src
python -m pip check
git diff --check
```

Import smoke tests cover every new evaluation module. CLI smoke testing writes
plan, replay, and report JSON only inside a temporary directory.

Two deterministic runs must produce identical report bytes when the injected
generation and monotonic clocks are fixed. Production CLI reports deliberately
retain their real generation time and measured evaluation latency.

## Empirical work still required

A representative evaluation requires:

- explicitly authorized pig video;
- sufficiently valid pig detections and tracking;
- source-level provenance;
- human-reviewed crossing-event ground truth;
- multiple predeclared candidate lines;
- reproducible reports and failure review.

No such empirical result was produced by implementation.
