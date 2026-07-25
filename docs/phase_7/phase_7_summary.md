# Phase 7 - Summary

## Status

Phase 7 lifecycle-aware directional counting infrastructure implemented;
representative pig duplicate-counting and reverse-movement validation remains
pending.

## Delivered

- explicit positive geometric direction;
- immutable `LiveCountingConfiguration`;
- lifecycle-qualified `TemporaryTrackIdentity`;
- immutable auditable decisions, frame results, snapshots, telemetry, and run
  summaries;
- `LiveDirectionalCounter` protocol;
- atomic `LifecycleDirectionalCounter`;
- first-positive increment and duplicate-positive suppression;
- reverse classification without decrement;
- bounded counted-identity capacity without silent eviction;
- stale, source, lifecycle, and crossing-provenance validation;
- independent crossing and counting lifecycle identities;
- coordinated reconnect reset;
- serial `LiveCountingPipeline` with no additional queue;
- optional local OpenCV lifecycle-count preview;
- technical CLI preflight, decisions, and structured summary;
- synthetic policy, atomicity, reconnect, architecture, privacy, and regression
  tests.

## Preserved boundaries

Phase 5.4 continues to emit neutral geometric events and maintains no count.
Phase 6 still evaluates those event streams without Phase 7 deduplication.
Phase 7 owns only the lifecycle-scoped directional policy.

No sessions, sections, loads, persistence, SQLite, operator UI, net count,
decrement-on-reverse, re-identification, cross-lifecycle aggregation, or Phase
8 implementation was added.

## Evidence

All Phase 7 evidence is synthetic. The fixtures verify policy and lifecycle
mechanics, not real pig identity, tracking quality, or count accuracy.

No pig-specific detector checkpoint, representative pig tracking, human
ground truth, reverse-movement study, duplicate-counting accuracy result, or
session evaluation was produced.

## Remaining risks

- an ID switch or fragmented track can count one animal more than once;
- ID reuse inside one lifecycle can suppress a valid new animal;
- reconnect reset can permit the same physical animal to increment again;
- no biological re-identification exists;
- reverse movement does not prove final physical departure;
- reverses do not decrement and no net count exists;
- jitter and gaps can affect crossing events upstream;
- positive direction or line endpoint order can be misconfigured;
- line placement remains uncalibrated;
- pig-specific detection and representative ground truth are absent;
- the Supervision ByteTrack API is deprecated;
- no session boundary exists until Phase 8.

## Next boundary

Audit Phase 7 and its CI before considering Phase 8. Do not treat the
lifecycle total as a session result.
