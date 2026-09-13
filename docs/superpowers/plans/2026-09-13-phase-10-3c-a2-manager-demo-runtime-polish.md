# Phase 10.3C-A.2 Manager Demo Runtime Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing frozen autonomous pig demo visibly play, publish latest-frame preview and frame-by-frame technical counts, cancel cooperatively, and remain unavailable unless the frozen V2 detector is configured.

**Architecture:** Reuse the existing `LatestPreviewFrameChannel` as the single-slot autonomous visual port and keep the existing detector → ByteTrack → crossing → `LifecycleDirectionalCounter` composition. Extend the autonomous application bridge with immutable bounded snapshots and one `threading.Event`; the Tk thread remains the only renderer and the autonomous count never mutates the Phase 8 lane.

**Tech Stack:** Python 3.12, immutable dataclasses, OpenCV/Ultralytics adapters, Tkinter, existing preview render plan, pytest, Ruff.

**Spec:** User-provided Phase 10.3C-A.2 requirements.

## Global Constraints

- Preserve Phase 10.3C-A.1 mathematics and `phase_10_3c_a_v2`.
- Do not inspect/select/annotate/evaluate Video C.
- Do not retrain or modify `hogflow_pig_demo_v2`.
- Reuse one detector, one tracker, one crossing path, one autonomous worker, and one latest-frame slot.
- Do not mutate Phase 8 business counts or persist autonomous demo state.
- Keep local media, model weights, frames, overlays, paths, and reports ignored/untracked.
- Preserve `DEMO MODEL — NOT PRODUCTION VALIDATED` and `AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED`.

---

### Task 1: Baseline, architecture, and UX audit

**Files:**
- Create: `docs/superpowers/plans/2026-09-13-phase-10-3c-a2-manager-demo-runtime-polish.md`
- Inspect: `src/hogflow/application/autonomous_demo.py`, `src/hogflow/calibration/orchestration.py`, `src/hogflow/camera/preview_channel.py`, `src/hogflow/presentation/`, `src/hogflow/bootstrap.py`, detector runtime models.
- Test: full existing suite before edits.

**Interfaces:**
- Baseline SHA must be recorded as `4764bbf2feec4625402e2a85a2c757f38c5241a2` unless Git reports a different HEAD.
- Existing preview remains latest-frame-only; no second channel is introduced unless reuse is technically impossible.

- [x] **Step 1: Record repository and environment baseline.**

Run the repository baseline commands (`git status`, `git branch --show-current`, `git rev-parse HEAD`, `git remote -v`, and the project Python interpreter with `-m pytest`).

- [x] **Step 2: Read project documents and UI guidance.**

Read `AGENTS.md`, `HOGFLOW_PROJECT_CONTEXT.md`, `HOGFLOW_PROJECT_MEMORY.md`, `INVENTION_LOG.md`, `MARKET_RESEARCH.md`, `README.md`, and the relevant `ui-ux-pro-max` guidance/search results. Preserve the dark industrial layout and existing 200 ms refresh.

- [x] **Step 3: Write the implementation plan and freeze scope.**

Confirm that only runtime polish is in scope; no consistency-metric changes, model changes, Video C work, persistence, Phase 10.4, or Phase 11.

---

### Task 2: Add bounded runtime event and preview contracts

**Files:**
- Modify: `src/hogflow/application/autonomous_demo.py`
- Modify: `src/hogflow/camera/preview_channel.py` only if reset/ownership reuse needs a narrow extension.
- Modify: `src/hogflow/calibration/orchestration.py` callback signatures.
- Test: `tests/test_autonomous_demo_bridge.py`, new source-only runtime/preview tests.

**Interfaces:**
- Add immutable bounded progress data carrying stage, frame sequence, current technical count, crossing-event total, processed frames, and optional latest `PreviewFrame`.
- Preserve a single latest-frame slot; the worker publishes by replacement and never calls Tk.
- `run_autonomous_demo(..., progress_callback=...)` checks a callable stop predicate between frames/passes and reports count progress during pass 2.

- [x] **Step 1: Add failing tests for intermediate count snapshots and latest-frame replacement.**

Use synthetic `PreviewFrame` payloads and a fake count pass that reports `0, 1, 2, 3`; assert no list/history is created and the newest frame replaces the older slot.

- [x] **Step 2: Implement immutable progress/event models.**

Keep fields path-free, bounded, and framework-neutral. Reuse `PreviewFrame` rather than adding a second image format.

- [x] **Step 3: Thread cancellation and progress through orchestration.**

Check the stop predicate before calibration, between calibration frames, between diagnostic passes, before pass 2, and between count frames. Report every count-frame update through the callback without storing history.

- [x] **Step 4: Run focused orchestration and preview tests.**

Run the project Python interpreter with `-m pytest tests/test_autonomous_demo_orchestration.py tests/test_autonomous_demo_bridge.py tests/test_preview_channel.py -q`.

---

### Task 3: Harden the autonomous controller lifecycle

**Files:**
- Modify: `src/hogflow/application/autonomous_demo.py`
- Modify: `src/hogflow/application/ports.py`
- Test: `tests/test_autonomous_demo_bridge.py`.

**Interfaces:**
- Extend `AutonomousDemoSnapshot` with `live_count`, `frames_processed`, `crossing_events`, `failure_category`, and bounded latest preview metadata/frame access.
- Add `cancel()`, make `close()` request cancellation and wait for the configured bounded timeout, and add `CANCELLED` distinct from `FAILED`.
- Keep exactly one non-daemon worker; duplicate starts and active-run overlap remain rejected.

- [x] **Step 1: Add lifecycle tests.**

