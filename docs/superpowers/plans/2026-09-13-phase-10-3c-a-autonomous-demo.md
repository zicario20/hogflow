# Phase 10.3C-A Autonomous Counting Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Add a framework-neutral autonomous calibration preflight that uses frozen V2 plus the existing ByteTrack/crossing/counter pipeline to select a safe counting line, run a clean two-pass local-video demo, and report AI self-consistency without claiming human accuracy.

**Architecture:** Add `hogflow.calibration` as a pure bounded-analysis layer over sanitized trajectory observations. Add one orchestration route that owns source/detector/tracker lifecycles, performs calibration without an active count, resets state, and replays the same source through the existing counting pipeline. Add a deterministic `autonomous-demo` CLI route and sanitized reporting; do not add a second detector, tracker, counter, or crossing implementation.

**Tech Stack:** Python 3.12, immutable dataclasses, existing `NormalizedLine`, `LiveCrossingConfiguration`, `VirtualLineCrossingDetector`, `LifecycleDirectionalCounter`, `CameraSource`, `LiveDetector`, `LiveTracker`, Supervision ByteTrack 0.29.1, Ultralytics V2, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-13-phase-10-3c-a-autonomous-demo-design.md`

## Global Constraints

- V2 artifact SHA remains `892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c`.
- Detector settings remain `imgsz=640`, confidence `0.25`, NMS IoU `0.5`, `max_det=300`, class `pig/0`.
- ByteTrack remains Supervision `0.29.1` with fingerprint `a7dff46135c238a62d7658d9878e85909ddb63ce30ae53344bf133fef6594c89`.
- Calibration never opens a business counting session or emits operational crossing events.
- Calibration state is reset before the official count pass; active-session replay guard remains authoritative.
- Autonomous evidence is called self-consistency only: `AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED`.
- Formal Phase 10.3C human-validation documentation remains unchanged.
- Real videos, frames, labels, weights, overlays, trajectories, and local runs stay ignored and untracked.
- CI uses synthetic observations/media only; no real model or video is required by tests.
- No Phase 10.4, persistence, Phase 11, dashboard, cloud AI, or model training work is included.

---

### Task 1: Add bounded calibration models and package boundary

**Files:**
- Create: `src/hogflow/calibration/__init__.py`
- Create: `src/hogflow/calibration/models.py`
- Test: `tests/test_autonomous_calibration_models.py`

**Interfaces:**
- Produce `CalibrationStatus`, `CalibrationConfidence`, `TrajectoryObservation`, `TrajectorySummary`, `CorridorEstimate`, `LineCandidate`, `LineCandidateMetrics`, `CountingGeometryConfiguration`, and `AutonomousCalibrationResult`.
- Every result is frozen, path-free, frame-free, tensor-free, and bounded.
- `CountingGeometryConfiguration.fingerprint` hashes canonical JSON containing detector/model fingerprints, tracker fingerprint, line endpoints, direction, crossing epsilon/retention, algorithm version, and settings.

- [ ] **Step 1: Write failing model tests.**

```python
def test_counting_configuration_fingerprint_is_stable_and_path_free() -> None:
    first = counting_configuration()
    second = counting_configuration()
    assert first.fingerprint == second.fingerprint


def test_result_rejects_more_than_64_sampled_centers() -> None:
    with pytest.raises(InputDataError):
        valid_summary(sampled_centers=tuple((0.1, 0.2) for _ in range(65)))
