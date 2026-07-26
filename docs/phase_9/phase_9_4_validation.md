# Phase 9.4 — Validation

## Evidence level

SYNTHETIC / HEADLESS ONLY.

No physical camera, operational video, pig image, validated pig detector,
representative tracking, human ground truth, display-server interaction, or
count-accuracy evidence was used.

## Baseline

- branch: `main`;
- baseline commit: `a2088d02860f42cb21a018f43ee3bffab152c2e4`;
- baseline message:
  `Implement Phase 9.3 camera acquisition and counting pipeline`;
- local `HEAD` and `origin/main` matched;
- working tree was clean;
- baseline suite: `830 passed, 1 warning`;
- warning: existing Supervision `ByteTrack` deprecation notice.

## Deterministic coverage

Tests cover:

- immutable preview models and safe `repr`;
- latest-frame replacement and consumption;
- no queue, deque, playback, or history;
- disabled, waiting, available, degraded, failed, and closed visual states;
- aggregate preview FPS;
- one publisher/one consumer synchronization;
- line, box, ID, anchor, side, direction, dimensions, and status primitives;
- processor publication while lane idle and occupied;
- render/publication failure isolation;
- reconnect reset of tracker and crossing state;
- bounded open and read recovery;
- disconnected camera state;
- no file-source reopen;
- pipeline-start gating and application shutdown;
- application-only presentation access;
- one cancellable Tk refresh callback;
- no Tk call from the worker;
- no OpenCV/framework object in preview contracts;
- no Phase 7/8 dependency reversal;
- no storage, network, database, or media output.

## Interpretation

Passing tests validate bounded visual delivery, deterministic overlay planning,
thread ownership, failure isolation, and source-recovery control flow. They do
not validate:

- real Tk rendering performance on the deployment workstation;
- a physical camera disconnect/reopen;
- detector/tracker throughput;
- pig-specific boxes or IDs;
- crossing or count accuracy;
- identity behavior through a real disconnect;
- representative operator usability.

## Commands

Focused Phase 9.4/9.3/presentation/architecture suites:

```text
python -m pytest -q \
  tests/test_preview_channel.py \
  tests/test_camera_frame_processor.py \
  tests/test_camera_recovery.py \
  tests/test_camera_pipeline_controller.py \
  tests/test_operator_live_preview.py \
  tests/test_operator_camera_integration.py \
  tests/test_operator_presentation.py \
  tests/test_operator_desktop.py \
  tests/test_operator_bootstrap.py \
  tests/test_phase_9_3_architecture.py \
  tests/test_phase_9_4_architecture.py \
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
hogflow --help
```

No dedicated static type checker is configured.

## Current local result

- focused Phase 9.4/9.3/presentation/architecture suite:
  `125 passed in 69.22s`;
- full regression suite:
  `868 passed, 1 warning in 93.08s`;
- Ruff lint: `All checks passed`;
- Ruff format: `247 files already formatted`;
- compileall: passed with no output;
- pip check: `No broken requirements found`;
- `git diff --check`: passed; Git reported only the existing Windows
  LF-to-CRLF working-copy notices;
- both `python -m hogflow --help` and `hogflow --help`: passed without opening
  a source;
- public import smoke test: `imports-ok`;
- warning: the existing Supervision `ByteTrack` deprecation notice for its
  planned removal in Supervision 0.30.0;
- no tests were skipped.

Remote CI is reported only after commit and push; local success is never
represented as remote success.

## Privacy audit

- no frame, image, video, or screenshot is tracked;
- preview frames exist only as in-memory RGB bytes;
- no recording or output path exists in the preview packages;
- no source path appears in snapshots or reports;
- no camera/RTSP credentials, private IP, weights, database, or operational log
  was added;
- tests use tiny synthetic byte payloads and opaque identifiers only.
