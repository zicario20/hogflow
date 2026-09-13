# Phase 10.3C-A.1 Autonomous Hardening + HMI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the autonomous consistency metrics so primary-count instability cannot be hidden, measure the missing trajectory signals, and expose the frozen autonomous demo through the existing dark industrial Tk HMI without changing the formal human-validation path.

**Architecture:** Keep geometry analysis framework-neutral in `hogflow.calibration`. The existing detector, ByteTrack, crossing, counter, and single shared-lane pipeline remain the only runtime components. Add a bounded autonomous-run bridge that is mutually exclusive with the existing pipeline worker, publishes immutable snapshots to the presenter, and never executes Tk work outside the UI thread.

**Tech Stack:** Python 3.12, immutable dataclasses, OpenCV/Ultralytics adapters already present, Supervision ByteTrack, Tkinter presentation, pytest, Ruff.

**Spec:** `C:/Users/sami/.codex/attachments/a411bb33-7ead-43d3-abff-a2b7e987f652/pasted-text.txt`

## Global Constraints

- Preserve all pre-hardening Phase 10.3C-A values as historical evidence.
- Do not retrain or alter `hogflow_pig_demo_v2`; do not inspect, select, annotate, or evaluate formal Video C candidates.
- Preserve the existing detector → tracker → crossing → counter architecture and replay/lifecycle guards.
- Autonomous consistency is not human accuracy; keep `AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED` and `DEMO MODEL — NOT PRODUCTION VALIDATED`.
- Keep all real media, frames, labels, weights, traces, and local paths ignored and untracked.
- Use Python 3.12.14 project environments; CI must remain synthetic/source-only.

---

### Task 1: Freeze baseline and add failing metric tests

**Files:**
- Create: `tests/test_autonomous_calibration_hardening.py`
- Create: `tests/test_autonomous_demo_bridge.py`
- Modify: `docs/superpowers/plans/2026-09-13-phase-10-3c-a1-autonomous-hardening-hmi.md`

**Interfaces:**
- Tests will target `line_band_agreement(primary_count, neighbor_counts)`, `detector_perturbation_agreement(primary_count, variant_counts)`, `count_family_metrics`, geometry diagnostics, hard confidence gates, reason codes, and immutable presentation models.

- [x] **Step 1: Record the clean baseline.**

Recorded clean baseline `9d5620fc43d440811925d8fc2a7e63cae420cb40` on `main`; the pre-change suite was 1094 passed and the final suite is 1103 passed.

- [x] **Step 2: Write tests that fail against the old semantics.**

Assert that `(29, 18, 18, 16, 17)` has low primary agreement, `(51, 50, 51, 51, 52)` has high agreement, zero families are bounded, and historical B-like metrics cannot return `HIGH`. Add synthetic trajectory cases for full/partial/zero corridor coverage, lost-near-line, and crossing-local continuity. Add immutable `AutonomousDemoPanel`/state tests for calibration, ready, low, inconclusive, count-range, and no-accuracy copy.

- [x] **Step 3: Run only the new tests and verify expected failures.**

Run `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_autonomous_calibration_hardening.py tests/test_autonomous_demo_bridge.py -q`; failures must identify missing APIs or old placeholder behavior, not fixture errors.

### Task 2: Implement primary-inclusive stability and trajectory diagnostics

**Files:**
- Modify: `src/hogflow/calibration/models.py`
- Modify: `src/hogflow/calibration/engine.py`
- Modify: `src/hogflow/calibration/__init__.py`
- Test: `tests/test_autonomous_calibration_hardening.py`

**Interfaces:**
- `count_family_metrics(primary_count: int, variant_counts: tuple[int, ...]) -> CountFamilyMetrics` returns min, max, median, absolute/relative spread, primary deviation, and primary agreement.
- `line_band_agreement(primary_count: int | tuple[int, ...], neighbor_counts: tuple[int, ...] | None = None) -> float` evaluates the primary-inclusive family while accepting the legacy tuple form as one complete family.
- `detector_perturbation_agreement(primary_count: int | tuple[int, ...], variant_counts: tuple[int, ...] | None = None) -> float` uses the same robust family logic.
- `evaluate_candidate_tracks(...)` returns real corridor coverage, lost-near-line ratio, crossing-local continuity, primary-inclusive metric fields, and bounded reason codes.

- [x] **Step 1: Add immutable aggregate fields and validation.**

Extend `LineCandidateMetrics` and `AutonomousCalibrationResult` with primary count, line/detector min/max/median/relative spread/agreement, corridor coverage, lost-near-line ratio, crossing-local continuity, reason codes, and algorithm version. Keep old fields as compatibility aliases and preserve bounded tuple storage.

