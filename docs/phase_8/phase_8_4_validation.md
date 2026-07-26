# Phase 8.4 — Validation

## Evidence level

Validation is deterministic, synthetic, and application-level. It proves
ownership, lifecycle, routing, and atomic state behavior without a camera,
model, real animal, network, database, thread, or display.

## Baseline

- branch: `main`;
- baseline commit: `19baa9d7a37f3defa63f1ac1831c24c7d5e92b62`;
- baseline message: `Implement Phase 8.3 multi-dock runtime coordination`;
- local `HEAD` and `origin/main` matched;
- working tree was clean;
- baseline suite: 739 passed with one existing Supervision ByteTrack
  deprecation warning.

## Focused scenarios

The Phase 8.4 tests cover:

- one shared lane constructed with one enabled, inactive Phase 7 counter;
- lane binding to Dock 1 with exact operation/session/lifecycle provenance;
- rejection of Dock 2 while Dock 1 owns the lane;
- explicit wrong-dock, wrong-source, wrong-lifecycle, and stale rejection;
- Phase 7 duplicate-positive and reverse behavior unchanged;
- completion transferring exactly one final total and releasing the lane;
- cancellation discarding unfinished total and releasing the lane;
- a later dock or later session binding the same physical lane;
- the same numeric tracker ID accepted in a fresh session lifecycle;
- mixed OPG/REGULAR sequential sessions through the same counter;
- terminal truck completion and cancellation leaving the lane available;
- replacement truck state without prior count leakage;
- live/finalized aggregate separation;
- counter close failure without partial session/domain mutation;
- idle and bound shutdown behavior;
- verified terminal-provenance adoption by Phase 8.2;
- immutable snapshots and framework/dependency boundaries.

## Commands

The required final commands are:

```text
python -m pytest -q
python -m pytest -q tests/test_shared_counting_lane.py \
  tests/test_multi_dock_runtime.py \
  tests/test_unloading_session_counting_service.py \
  tests/test_unloading_session_counting_models.py \
  tests/test_architecture_boundaries.py
python -m ruff check --no-cache .
python -m ruff format --check --no-cache .
python -m compileall -q src
python -m pip check
git diff --check
```

An import smoke test covers the new lane models/errors/component and the
updated runtime coordinator. No dedicated static type checker is configured
in `pyproject.toml`.

Results after implementation and documentation:

- focused Phase 8.4/8.2/architecture suite: 69 passed;
- full regression suite: 745 passed;
- skipped tests: 0;
- warnings: one existing Supervision ByteTrack deprecation warning;
- Ruff check: passed;
- Ruff format check: passed, 210 files already formatted;
- compileall: passed;
- pip check: no broken requirements;
- `git diff --check`: passed, with informational Windows LF-to-CRLF notices;
- import smoke test: passed;
- GitHub Actions is recorded separately after push and is not inferred from
  these local results.

## Limitations

- Synthetic lifecycle events do not validate pig identity or count accuracy.
- No shared physical camera was opened.
- The coordinator remains synchronous and caller-serialized.
- There is no durable recovery or history.
- The installed Supervision ByteTrack API remains deprecated.
- Remote GitHub Actions is separate evidence and must be reported only after
  the pushed commit's run concludes.
