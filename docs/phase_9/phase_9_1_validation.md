# Phase 9.1 — Validation

## Evidence level

Validation is deterministic, synthetic, headless, and application-level. It
uses the real Phase 8.4 coordinator and public Phase 7 counter with synthetic
crossing events. It uses no camera, media, model, display server, network,
database, filesystem fixture, or private data.

## Baseline

- branch: `main`;
- baseline commit: `328cfc2062b90f536503fb847ae79b130bd25da2`;
- baseline message: `Implement Phase 8.4 shared counting lane alignment`;
- local `HEAD` and `origin/main` matched;
- working tree was clean;
- baseline suite: 745 passed with one existing Supervision ByteTrack
  deprecation warning.

## Covered behavior

- empty four-dock runtime;
- registered and active trucks;
- active unloading session and occupied shared lane;
- direct live-count refresh from the lane snapshot;
- session completion releasing the lane and transferring finalized totals;
- session cancellation releasing the lane without transferring live count;
- completed and cancelled truck rendering;
- mixed OPG/REGULAR/P12 session-plan parsing;
- deterministic pig-type display including `P-12`;
- finalized total and active/completed current-record rendering;
- expected domain error display and propagation;
- immutable commands and screen models;
- public application/view protocol conformance;
- no eager Tkinter import or display creation;
- application and presentation dependency boundaries;
- Phase 7/8 independence from Phase 9.

## Commands

Focused Phase 9.1 and architecture suite:

```text
python -m pytest -q \
  tests/test_operator_application.py \
  tests/test_operator_presentation.py \
  tests/test_architecture_boundaries.py
```

Full gates:

```text
python -m pytest -q
python -m ruff check --no-cache .
python -m ruff format --check --no-cache .
python -m compileall -q src
python -m pip check
git diff --check
```

No dedicated static type checker is configured in `pyproject.toml`.

Final local results:

- focused Phase 9.1/architecture suite: 39 passed;
- full regression suite: 770 passed;
- skipped tests: 0;
- warnings: one existing Supervision ByteTrack deprecation warning;
- Ruff check and format: passed;
- compileall: passed;
- pip check: no broken requirements;
- `git diff --check`: passed;
- import smoke test: passed.

GitHub Actions remains separate evidence and must be reported only after the
commit is pushed and its run is retrieved.

## Interpretation

Passing tests proves that the operator workflow delegates to public Phase 8
commands and renders current immutable state under controlled synthetic input.
It does not prove:

- desktop usability in a representative plant workflow;
- camera or live-pipeline integration;
- pig detection, tracking, crossing, or count accuracy;
- concurrent updates or thread safety;
- persistence, recovery, authentication, or production readiness.
