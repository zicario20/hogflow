# Phase 6 — Summary

## Status

Phase 6 evaluation infrastructure implemented; representative pig
line-position evaluation remains pending.

## Delivered

- immutable normalized line candidates and canonical plans;
- explicit synthetic, controlled, representative-without-ground-truth, and
  representative-with-ground-truth evidence levels;
- immutable path-free tracking replays;
- optional tracker-independent ground-truth crossing events;
- serial isolated replay through the Phase 5.4 crossing detector;
- descriptive event, track, gap, endpoint, lifecycle, density, and latency
  metrics;
- deterministic one-to-one greedy event matching;
- crossing-event precision, recall, F1, frame offsets, direction diagnostics,
  and event-count error;
- explicit ranking methods and stable tie-breaks;
- no automatic recommendation without ground truth;
- strict schema-versioned plan/replay JSON;
- deterministic sanitized report JSON and atomic writes;
- headless offline CLI;
- bounded evaluation telemetry;
- synthetic clean-pass, finite-extension, and jitter/gap fixtures;
- architecture, privacy, CLI, serialization, matching, ranking, and regression
  tests.

## Preserved boundaries

Phase 6 reuses `VirtualLineCrossingDetector` and `NormalizedLine`; it does not
copy Phase 5.4 side classification or finite-segment emission logic.

The live pipeline does not auto-select or change its line. Applying an
evaluated candidate requires an explicit human configuration action.

No accumulated count, one-ID-one-count rule, reverse correction, session,
storage, UI, camera, detector execution, or Phase 7 behavior was added.

## Evidence

The implementation is validated with synthetic `TrackingResult` fixtures only.
Synthetic ground truth demonstrates matching and ranking mechanics, not
real-world accuracy.

No representative pig replay, human crossing ground truth, calibrated line,
pig detector, real pig tracking, or count-accuracy result was produced.

## Remaining risks

- line choice remains uncalibrated;
- bottom-center versus center anchor bias;
- jitter and large gaps;
- short-segment endpoint sensitivity;
- ID switches, fragmentation, misses, and occlusion;
- greedy rather than globally optimal matching;
- no representative evidence;
- deprecated Supervision ByteTrack API.

## Next boundary

At the Phase 6 completion boundary, the recommendation was to audit Phase 6
and perform an explicitly authorized representative evaluation before Phase 7.
The later Phase 7 implementation does not change Phase 6 metrics or evidence.