```

- [ ] **Step 2: Run the focused tests and verify they fail because the models do not exist.**

Run: `.venv/phase10_3a/Scripts/python.exe -m pytest tests/test_autonomous_calibration_models.py -q`

- [ ] **Step 3: Implement immutable models with finite normalized coordinates, bounded samples, enum validation, SHA-256 fingerprints, and sanitized text. Keep framework imports out of the package.**

- [ ] **Step 4: Run focused tests and existing crossing/tracking model tests.**

Run: `.venv/phase10_3a/Scripts/python.exe -m pytest tests/test_autonomous_calibration_models.py tests/test_live_crossing_models.py tests/test_live_tracking_models.py -q`

- [ ] **Step 5: Commit.**

```powershell
git add src/hogflow/calibration tests/test_autonomous_calibration_models.py
git commit -m "Add autonomous calibration result models"
```

### Task 2: Implement deterministic trajectory accumulation and motion geometry

**Files:**
- Create: `src/hogflow/calibration/engine.py`
- Test: `tests/test_autonomous_calibration_engine.py`

**Interfaces:**
- `AutonomousCalibrationSettings` stores minimum lifetime `8`, minimum normalized displacement `0.04`, maximum sampled centers `64`, corridor percentiles `10/90`, candidate positions `(0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)`, neighbor offsets `(-0.04, -0.02, 0.02, 0.04)`, and diagnostic confidences `(0.20, 0.30)`.
- `AutonomousCalibrationEngine.observe(observation: TrajectoryObservation) -> None` keeps bounded tracker summaries/samples.
- `AutonomousCalibrationEngine.finish() -> AutonomousCalibrationResult` computes eligibility, direction, purity, corridor, candidates, and a preliminary result.
- Pure functions: `estimate_dominant_direction`, `estimate_corridor`, `generate_line_candidates`, and `score_candidate`.

- [ ] **Step 1: Write failing tests for vertical, horizontal, diagonal, bidirectional, short-track, jitter, bounded-history, perpendicularity, corridor percentiles, edge rejection, and deterministic ordering.**

```python
def test_bidirectional_flow_is_inconclusive_without_a_fabricated_line() -> None:
    result = calibrate(opposing_observations())
    assert result.status is CalibrationStatus.INCONCLUSIVE
    assert result.selected_line is None
```

- [ ] **Step 2: Run the focused tests and verify expected missing-symbol failures.**

Run: `.venv/phase10_3a/Scripts/python.exe -m pytest tests/test_autonomous_calibration_engine.py -q`

- [ ] **Step 3: Implement bounded accumulation, robust vector aggregation, percentile corridor estimation, normalized perpendicular candidate generation, and safety rejection. Reject weak resultant direction, low evidence, edge-adjacent segments, degenerate segments, and candidates without both pre/post space.**

- [ ] **Step 4: Implement deterministic score components and confidence tiers. Use the approved weights: direction `.25`, unique-forward `.20`, continuity `.20`, neighbor agreement `.15`, corridor coverage `.10`, perturbation agreement `.10`, with reverse `.10`, multiple-cross `.10`, lost-near-line `.10`, and edge `.05` penalties; clip `[0,1]`; tie-break by minimum neighbor agreement, continuity, then candidate ID.**

- [ ] **Step 5: Run focused tests, refactor only after green, and commit.**

```powershell
git add src/hogflow/calibration/engine.py tests/test_autonomous_calibration_engine.py
git commit -m "Implement bounded autonomous motion calibration"
```

### Task 3: Add analysis-only crossing metrics and consistency variants

**Files:**
- Modify: `src/hogflow/calibration/engine.py`
- Create: `tests/test_autonomous_calibration_consistency.py`

**Interfaces:**
- `evaluate_candidate_tracks(candidate, summaries) -> LineCandidateMetrics` uses existing normalized geometry semantics but never updates the operational counter.
- `neighbor_counts(candidate, summaries, offsets) -> tuple[int, ...]` evaluates only declared line offsets.
- `detector_perturbation_counts(primary_count, diagnostic_counts)` records confidence `0.20/0.30` diagnostics without changing the official threshold.
- `line_band_agreement`, `relative_spread`, and `consistency_confidence` are deterministic and bounded.

- [ ] **Step 1: Write failing tests for one-forward-crossing ratio, reverse penalty, pre/post continuity, neighbor spread, perturbation stability, confidence tiers, and deterministic tie-breaking.**

```python
def test_neighbor_band_prefers_stable_candidate() -> None:
    stable = line_metrics(neighbor_counts=(50, 51, 51, 52))
    unstable = line_metrics(neighbor_counts=(34, 67, 40, 59))
    assert stable.neighbor_agreement > unstable.neighbor_agreement
