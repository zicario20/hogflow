# Phase 9.2 — Validation

## Evidence level

Validation is synthetic, deterministic, local, and headless. It uses the real
Phase 7 counter and Phase 8 shared-lane coordinator but no camera, frames,
model, video, display server, filesystem data, network, database, or private
operational information.

## Baseline

- branch: `main`;
- baseline commit: `bd462af0354430dc060e359fa6ae1b8c9e816169`;
- baseline message: `Implement Phase 9.1 operator MVP user interface`;
- local `HEAD` and `origin/main` matched;
- working tree was clean;
- baseline suite: 770 passed with one existing Supervision ByteTrack
  deprecation warning.

## Covered behavior

- selected-dock button enable/disable rules across available, planned, active,
  session-active, completable, terminal, and closed states;
- authoritative next-session and completion eligibility in Phase 8 snapshots;
- shared-lane owner text and current pig/session/live count;
- truck/session status messages;
- cancel-session and cancel-truck confirmation text and accept/decline paths;
- exit confirmation with an active lane or non-terminal truck;
- active-session shutdown discard without fabricated completion;
- idle shutdown and repeated shutdown;
- complete form validation before application invocation;
- duplicate session ID/sequence rejection;
- no presenter or Tk snapshot cache;
- manual refresh;
- composition root, injected view, and module entry point;
- CLI help without GUI creation;
- no eager Tkinter import;
- no camera/CV/storage/network/thread dependency.

## Commands

Focused Phase 9.2, coordinator, and architecture suite:

```text
python -m pytest -q \
  tests/test_operator_application.py \
  tests/test_operator_presentation.py \
  tests/test_operator_bootstrap.py \
  tests/test_operator_desktop.py \
  tests/test_multi_dock_runtime.py \
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
python -m hogflow --help
```

No dedicated static type checker is configured.

## Current local result

- focused Phase 9.2/coordinator/architecture suite: 91 passed;
- full regression suite: 794 passed;
- warnings: one existing Supervision ByteTrack deprecation warning;
- remote CI: must be retrieved after push and reported separately.

## Interpretation

Passing tests prove deterministic workflow guidance, composition, delegation,
and cleanup under controlled synthetic state. They do not prove:

- representative operator usability or accessibility;
- live camera or counting integration;
- pig detection/tracking/count accuracy;
- crash recovery or durable history;
- concurrent updates or thread safety;
- production readiness.
