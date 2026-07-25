# Phase 8.1 - Validation

## Evidence level

Validation is synthetic and deterministic. It verifies domain contracts,
transitions, totals, atomicity, dock isolation, architecture, and regressions.
It does not validate a plant workflow, live counts, real pigs, concurrency,
persistence, or operator behavior.

## Covered scenarios

- all four dock IDs and pig types;
- stable `p12` internal representation;
- session creation, count and timestamp validation;
- one, two, three, four, and six-session operations;
- unique session IDs and sequence numbers;
- operation and session activation rules;
- one active session per operation;
- strict sequence ordering with cancelled sessions treated as terminal;
- final non-negative actual counts, including zero;
- operation completion and cancellation;
- immutable session summaries and deterministic per-type totals;
- three regular sessions totaling 165;
- mixed OPG/regular sessions totaling 160;
- one P12 session totaling 10;
- NAE behavior;
- same-dock occupancy rejection and post-terminal availability;
- simultaneous isolated records for several docks;
- copy-on-write atomicity after invalid transitions;
- imports and architecture boundaries;
- all pre-Phase 8.1 regression tests.

## Runtime

The repository's Windows environment is:

```powershell
.\.venv\windows\Scripts\python.exe
```

The shell-global `python` may resolve to a different interpreter without the
project development dependencies, so validation uses the explicit environment.

## Focused tests

```powershell
.\.venv\windows\Scripts\python.exe -m pytest -q `
  tests/test_unloading_models.py `
  tests/test_truck_operation.py `
  tests/test_dock_operation_registry.py `
  tests/test_architecture_boundaries.py
```

## Full quality gates

```powershell
.\.venv\windows\Scripts\python.exe -m pytest
.\.venv\windows\Scripts\python.exe -m ruff check --no-cache .
.\.venv\windows\Scripts\python.exe -m ruff format --check --no-cache .
.\.venv\windows\Scripts\python.exe -m compileall -q src
.\.venv\windows\Scripts\python.exe -m pip check
git diff --check
```

No static type checker is configured in `pyproject.toml`; Phase 8.1 adds no
type-checking dependency.

## Expected warning

The existing Supervision `ByteTrack` deprecation `FutureWarning` remains
visible in the full suite. Phase 8.1 neither imports nor changes Supervision.

## Interpretation

Passing these checks proves the copy-on-write domain rules for controlled
inputs. It does not prove:

- that the four-dock description matches every deployment;
- that actual session boundaries are detected automatically;
- that Phase 7 totals transfer correctly to sessions;
- that a lifecycle total is an accurate biological pig count;
- that persistence or concurrent command handling is safe.
