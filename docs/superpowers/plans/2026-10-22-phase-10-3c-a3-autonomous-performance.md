# Phase 10.3C-A.3 Autonomous Performance Implementation Plan

> **For agentic workers:** This plan is executed inline under the explicit user authorization in the phase request. Keep each checkbox testable and preserve all Phase 10.3C-A.2 boundaries.

**Goal:** Make the frozen autonomous demo ready for repeatable local counting tests by reusing compact tracking evidence when safe, emitting bounded run reports, and exposing truthful performance diagnostics without changing V2 or business counting.

**Architecture:** Keep one detector, one ByteTrack instance per inference pass, one existing crossing detector and one `LifecycleDirectionalCounter`. The calibration pass may retain only compact immutable `TrackingResult` records under a frame cap; the count pass replays those tracks while decoding the video for preview, falling back to the current detector pass if the cache is incomplete. A report writer emits sanitized JSON/Markdown under ignored local roots.

**Tech Stack:** Python 3.12, dataclasses, OpenCV/Ultralytics adapters, Tkinter, pytest, Ruff, psutil/pynvml when available.

**Spec:** User-provided `HOGFLOW — PHASE 10.3C-A.3 Autonomous Counting Test & Performance Optimization`.

## Global Constraints

- Preserve `hogflow_pig_demo_v2`, its SHA, frozen settings, ByteTrack, `LiveDirectionalCounter`, four docks, one shared lane, historical evidence, and Video C reservation.
- No datasets, V3 training, human annotations/counts, production persistence, or model/pipeline replacement.
- Autonomous numbers are `AUTONOMOUS ESTIMATE — NOT INDEPENDENTLY VERIFIED`.
- No frame/video history is retained; compact replay data is bounded and contains no pixels.
- Tests use synthetic sources; real runs use only already-authorized ignored local media.

---

### Task 1: Baseline and failing contracts

**Files:**
- Inspect: `src/hogflow/calibration/orchestration.py`, `src/hogflow/calibration/models.py`, `src/hogflow/__main__.py`, presentation files.
- Test: `tests/test_autonomous_demo_orchestration.py`, new A.3 tests.

- [x] Record clean HEAD, V2 fingerprint, environment, and A.2 baseline on the selected local demo video.
- [x] Add failing synthetic tests proving an optimized run replays compact tracking evidence, reports inference-pass count, and preserves the legacy count.
- [x] Add failing report serialization tests with no local paths or pixels.

### Task 2: Bounded tracking replay optimization

**Files:**
- Modify: `src/hogflow/calibration/orchestration.py` and its immutable result/configuration models.
- Test: `tests/test_autonomous_demo_orchestration.py`, new `tests/test_autonomous_performance.py`.

- [x] Add a bounded replay-frame record and capture primary tracking results only up to a configured cap.
- [x] Replay the existing tracking results through the existing crossing/counter while reading current video frames for preview.
- [x] Preserve a legacy mode and fall back when replay evidence is incomplete; expose `cache_replay_used` and `inference_passes`.
- [x] Verify synthetic forward/reverse/duplicate/cancellation semantics remain unchanged.

### Task 3: Sanitized run reports and benchmark command

**Files:**
- Create: `src/hogflow/calibration/reporting.py`.
- Modify: `src/hogflow/__main__.py`, `src/hogflow/calibration/__init__.py`.
- Test: `tests/test_autonomous_demo_cli.py`, new `tests/test_autonomous_reporting.py`.

- [x] Add deterministic JSON/Markdown reports containing run ID, logical video ID/hash, model hash, configuration, line, direction, counts, tracks, FPS, latency, pass count, cache mode, warnings, and explicit non-verification wording.
- [x] Write only below ignored `data/runs`/`data/metrics` roots and never serialize absolute paths or pixels.
- [x] Add an explicit benchmark option that runs legacy and optimized modes under identical configuration and reports before/after values.

### Task 4: Manager-demo presentation polish

**Files:**
- Modify: `src/hogflow/presentation/models.py`, `presenter.py`, `desktop.py` only where existing A.2 contracts lack restart/report affordances.
- Test: `tests/test_phase_10_3c_a3_hmi.py` and existing HMI suites.

- [x] Keep `AUTO CALIBRATE & COUNT`, `CANCEL`, latest-frame preview and technical live count unchanged.
- [x] Reuse the existing bounded `Restart Video` action for repeat tests and add `VIEW REPORT`, enabled only after a completed local Markdown report exists. The HMI opens it through the host OS without exposing the path.
- [x] Preserve dark industrial tones, blue informational LIVE MODE, amber LOW, and no accuracy claims.

### Task 5: Real local benchmark, documentation, and gates

**Files:**
- Modify: `docs/phase_10/phase_10_3c_a_autonomous_demo.md`, `HOGFLOW_PROJECT_MEMORY.md`.
- Never add: media, weights, frames, screenshots, or reports to Git.

- [x] Run A.2 and A.3 on the same already-selected demo video and compare count, pass count, total time, FPS, latency, RAM/VRAM availability, and cancellation behavior.
- [x] Investigate any count difference before accepting the optimization; counts and directional events were unchanged.
- [x] Run full tests, Ruff, format, compile, pip check, CLI help, hygiene checks, commit, push, and verify CI.