Cover cancellation during calibration, cancellation during count, close while active, no lingering worker, duplicate start, inconclusive no-pass-two, failure sanitization, and reusable start after cancellation.

- [x] **Step 2: Implement the stop event and bounded worker joins.**

Use one `threading.Event`, clear it on start, set it on cancel/close, and translate an expected stop into `CANCELLED` rather than `FAILED`.

- [x] **Step 3: Publish live count and preview snapshots.**

The controller replaces one immutable snapshot per callback; it never owns business count, lane state, queues, or frame history.

- [x] **Step 4: Run controller/application regression tests.**

Run the project Python interpreter with `-m pytest tests/test_autonomous_demo_bridge.py tests/test_operator_application.py tests/test_operator_camera_integration.py tests/test_camera_pipeline_controller.py -q`.

---

### Task 4: Enforce frozen V2 detector readiness

**Files:**
- Modify: `src/hogflow/application/operator_service.py`
- Modify: `src/hogflow/bootstrap.py`
- Modify: `src/hogflow/presentation/models.py`, `presenter.py`, `desktop.py`.
- Test: new source-only detector-gate and action-state tests.

**Interfaces:**
- Auto Demo is enabled only for a configured local file, free lane, stopped normal pipeline, idle autonomous worker, and a compatible non-empty V2 configuration.
- Reject empty backend, wrong target class/ID, threshold, IoU, image size, max detections, half precision, or mismatched loaded artifact fingerprint with sanitized errors.
- Expose compact detector state in the existing pipeline diagnostics without paths or accuracy claims.

- [x] **Step 1: Add failing gate/action tests.**

Test EMPTY, wrong class/settings/fingerprint, correct V2 settings, active pipeline, active lane, and active autonomous worker.

- [x] **Step 2: Implement configuration and runtime provenance checks.**

Validate immutable settings before starting and verify artifact identity after the detector loads where the adapter exposes it.

- [x] **Step 3: Add explicit start/cancel action state.**

Show `AUTO CALIBRATE & COUNT` while idle and `CANCEL AUTO DEMO` while active; do not infer availability from button text.

- [x] **Step 4: Run detector/application/presentation tests.**

Run the focused gate/action/HMI suites and preserve architecture boundaries.

---

### Task 5: Integrate autonomous preview/count into the Tk HMI

**Files:**
- Modify: `src/hogflow/presentation/presenter.py`
- Modify: `src/hogflow/presentation/desktop.py`
- Modify: `src/hogflow/presentation/preview.py` only if a bounded autonomous overlay requires it.
- Test: `tests/test_operator_presentation.py`, `tests/test_operator_live_preview.py`, `tests/test_operator_hmi_design.py`, new source-only HMI tests.

**Interfaces:**
- Preview producer selection is mutually exclusive: autonomous latest frame wins while the current autonomous run is active; normal pipeline preview resumes after clear/complete.
- Calibration hides candidate/default lines; the selected line appears only after lock and remains through pass 2/complete.
- The prominent count shows `CALIBRATING…`, then intermediate autonomous count, and final count; LOW remains amber through COMPLETE; INCONCLUSIVE/CANCELLED/FAILED remain truthful.

- [x] **Step 1: Add source-only HMI state tests.**

Assert CALIBRATING, COUNTING with live count, COMPLETE, LOW, INCONCLUSIVE, CANCELLED, detector-not-loaded, line-lock visibility, and no accuracy copy.

- [x] **Step 2: Project autonomous snapshots and detector state.**

Keep the existing snapshot-driven presenter and dark industrial semantic tones; do not store business state in widgets.

- [x] **Step 3: Add the context-sensitive cancel button and live preview selection.**

Use the existing 200 ms refresh; keep all Tk calls on the UI thread and clear autonomous frames on source change, cancel, new run, and shutdown.

- [x] **Step 4: Run all presentation/desktop tests.**

Run the project Python interpreter with `-m pytest tests/test_operator_presentation.py tests/test_operator_live_preview.py tests/test_operator_hmi_design.py tests/test_operator_desktop_scrolling.py -q`.

---

### Task 6: Documentation, local smoke, quality gates, and publication

**Files:**
- Modify: `docs/phase_10/phase_10_3c_a_autonomous_demo.md`
- Modify: `HOGFLOW_PROJECT_MEMORY.md`
- Modify: this plan with completed checkboxes.
- Never add: video, frame, model, screenshot, overlay, or local-path artifacts.

**Interfaces:**
- Documentation records A.2 runtime behavior and manual smoke status without changing A.1 evidence or claiming human accuracy.
- Final status must retain `AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED` and `DEMO MODEL — NOT PRODUCTION VALIDATED`.

- [x] **Step 1: Run same-video runtime smoke.**

Use only the already-selected autonomous demo video. Verify visible calibration playback, line lock, clean pass-two restart, intermediate counts, completion, cancellation, and close behavior; record actual outcomes without forcing count 6.

- [x] **Step 2: Run final gates.**

Run pytest, Ruff check/format, compileall, pip check, git diff check, CLI help, and the architecture/hygiene checks.

- [x] **Step 3: Inspect privacy and diff scope.**

Confirm no formal C work, no algorithm drift, no media/model files, no second runtime, no persistence, and no business-count mutation.

- [x] **Step 4: Commit, push, and verify CI.**

Use a descriptive commit, push `origin/main`, verify `HEAD == origin/main`, and retrieve the actual GitHub Actions run conclusion.

- [x] **Step 5: Stop at Phase 10.3C-A.2.**

Do not select Video C, retrain V3, start persistence, Phase 10.4, Phase 11, analytics, or dock/workflow changes.
