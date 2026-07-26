# Phase 8.3 — Validation

## Evidence level

The validation is deterministic and synthetic. It demonstrates application
coordination and isolation only. It does not validate simultaneous physical
cameras, real pigs, detector/tracker quality, operational throughput, or
production concurrency.

## Baseline

- branch: `main`
- baseline commit: `8416eba3607f614ab42145cc0ed0b6b22bfdd435`
- baseline message: `Implement Phase 8.2 session counting integration`
- local and `origin/main` matched before implementation
- working tree was clean
- baseline suite: 707 passed, 1 existing Supervision ByteTrack deprecation warning

## Focused scenarios

The Phase 8.3 tests cover:

- registration at one and all four docks;
- invalid dock, occupied dock, dock mismatch, source collision, operation-ID
  collision, and factory failure;
- operation startup without premature counter startup;
- four logically simultaneous active sessions;
- one owned counter, source, crossing lifecycle, and counting lifecycle per dock;
- same tracker ID counted independently at two docks;
- duplicate-positive suppression inside one dock only;
- wrong-source, wrong-lifecycle, and stale-result rejection;
- active and finalized lifecycle collision rejection;
- rollback of a prospective session after counting-lifecycle collision;
- exact one-time session transfer;
- mixed OPG/REGULAR sequential sessions with fresh identity state;
- P12 and NAE operation behavior;
- session and active-truck cancellation;
- prior completed totals preserved during later cancellation;
- terminal record replacement by a clean truck runtime;
- live counts separated from finalized and combined totals;
- deterministic Dock 1–4 snapshots;
- local failure isolation;
- close with no runtimes, active sessions, repeated calls, and partial failure;
- Phase 8.2 pre-commit lifecycle-validator behavior;
- architecture and import-side-effect boundaries.

The test factory uses deterministic per-dock counting-lifecycle namespaces.
Separate collision fixtures intentionally return identical IDs to prove the
coordinator rejects them and Phase 8.2 rolls back startup.

## Quality commands

Final results are recorded after all implementation and documentation changes:

```text
python -m pytest -q
python -m pytest -q tests/test_multi_dock_runtime.py \
  tests/test_unloading_session_counting_service.py \
  tests/test_architecture_boundaries.py
python -m ruff check --no-cache .
python -m ruff format --check --no-cache .
python -m compileall -q src
python -m pip check
git diff --check
```

An import smoke test covers:

```text
hogflow.sessions.runtime_coordinator
hogflow.sessions.runtime_models
hogflow.sessions.runtime_errors
```

Results:

- focused Phase 8.3/8.2/architecture suite: 55 passed;
- full regression suite: 739 passed;
- skipped tests: 0;
- warnings: 1 existing Supervision ByteTrack deprecation warning;
- Ruff check: passed;
- Ruff format check: passed, 206 files formatted;
- compileall: passed;
- pip check: no broken requirements;
- `git diff --check`: passed;
- import smoke test: passed.

No dedicated static type checker is configured in `pyproject.toml`.

## Validation limits

- Commands are synchronous and serialized in tests.
- No worker, thread, async task, queue, camera, network, database, or UI is
  created.
- Synthetic counters demonstrate contract behavior but do not validate
  detector, tracker, line, or counting accuracy.
- GitHub Actions status must be verified separately after push; local success
  alone is not remote CI evidence.