- [x] **Step 2: Implement robust family statistics.**

Use median as the denominator center; return zero-safe bounded values. Include the official primary count in both line and detector families. Remove the hardcoded `0.10 * 0.0` score term.

- [x] **Step 3: Implement geometry signals from sampled trajectories.**

Compute finite-segment crossing parameters for corridor coverage, before/after side evidence for crossing-local continuity, and a declared normalized near-line termination window for technical lost-near-line ratio. Preserve unique tracker-bounded crossing counts and never infer biological loss.

- [x] **Step 4: Redesign score and hard confidence gates.**

Use documented real components and penalties, clamp to `[0, 1]`, and require hard gates for `HIGH`: eligible tracks, direction purity, primary-inclusive line/detector stability, uniqueness, corridor coverage, continuity, and acceptable loss. Emit bounded reason codes for instability and insufficiency.

- [x] **Step 5: Run the new tests and the existing calibration tests.**

Run `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_autonomous_calibration_hardening.py tests/test_autonomous_calibration_engine.py tests/test_autonomous_calibration_consistency.py tests/test_autonomous_calibration_models.py -q` and keep all green.

### Task 3: Version the algorithm and expose hardened data through orchestration/CLI

**Files:**
- Modify: `src/hogflow/calibration/orchestration.py`
- Modify: `src/hogflow/calibration/__init__.py`
- Modify: `src/hogflow/__main__.py`
- Modify: `tests/test_autonomous_demo_orchestration.py`
- Modify: `tests/test_autonomous_demo_cli.py`

**Interfaces:**
- `AUTONOMOUS_CALIBRATION_ALGORITHM_VERSION = "phase_10_3c_a_v2"` is included in counting geometry and result fingerprints.
- `AutonomousDemoResult` remains path-free and adds no raw frame/tensor data.
- CLI JSON exposes `primary_count`, `line_count_range`, `detector_count_range`, `consistency_score`, `confidence`, `reason_codes`, and algorithm version.

- [x] **Step 1: Add failing assertions for versioned fingerprints and JSON fields.**
- [x] **Step 2: Pass primary-inclusive families and diagnostic values into result construction.**
- [x] **Step 3: Add algorithm version to result/geometry fingerprints without changing historical fingerprints.**
- [x] **Step 4: Add sanitized aggregate CLI serialization and preserve inconclusive exit behavior.**
- [x] **Step 5: Run orchestration/CLI tests.**

Run `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_autonomous_demo_orchestration.py tests/test_autonomous_demo_cli.py tests/test_autonomous_calibration_hardening.py -q`.

### Task 4: Add one controlled autonomous-run application bridge

**Files:**
- Create: `src/hogflow/application/autonomous_demo.py`
- Modify: `src/hogflow/application/ports.py`
- Modify: `src/hogflow/application/operator_service.py`
- Modify: `src/hogflow/application/__init__.py`
- Modify: `src/hogflow/bootstrap.py`
- Create: `tests/test_autonomous_demo_bridge.py`

**Interfaces:**
- `AutonomousDemoState` is an immutable enum with `IDLE`, `CALIBRATING`, `READY`, `COUNTING`, `LOW`, `INCONCLUSIVE`, `COMPLETE`, `FAILED`.
- `AutonomousDemoSnapshot` is immutable, bounded, path-free, and contains state, result summary, observed range, selected-line visibility, and failure category.
- `AutonomousDemoController.start(video_request) -> AutonomousDemoSnapshot`, `.snapshot() -> AutonomousDemoSnapshot`, `.close() -> None` owns at most one non-daemon run thread and rejects overlap with the existing pipeline worker or occupied shared lane.

- [x] **Step 1: Write failing lifecycle tests.**

Cover idle→calibrating→ready/counting, inconclusive not starting pass two, low warning, failure sanitization, duplicate start rejection, shutdown, and no second run while the normal pipeline worker is active.

- [x] **Step 2: Implement the controller as a bounded bridge.**

Use the existing `run_autonomous_demo` callback and a single joinable worker owned by the application boundary. Publish only immutable snapshots; never call Tkinter from the worker. Use the existing source request and frozen detector configuration supplied by bootstrap.

- [x] **Step 3: Add application protocol/service methods and composition wiring.**

Expose `start_autonomous_demo`, `autonomous_demo_snapshot`, and `stop_autonomous_demo` without adding persistence, queues, counters, or detector stacks. Keep normal `run` behavior unchanged.

- [x] **Step 4: Run bridge tests and existing application tests.**

