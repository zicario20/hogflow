# Phase 5.4 — Summary

## Status

Phase 5.4 tooling implements live virtual-line crossing events. The phase ends
at immutable directional geometric events and does not implement an
accumulated pig count.

## Delivered

- normalized immutable point and finite-line models;
- explicit `NEGATIVE`, `ON_LINE`, and `POSITIVE` sides;
- neutral `NEGATIVE_TO_POSITIVE` and `POSITIVE_TO_NEGATIVE` events;
- bottom-center and center representative-point policies;
- explicit normalized epsilon;
- finite-segment validation using two real stable observations;
- lifecycle-qualified temporary IDs;
- deterministic absence cleanup;
- stale sequence and cross-stream rejection;
- reset/reconnect state clearing;
- bounded crossing telemetry;
- optional serial `LiveCrossingPipeline`;
- optional local OpenCV diagnostic preview;
- explicit CLI activation and normalized configuration;
- synthetic unit, pipeline, preview, CLI, architecture, and regression tests;
- ADR-039 through ADR-041 and dependency/governance updates.

## Preserved behavior

When crossing is not explicitly enabled, the CLI and runtime retain the Phase
5.3 live tracking path. The Phase 1 finite counter, positive-direction
deduplication, JSONL format, and generic finite-video CLI are unchanged.

The live implementation adds no queue, no frame history, no automatic media
output, and no framework object to its public models.

## Validation evidence

- baseline: 465 tests passed;
- focused Phase 5.4/regression suite: 86 passed;
- full suite: 524 passed with the one known Supervision ByteTrack deprecation
  warning;
- Ruff check and format check passed;
- `compileall`, `pip check`, `git diff --check`, import smoke, synthetic CLI
  smoke, and tracked-artifact audit passed;
- remote CI is reported only after the Phase 5.4 commit is pushed.

## Evidence not produced

- no pig-specific model was executed;
- no real pig tracking validation was performed;
- no line position was evaluated;
- no ground-truth crossing labels exist;
- no event accuracy or count accuracy was measured;
- no RTSP production certification was performed.

## Scope confirmation

Phase 5.4 does not implement accumulated counting, one-ID-one-count
deduplication, operational direction, sessions, storage, dashboard, line
optimization, Phase 6, Phase 7, or a later roadmap phase.

## Remaining risks

ID switches, track fragmentation, occlusions, dense groups, missed tracks,
large frame gaps, detector jitter, uncalibrated line placement, reconnect ID
reuse, and the deprecated Supervision ByteTrack API remain observable risks.
A crossing event is a geometric observation, not evidence of a unique animal.
