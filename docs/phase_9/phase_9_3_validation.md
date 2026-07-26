# Phase 9.3 — Validation

## Evidence level

SYNTHETIC / HEADLESS ONLY.

No physical camera, private video, pig footage, validated pig detector,
representative tracking, or human ground truth was used.

## Baseline

- branch: `main`
- baseline commit:
  `57db18e6078e40c96562c9216f705d327111f709`
- baseline suite: `794 passed, 1 warning`
- warning: existing Supervision `ByteTrack` deprecation notice

The first baseline attempt used the incomplete MSYS virtual environment and
failed collection because OpenCV/NumPy were absent. The validated baseline
used `.venv/windows/Scripts/python.exe` with local writable runtime cache
directories.

## Deterministic coverage

The Phase 9.3 suite covers immutable models, camera/file configuration,
exact detector/tracker/crossing association, lifecycle provenance, idle-lane
behavior, source exhaustion/failure, stage failure categories, worker
shutdown, active-session routing, stale-result rejection, sequential dock
isolation, presentation state, CLI validation, and dependency boundaries.

Final focused Phase 9.3/operator/architecture result:
`98 passed in 74.94s`.

The first full run collected 828 tests. It produced `826 passed` plus two
architecture expectation failures that encoded the Phase 9.2 no-camera
composition. The implementation removed an unnecessary
`application → streaming` dependency and updated only the composition-root
expectation to permit explicitly authorized adapter/detector/tracker wiring
while retaining framework, storage, network, and UI restrictions.

Final full regression result: `830 passed, 1 warning in 92.39s`. The warning is
the existing Supervision `ByteTrack` deprecation notice.

Ruff, format, compile, dependency, diff, import, and CLI gates are recorded in
the Phase 9.3 summary and completion report:

- `python -m ruff check --no-cache .`: passed;
- `python -m ruff format --check --no-cache .`: 240 files formatted;
- `python -m compileall -q src`: passed;
- `python -m pip check`: no broken requirements;
- `git diff --check`: passed; Windows checkout emitted only expected LF/CRLF
  conversion notices;
- import smoke: passed;
- `python -m hogflow --help`: passed without opening a source;
- installed `hogflow --help`: passed after refreshing the pre-existing editable
  environment without dependencies or network access.

Remote CI is recorded only after the implementation commit is pushed.

## Privacy audit

- no frames or video committed;
- no source paths stored in reports or snapshots;
- no camera/RTSP credentials;
- no model weights;
- no databases or logs;
- no physical camera opened;
- all test frames and crossing events synthetic.