Run `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_autonomous_demo_bridge.py tests/test_operator_application.py tests/test_operator_camera_integration.py -q`.

### Task 5: Integrate the autonomous workflow into the existing Tk HMI

**Files:**
- Modify: `src/hogflow/presentation/models.py`
- Modify: `src/hogflow/presentation/presenter.py`
- Modify: `src/hogflow/presentation/desktop.py`
- Modify: `src/hogflow/presentation/theme.py`
- Modify: `src/hogflow/presentation/__init__.py`
- Modify: `tests/test_operator_hmi_design.py`
- Modify: `tests/test_operator_desktop_scrolling.py`
- Modify: `tests/test_operator_presentation.py`

**Interfaces:**
- `OperatorAction.AUTO_CALIBRATE_COUNT` is snapshot-derived and enabled only for an explicit local file with no occupied lane/pipeline.
- `AutonomousDemoPanel` renders state, direction, lock state, consistency, observed range, reason, and truthful helper text.
- `OperatorScreen.autonomous_demo` is the only autonomous UI projection; no widget stores business state.

- [x] **Step 1: Write failing source-only HMI tests.**

Assert the new panel and action are inside the scrollable layout, render `CALIBRATING`, `READY`, `LOW`, `INCONCLUSIVE`, and `LIVE COUNT` states, hide business count during calibration, reveal the line only after lock, show “Observed consistency range”, never render “accuracy”, and reflow at 1920×1080 and 1366×768 without horizontal overflow.

- [x] **Step 2: Add presentation models and presenter projection.**

Translate the immutable application snapshot into semantic status tones and concise reason messages. Keep LIVE COUNT prominent and do not mix autonomous mode with camera health.

- [x] **Step 3: Add the compact panel and action to Tk.**

Place the panel in the camera/pipeline/action region, preserve the 2×2 docks, dark palette, keyboard focus, and 200 ms refresh. Disable/enable controls from snapshots only; no synchronous full-video inference in the Tk callback.

- [x] **Step 4: Run all HMI tests.**

Run `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_operator_hmi_design.py tests/test_operator_desktop_scrolling.py tests/test_operator_desktop.py tests/test_operator_presentation.py -q`.

### Task 6: Document hardened evidence and perform frozen real runs

**Files:**
- Modify: `docs/phase_10/phase_10_3c_a_autonomous_demo.md`
- Modify: `HOGFLOW_PROJECT_MEMORY.md`
- Create (ignored): `data/evaluation/phase10_3c_a/post_hardening_summary.json`

- [x] **Step 1: Preserve a pre-hardening subsection verbatim.**

Record the historical A/B/autonomous values, old score, old confidence, and historical fingerprints as pre-hardening evidence.

- [x] **Step 2: Run the frozen V2 on A, B, and the same autonomous demo video.**

Use Python 3.12.14, Torch 2.11.0+cu128, CUDA 12.8, Ultralytics 8.4.135, OpenCV 4.14.0.94, Supervision 0.29.1, and the existing V2 artifact. Do not inspect or select formal C candidates.

- [x] **Step 3: Record post-hardening metrics.**

Include all required aggregates, score, confidence, reason codes, FPS, latency, and explicit autonomous verdict. Do not add accuracy/count-error claims.

- [x] **Step 4: Update project memory only with verified facts.**

Keep formal Phase 10.3C blocked and state that no human ground truth was measured.

### Task 7: Final gates, review, publication, and stop

**Files:**
- Modify only source/tests/docs required by prior tasks.

- [x] **Step 1: Run full gates.**

Run `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m pytest`, `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m ruff check --no-cache .`, `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m ruff format --check --no-cache .`, `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m compileall -q src`, `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m pip check`, `git diff --check`, `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m hogflow --help`, and `D:\hogflow\.venv\phase10_3a\Scripts\python.exe -m hogflow autonomous-demo --help`.

- [x] **Step 2: Audit hygiene.**

Run `git status --ignored` and `git ls-files`; verify no media, frames, labels, models, traces, private paths, or local outputs are tracked.

- [x] **Step 3: Inspect diff and request review.**

Confirm only Phase 10.3C-A.1 source/tests/sanitized docs changed, formal Phase 10.3C remains untouched, and no roadmap phase beyond this subphase started.

- [ ] **Step 4: Commit and publish.**

Use descriptive commits for the scoped changes, push to `origin/main`, verify local `HEAD` equals `origin/main`, and report the actual CI run/conclusion.

- [ ] **Step 5: Stop.**

Do not select/annotate/evaluate Video C, retrain V2, start persistence, Phase 10.4, Phase 11, analytics, or UI redesign.
