# Phase 8.2 - Validation

## Evidence level

Validation is synthetic and deterministic. It exercises the public Phase 7
counter with immutable synthetic crossing results and the Phase 8.1 aggregate.
No camera, model, GPU, network, pig video, private data, or database is used.

## Covered behavior

- one session owns one crossing/counting lifecycle;
- only the Phase 7 positive-direction total transfers;
- reverse events and duplicate positives do not inflate a session total;
- sequential sessions receive different counting lifecycle IDs;
- the same numeric tracker ID can contribute once in each separate session;
- mixed OPG and regular sessions preserve independent type totals;
- starting a second lifecycle while a session is active is rejected;
- completed and cancelled lifecycles close Phase 7;
- cancellation discards the unfinished count and preserves earlier sessions;
- duplicate completion and finalized-count mutation are rejected;
- crossing lifecycle reuse is rejected without starting the next session;
- source, lifecycle, and timestamp mismatch is rejected before counting;
- completion before the latest counting result is atomic and rejected;
- counter-close failure leaves the domain session active and unmodified;
- Phase 7 fresh-start gauges reset to zero;
- Phase 7 and Phase 8.1 do not import back from `hogflow.sessions`;
- application integration imports no CV framework or forbidden layer.

## Commands

Focused Phase 8.2 and regression suite:

```powershell
.\.venv\windows\Scripts\python.exe -m pytest -q `
  tests/test_unloading_session_counting_models.py `
  tests/test_unloading_session_counting_service.py `
  tests/test_unloading_models.py `
  tests/test_truck_operation.py `
  tests/test_dock_operation_registry.py `
  tests/test_lifecycle_directional_counter.py `
  tests/test_live_counting_contract.py `
  tests/test_live_counting_pipeline.py `
  tests/test_architecture_boundaries.py
```

Result: `123 passed`.

Full quality gates:

```powershell
.\.venv\windows\Scripts\python.exe -m pytest
.\.venv\windows\Scripts\python.exe -m ruff check --no-cache .
.\.venv\windows\Scripts\python.exe -m ruff format --check --no-cache .
.\.venv\windows\Scripts\python.exe -m compileall -q src
.\.venv\windows\Scripts\python.exe -m pip check
git diff --check
```

Full-suite result: `707 passed`; Ruff check and format, `compileall`,
`pip check`, and `git diff --check` passed.

No static type checker is configured in `pyproject.toml`; Phase 8.2 adds no
dependency.

## Existing warning

The installed `supervision==0.29.1` ByteTrack deprecation warning remains.
Phase 8.2 neither imports nor changes the adapter.

## Interpretation

Passing tests establish lifecycle ownership, count-transfer, isolation, and
atomic application mechanics for controlled inputs. They do not establish:

- that Phase 7 counts correspond to unique pigs;
- correct behavior under real ID switches, fragmentation, or occlusion;
- a policy for reconnect in the middle of one physical unloading session;
- simultaneous multi-dock runtime safety;
- persistence or operator workflow correctness;
- production readiness or count accuracy.