```

- [ ] **Step 2: Run focused tests and verify they fail before implementation.**

Run: `.venv/phase10_3a/Scripts/python.exe -m pytest tests/test_autonomous_calibration_consistency.py -q`

- [ ] **Step 3: Implement metrics with explicit denominators. A track enters the uniqueness denominator only if its bounded trajectory reaches the candidate safe corridor; exactly one forward crossing is the numerator.**

- [ ] **Step 4: Run focused tests, then all calibration tests, and commit.**

```powershell
git add src/hogflow/calibration/engine.py tests/test_autonomous_calibration_consistency.py
git commit -m "Add autonomous line consistency metrics"
```

### Task 4: Add deterministic autonomous demo candidate selection

**Files:**
- Create: `src/hogflow/calibration/video_selection.py`
- Test: `tests/test_autonomous_demo_selection.py`

**Interfaces:**
- `select_autonomous_demo_candidate(candidates, excluded_names, suitability_probe) -> AutonomousVideoSelection` excludes A/B and the three historical basenames, hashes sanitized basenames for ordering, and selects the first readable/suitable candidate without comparing performance.
- `AutonomousVideoSelection` contains only sanitized candidate ID, selection rank, metadata, and rejection reasons; serialized output never contains an absolute path.

- [ ] **Step 1: Write failing tests for exclusion, deterministic order, first-suitable selection, unreadable rejection, and no-candidate failure.**

```python
def test_selection_never_chooses_by_count_or_score() -> None:
    result = select_autonomous_demo_candidate(candidates, excluded, probe)
    assert result.candidate_id == "autonomous_demo_video_1"
    assert result.selection_reason == "first_suitable_in_sanitized_hash_order"
```

- [ ] **Step 2: Run focused tests and verify intended failures.**

Run: `.venv/phase10_3a/Scripts/python.exe -m pytest tests/test_autonomous_demo_selection.py -q`

- [ ] **Step 3: Implement SHA-256 sanitized-basename ordering and bounded metadata/sample probing. Do not decode all candidates before deterministic order reaches each candidate.**

- [ ] **Step 4: Run focused tests and commit.**

```powershell
git add src/hogflow/calibration/video_selection.py tests/test_autonomous_demo_selection.py
git commit -m "Add deterministic autonomous demo video selection"
```

### Task 5: Implement the framework adapter and two-pass local-video orchestration

**Files:**
- Create: `src/hogflow/calibration/orchestration.py`
- Create: `tests/test_autonomous_demo_orchestration.py`
- Modify: `src/hogflow/calibration/__init__.py`

**Interfaces:**
- `AutonomousDemoConfiguration` carries the frozen `PigDetectorConfiguration`, `ByteTrackConfiguration`, calibration settings, crossing epsilon/retention, and sanitized demo ID.
- `run_autonomous_demo(configuration, source_factory, detector_factory, tracker_factory, clock) -> AutonomousDemoResult` performs calibration, explicit reset, count pass, and bounded runtime aggregation.
- `AutonomousDemoResult` contains calibration result, primary count, variant summaries, source/pipeline FPS, latencies, detector/tracker/crossing failures, HMI state, and limitations.
- The adapter converts `TrackingResult.tracked_objects` to `TrajectoryObservation` using `FramePacket`; no framework object enters calibration models.

- [ ] **Step 1: Write failing synthetic orchestration tests.** Assert calibration emits no counter events, tracker/crossing/counter reset occurs before pass 2, pass 2 starts at sequence zero, and inconclusive calibration never starts counting.

```python
def test_calibration_does_not_leak_into_second_pass_count() -> None:
    result = run_autonomous_demo(
        synthetic_configuration(),
        source_factory=synthetic_source_factory,
        detector_factory=synthetic_detector_factory,
        tracker_factory=synthetic_tracker_factory,
        clock=FakeClock(),
    )
    assert result.calibration_events == 0
    assert result.pass_two_first_frame_sequence == 0
