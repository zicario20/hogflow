# Phase 10.3C-A — Autonomous Counting Calibration & AI Consistency Validation

## Status and scope

This design adds an autonomous demonstration path underneath Phase 10.3. It
does not replace or weaken the formal Phase 10.3C human-ground-truth path.

The autonomous path may choose a local demo video, infer a counting geometry,
run a clean two-pass count, and report bounded self-consistency. It must never
call that result accuracy, ground truth, human-equivalent truth, certification,
or production readiness.

The formal human-validation document remains unchanged:
`docs/phase_10/phase_10_3c_independent_validation.md`.

## Goals

1. Keep the frozen V2 detector and current Supervision ByteTrack configuration
   unchanged.
2. Infer dominant pig motion and a plausible counting corridor from bounded
   trajectory summaries.
3. Generate and score a small deterministic set of perpendicular line
   candidates using self-consistency metrics.
4. Lock one line/configuration before the official count pass.
5. Reset all transient detector, tracker, crossing, counter, preview, and
   calibration state between calibration and counting.
6. Produce a manager-readable autonomous count with direction, selected line,
   confidence tier, consistency variants, runtime metrics, and limitations.
7. Preserve the existing detector → tracker → crossing → counter → HMI
   architecture and replay guard.

## Non-goals

- No V2 retraining, V3, ensemble, pseudo-labeling, or external model.
- No second detector, tracker, counter, or crossing algorithm.
- No human count fabrication and no precision/recall/F1 without boxes.
- No claim of count accuracy or production readiness.
- No persistence, Phase 10.4, Phase 11, dashboard, PostgreSQL, SignalR, or
  cloud/SaaS processing.
- No continuous line movement during an active count.

## Architecture

The new layer is framework-neutral and receives tracker observations through a
small protocol. It is placed before an active counting lifecycle:

```text
Frozen PigDetectorConfiguration/V2
        ↓
Existing UltralyticsLiveDetector
        ↓
Existing Supervision ByteTrack
        ↓
Bounded trajectory observations
        ↓
AutonomousCalibrationEngine
        ↓
Immutable CountingGeometryConfiguration
        ↓
Existing VirtualLineCrossingDetector
        ↓
Existing LifecycleDirectionalCounter / SharedCountingLane / HMI
```

The engine must not import Ultralytics, OpenCV, Supervision, Tkinter, or
presentation code. A small orchestration adapter owns framework objects and
converts their outputs into bounded observations.

## Proposed modules and contracts

### `src/hogflow/calibration/models.py`

Frozen dataclasses/enums with validation and deterministic serialization:

- `CalibrationStatus`: `READY`, `INCONCLUSIVE`, `FAILED`.
- `CalibrationConfidence`: `HIGH`, `MEDIUM`, `LOW`, `INCONCLUSIVE`.
- `CalibrationPoint` and `TrajectorySummary` containing only bounded scalar
  and tuple data: tracker ID, first/last frame, first/last center, sampled
  centers (bounded), lifetime, displacement, path length, direction, continuity,
  confidence summary, and edge flags.
- `CorridorEstimate`: normalized along-flow and cross-flow bounds plus margins.
- `LineCandidateMetrics`: candidate geometry, crossing/continuity/penalty
  aggregates, neighbor counts, detector perturbation counts, and score.
- `CountingGeometryConfiguration`: selected normalized line, positive
  direction, crossing settings, tracker fingerprint, detector fingerprints,
  algorithm version, and its SHA-256 fingerprint.
- `AutonomousCalibrationResult`: status, direction, purity, corridor,
  selected candidate, bounded candidate metrics, confidence, consistency score,
  fingerprint, and limitations. It contains no frames, tensors, model objects,
  or unbounded history.

### `src/hogflow/calibration/engine.py`

Pure deterministic operations:

- bounded trajectory accumulation with explicit maximum tracks and samples;
- eligibility filtering;
- robust dominant-direction estimation;
- corridor estimation in along/cross normalized coordinates;
- perpendicular candidate generation;
- safety rejection;
- candidate metrics and transparent score calculation;
- confidence tier selection;
- deterministic result/configuration fingerprints.

Suggested default constants are conservative and explicit, not tuned against a
hidden result: minimum lifetime 8 frames, minimum normalized displacement 0.04,
maximum sampled centers 64 per track, corridor percentiles 10/90, candidate
positions 35/40/45/50/55/60/65/70 percent of robust travel, neighbor offsets
-4/-2/0/+2/+4 percent, and detector diagnostic confidences 0.20/0.25/0.30.
These values are configuration data and are recorded in the result fingerprint.

### `src/hogflow/calibration/orchestration.py`

Owns the two-pass local-video flow while reusing the existing runtime
components:

1. Open the authorized local source in `CALIBRATING` state.
2. Run the frozen detector and ByteTrack without opening a business counting
   session or emitting operational crossing events.
3. Feed bounded observations to the engine and produce a result.
4. If status is not `READY`, return `AUTOCALIBRATION INCONCLUSIVE` and do not
   silently start a count.
5. Freeze the `CountingGeometryConfiguration`.
6. Reset detector temporal state, tracker, crossing, counter, preview count,
   and calibration state.
7. Restart the source from frame zero and run the existing crossing/counter
   path with the frozen line.
8. Return bounded runtime and consistency evidence.

The existing active-session replay guard remains authoritative. Calibration is
not a hidden replay of an active session.

### CLI integration

Add a subcommand following existing parser conventions:

```text
python -m hogflow autonomous-demo --video <authorized-local-video>
```

The command must require the existing frozen model arguments or a documented
demo profile that resolves to the exact frozen V2 artifact/configuration. It
must print sanitized IDs/metrics and never print private absolute paths.

The existing `run` command remains unchanged unless a minimal, tested alias is
needed. No second application entry point is created.

