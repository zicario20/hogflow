# Phase 7 - Validation

## Evidence level

Phase 7 validation is synthetic and deterministic. It verifies contracts,
policy mechanics, lifecycle coordination, atomicity, architecture, CLI, and
cleanup. It does not validate pig detection, real tracking, biological
deduplication, reverse behavior in a livestock passage, or count accuracy.

## Required business scenarios

The synthetic fixtures cover:

1. **Forward clean** - two temporary tracks cross once in the configured
   positive direction; final lifecycle total is two.
2. **Reverse and repeat** - one track produces positive, reverse, positive;
   only the first positive increments and final total is one.
3. **Reverse only** - reverse events are recorded with zero increment.
4. **Reconnect** - the same numeric tracker ID can increment once in each
   independent crossing/counting lifecycle; totals are not combined.
5. **Multiple tracks in one frame** - two positive events are ordered
   deterministically and applied atomically with frame increment two.
6. **Atomic invalid batch** - one inconsistent event rejects the frame; no
   valid event in that frame is partially applied.

Additional tests cover:

- disabled defaults and invalid configuration;
- immutable/hashable lifecycle-qualified identities;
- coherent decisions and totals;
- duplicate positive after empty/missed-event frames;
- explicit inverted positive direction;
- source, lifecycle, crossing fingerprint, line, and frame mismatches;
- stale/repeated frames and valid sequence gaps;
- capacity failure without ID eviction;
- start, reset, close, callback STOP, and fatal cleanup;
- temporary tracker failure producing no fabricated decision;
- reconnect resetting crossing and counting;
- preview failure isolation;
- Phase 5.4 behavior when counting is disabled;
- CLI preflight validation and structured local output;
- package imports and framework/dependency boundaries.

## Commands

Use the repository Windows environment:

```powershell
$env:PATH=(Resolve-Path '.venv\windows\Scripts').Path + ';' + $env:PATH
```

Focused Phase 7 and regression suite:

```powershell
python -m pytest -q `
  tests/test_live_counting_models.py `
  tests/test_lifecycle_directional_counter.py `
  tests/test_live_counting_contract.py `
  tests/test_live_counting_pipeline.py `
  tests/test_opencv_counting_preview.py `
  tests/test_live_crossing_models.py `
  tests/test_live_crossing_detector.py `
  tests/test_live_crossing_pipeline.py `
  tests/test_live_tracking_pipeline.py `
  tests/test_architecture_boundaries.py `
  tests/test_live_detection_cli.py
```

Full quality gates:

```powershell
python -m pytest
python -m ruff check --no-cache .
python -m ruff format --check --no-cache .
python -m compileall -q src
python -m pip check
git diff --check
```

Import smoke test:

```powershell
python -c "from hogflow.counting import LifecycleDirectionalCounter, LiveCountingConfiguration; from hogflow.pipeline import LiveCountingPipeline; from hogflow.adapters.opencv_counting_preview import OpenCVCountingPreview; print('phase7-import-ok')"
```

Synthetic CLI smoke test:

```powershell
python -m hogflow.video.live_detection_cli `
  --source-type synthetic `
  --synthetic-frames 20 `
  --detector synthetic-moving `
  --tracker deterministic-iou `
  --enable-crossing `
  --crossing-line-start 0.5,0.1 `
  --crossing-line-end 0.5,0.9 `
  --enable-counting `
  --positive-direction positive_to_negative `
  --statistics-interval 100
```

The synthetic source is intentionally allowed to outrun inference under the
latest-frame policy. A zero-event CLI run remains a valid lifecycle smoke test;
positive/reverse/duplicate policy behavior is validated with controlled
synthetic fixtures.

## Known warning

The installed `supervision==0.29.1` emits the existing warning that ByteTrack
is deprecated and scheduled for removal in Supervision 0.30. Phase 7 adds no
dependency and does not migrate that adapter.

## Interpretation

Passing tests establish that the implemented code follows the approved Phase 7
policy for synthetic inputs. They do not establish:

- correct pig detections;
- representative track continuity;
- absence of ID switches or fragmentation;
- correct behavior under dense occlusion;
- correct operational positive direction;
- calibrated line placement;
- session-level count accuracy;
- production readiness.
