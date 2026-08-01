# Phase 10.1 — Validation Record

## Evidence level

SYNTHETIC / LOCAL SOFTWARE VALIDATION ONLY.

No physical camera, real pig video, validated pig detector, production shift,
operator deployment, or count-accuracy evidence was used.

## Baseline

- Branch: `main`.
- Baseline `HEAD` and `origin/main`:
  `6fd6f02f691029998e2adef098cbad3757424780`.
- Baseline commit: `Implement Phase 9.4 live operator experience and diagnostics`.
- Pre-existing unrelated workspace state was preserved and excluded:
  `data/raw/.gitkeep` deleted and `.agents/` untracked.
- Baseline suite: 866 passed, with one architecture subprocess anomaly caused
  by the manually supplied bytecode-cache environment and one privacy failure
  caused solely by the pre-existing `.gitkeep` deletion. The architecture test
  passed alone under the normal project runtime.

## Focused validation

The Phase 10.1 suites cover:

- immutable models and configuration validation;
- deterministic fingerprints and sanitized issues;
- heartbeat health/component/worker projections;
- process memory and bounded queue/slot reporting;
- pipeline stall, stale frame, dead worker, repeated failure thresholds;
- recoverable/fatal failure separation;
- camera, pipeline, and preview restart policy;
- active-lane safety and bounded restart budget;
- one-worker restart composition and exact processed-frame provenance;
- counter reset folding into lifetime aggregate diagnostics;
- 10,000-heartbeat constant-history simulation;
- deterministic replay of the same observation sequence;
- architecture imports, no CV leakage, no storage/network/UI, and no extra
  worker/async/queue construction.

Focused Phase 10.1 result before the final repository-wide quality pass:
`41 passed`.

Final repository-wide pytest result: `909 passed, 1 warning` in 329.24 seconds
with Python 3.12.13. The warning is the existing Supervision ByteTrack
deprecation notice.

## Required final commands

The final report records the actual results of:

```console
python -m pytest
python -m ruff check --no-cache .
python -m ruff format --check --no-cache .
python -m compileall -q src
python -m pip check
git diff --check
```

The endurance simulation is included in pytest and performs 10,000 synthetic
heartbeats without retaining heartbeat history. Repository privacy checks are
run with the tracked placeholder temporarily restored, then the user's
pre-existing deletion is restored before staging.

Final local quality results:

| Check | Result |
| --- | --- |
| Focused Phase 10.1 | 41 passed |
| Full pytest | 909 passed; 1 inherited ByteTrack deprecation warning |
| Ruff check | Passed for the repository with pre-existing untracked `.agents/` excluded |
| Ruff format check | 261 files formatted; passed with pre-existing untracked `.agents/` excluded |
| compileall | Passed |
| pip check | No broken requirements |
| git diff --check | Passed; only platform line-ending notices |
| Import smoke | Passed; created health, pipeline queue capacity 0, preview capacity 1 |

The literal full-tree Ruff format command also inspected the unrelated
untracked `.agents/` skill cache and reported 24 of those external helper files
would be reformatted. They were present before Phase 10.1, are not part of the
repository commit, and were neither changed nor used as HogFlow source.

## Limitations

- Synthetic loop count is not a multi-shift wall-clock soak test.
- Process memory sampling is best-effort and platform-specific.
- No physical USB reopen or detector/tracker backend recovery was exercised.
- Thresholds are not empirically tuned.
- Identity-resetting restart is intentionally unavailable during active lane
  ownership; automatic continuity-safe failover is not implemented.
- GitHub Actions status must be retrieved after push and must not be inferred
  from local results.