## Calibration algorithm

### Track eligibility

Reject tracks that are too short, have normalized displacement below the
minimum, show excessive path-to-displacement jitter, have insufficient
detection continuity, or only touch an image edge without corridor evidence.
Eligibility is deterministic and reported as aggregate counts.

### Dominant direction and purity

Normalize eligible displacement vectors and compute a robust mean direction
after rejecting vectors with weak magnitude and opposite outliers. Alignment is
the dot product with the dominant vector. Report median, p10/p90, positive
alignment ratio, and reverse ratio as `direction_purity`, never accuracy.

If eligible vectors are insufficient or their resultant direction is weak, the
result is `INCONCLUSIVE` and no line is selected.

### Corridor and lines

Project trajectory centers into along-flow and cross-flow coordinates. Use the
10th/90th percentiles with bounded margins, clamped away from image edges.
Generate eight line positions at 35–70% of robust travel. Each line is a finite
normalized segment spanning only the estimated cross-flow corridor. The line
normal is the dominant flow direction, so the line is perpendicular to motion.

Reject degenerate, edge-adjacent, out-of-corridor, low-evidence, or
pre/post-unsafe candidates.

### Candidate metrics and score

For each candidate, evaluate the existing crossing geometry over the same
trajectory observations in analysis-only mode. No operational counter is
updated. Record:

- eligible tracks expected to traverse the candidate;
- unique forward crossings and reverse crossings;
- multiple-crossing and oscillation ratios;
- pre/post continuity;
- lost-near-line and fragmentation indicators;
- corridor coverage and edge penalty;
- neighbor-line counts at the declared offsets.

The normalized autonomous consistency score is explicitly:

```text
score = 0.25 * direction_alignment
      + 0.20 * unique_forward_ratio
      + 0.20 * pre_post_continuity
      + 0.15 * neighbor_line_agreement
      + 0.10 * corridor_coverage
      + 0.10 * detector_perturbation_agreement
      - 0.10 * reverse_ratio
      - 0.10 * multiple_crossing_ratio
      - 0.10 * lost_near_line_ratio
      - 0.05 * edge_penalty
```

The score is clipped to `[0, 1]`, ties are broken by higher minimum neighbor
agreement, then higher continuity, then candidate ID. It is called an
`AUTONOMOUS CONSISTENCY SCORE`, never accuracy.

Confidence thresholds are fixed in code and documented: `HIGH` requires at
least 8 eligible tracks, direction purity ≥ 0.80, neighbor agreement ≥ 0.80,
pre/post continuity ≥ 0.75, and score ≥ 0.75; `MEDIUM` requires at least 5
tracks, purity ≥ 0.65, neighbor agreement ≥ 0.60, continuity ≥ 0.55, and score
≥ 0.55; `LOW` requires enough evidence to count but misses one or more medium
thresholds; otherwise `INCONCLUSIVE`.

### Consistency variants

The primary official count uses confidence `0.25` and the selected line. The
engine additionally runs only the declared diagnostics: line offsets -4/-2/+2/+4
percent and detector confidence 0.20/0.30. It reports min, max, median, primary,
spread, and relative spread where defined. These variants do not alter the
official configuration.

## Video selection policy

The autonomous demo identity is `autonomous_demo_video_1`, distinct from
formal `demo_video_c`. Selection excludes A, B, and the three historical
videos, sorts the remaining candidate basenames by SHA-256 of the sanitized
basename, and chooses the first readable candidate with meaningful pig
detections and enough eligible trajectories. Candidate choice is based on
suitability, never on the best count or consistency result. Committed reports
contain only sanitized candidate IDs and reasons.

## HMI and operator states

The existing dark industrial HMI remains unchanged except for minimal status
text if the current presenter supports it without a redesign:

```text
CALIBRATING
AUTO CALIBRATION READY / LOW CALIBRATION CONFIDENCE
LIVE COUNT
```

The selected line can use the existing cyan information treatment; warnings use
amber. `INCONCLUSIVE` blocks automatic counting unless an explicit future
operator override is implemented. No green accuracy badge is introduced.

## Failure and safety behavior

- No eligible trajectories or bidirectional flow: return `INCONCLUSIVE`.
- Unsafe/unstable candidate family: return `INCONCLUSIVE`; do not guess a line.
- Any calibration exception: leave no active count and return a bounded failure.
- Any count-pass replay while a session is active: existing guard blocks it.
- Camera motion after calibration is reported as `CALIBRATION MAY BE STALE`; the
  line is never shifted during an active count.
- Calibration data is bounded and contains no frames or private paths.

## Testing strategy

Write synthetic tests before production code for direction, diagonal flow,
bidirectional inconclusive results, corridor bounds, perpendicular candidates,
edge rejection, crossing uniqueness, pre/post continuity, reverse/lost-near-line
penalties, neighbor stability, score determinism, confidence tiers, config
fingerprints, two-pass reset isolation, replay safety, deterministic candidate
selection, and architecture boundaries. Real videos/models remain local and are
never required by CI.

## Evidence and documentation

Create `docs/phase_10/phase_10_3c_a_autonomous_demo.md` with A/B autonomous
results, the selected autonomous demo ID, primary/variant counts, runtime,
HMI state, limitations, and the exact statement:

> **AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED**

The formal 10.3C document and its human-evidence blockers must remain intact.
The final autonomous verdict may be `AUTONOMOUS DEMO READY`, `AUTONOMOUS DEMO
READY — LOW CONSISTENCY`, `AUTOCALIBRATION INCONCLUSIVE`, or `AUTONOMOUS DEMO
BLOCKED BY TECHNICAL FAILURE`; it may never be `ACCURATE`, `CERTIFIED`, or
`PRODUCTION READY`.