```

- [ ] **Step 2: Run focused tests and verify the missing orchestrator failure.**

Run: `.venv/phase10_3a/Scripts/python.exe -m pytest tests/test_autonomous_demo_orchestration.py -q`

- [ ] **Step 3: Implement source EOF/lifecycle ownership with existing `CameraSource`, `LiveDetector`, `LiveTracker`, `TrackingRequest`, and `VirtualLineCrossingDetector` contracts. Calibration must not open a business session.**

- [ ] **Step 4: Implement reset and pass-2 lifecycle using fresh counter/crossing lifecycle; never bypass the replay guard.**

- [ ] **Step 5: Add cleanup, insufficient-evidence, and active-session replay tests; run all calibration/orchestration tests; commit.**

```powershell
git add src/hogflow/calibration tests/test_autonomous_demo_orchestration.py
git commit -m "Add two-pass autonomous counting orchestration"
```

### Task 6: Add the autonomous-demo CLI route and sanitized output

**Files:**
- Modify: `src/hogflow/__main__.py`
- Create: `tests/test_autonomous_demo_cli.py`
- Modify: `src/hogflow/calibration/__init__.py`

**Interfaces:**
- Extend the top-level parser with `autonomous-demo` while preserving `run` behavior/help.
- Require the explicit local video or deterministic selection mode, frozen model/provenance, and exact frozen detector settings; reject mismatches before execution.
- `main()` returns a sanitized bounded summary and nonzero error for inconclusive calibration; output never contains private absolute paths.

- [ ] **Step 1: Write failing parser tests for subcommand/help, frozen settings, path-free output, and inconclusive exit behavior.**
- [ ] **Step 2: Run focused tests and verify failure because the route is absent.**
- [ ] **Step 3: Implement the route using existing argument conventions; do not alter `run` semantics.**
- [ ] **Step 4: Run focused tests and `python -m hogflow autonomous-demo --help`.**
- [ ] **Step 5: Commit.**

```powershell
git add src/hogflow/__main__.py src/hogflow/calibration tests/test_autonomous_demo_cli.py
git commit -m "Add autonomous demo counting command"
```

### Task 7: Execute A/B sanity calibration and one deterministic autonomous demo

**Files:**
- Create ignored local outputs: `data/evaluation/phase10_3c_a/`
- Create: `docs/phase_10/phase_10_3c_a_autonomous_demo.md`
- Modify: `HOGFLOW_PROJECT_MEMORY.md`
- Test: `tests/test_phase_10_3c_a_boundaries.py`

**Interfaces:**
- Use frozen GPU V2/ByteTrack; A and B are algorithm-sanity development evidence only, with no human totals.
- Select exactly one autonomous demo candidate via the deterministic selector and run it once after selection.
- Persist only sanitized aggregate JSON/Markdown under ignored evaluation roots; committed docs contain IDs and aggregate metrics only.

- [ ] **Step 1: Write failing boundary tests for no accuracy claims, formal 10.3C report preservation, one-active-model gate, ignored outputs, and no media/model tracking.**
- [ ] **Step 2: Run boundary tests and verify intended failures.**
- [ ] **Step 3: Execute A and B calibration; record direction, purity, corridor, selected line, eligible tracks, line-band counts, score, confidence, runtime, and failures. If inconclusive, do not force a line.**
- [ ] **Step 4: Select `autonomous_demo_video_1` by suitability order, execute calibration/reset/pass 2, and never replace it based on results.**
- [ ] **Step 5: Review bounded outputs, verify no frames/trajectories/paths retained, and write the report with `AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED`.**
- [ ] **Step 6: Update memory in a separate 10.3C-A subsection while preserving the formal 10.3C block.**
- [ ] **Step 7: Commit source/tests/docs only.**

```powershell
git add docs/phase_10/phase_10_3c_a_autonomous_demo.md HOGFLOW_PROJECT_MEMORY.md tests/test_phase_10_3c_a_boundaries.py
git commit -m "Document autonomous counting consistency evidence"
```

### Task 8: Run gates, review, push, and verify CI

**Files:**
- Modify only files required by failed gates or reviewer findings.

- [ ] **Step 1: Run exact gates.**

```powershell
.venv/phase10_3a/Scripts/python.exe -m pytest
.venv/phase10_3a/Scripts/python.exe -m ruff check --no-cache .
.venv/phase10_3a/Scripts/python.exe -m ruff format --check --no-cache .
.venv/phase10_3a/Scripts/python.exe -m compileall -q src
.venv/phase10_3a/Scripts/python.exe -m pip check
git diff --check
.venv/phase10_3a/Scripts/python.exe -m hogflow --help
.venv/phase10_3a/Scripts/python.exe -m hogflow run --help
.venv/phase10_3a/Scripts/python.exe -m hogflow autonomous-demo --help
```

- [ ] **Step 2: Verify `git status --ignored`, `git ls-files`, one active model candidate, ignored evaluation roots, and no media/weights/frames/labels tracked.**
- [ ] **Step 3: Request focused code review against the design and plan; fix Critical/Important findings before merge.**
- [ ] **Step 4: Push `main` normally and poll GitHub Actions to terminal conclusion.**
- [ ] **Step 5: Report status/verdict, baseline/final SHA, frozen model, algorithm, A/B results, demo selection, counts/consistency, runtime/HMI, tests, Git/CI, and both disclaimers.**

## Plan self-review

- The formal human-validation report is never rewritten.
- No task trains or changes V2.
- Every production-code task begins with a failing synthetic test.
- Calibration is analysis-only and reset before pass 2.
- Candidate selection is deterministic and not performance-based.
- Real media remains outside CI and version control.
- The plan stops before persistence, Phase 10.4, Phase 11, and later phases.
