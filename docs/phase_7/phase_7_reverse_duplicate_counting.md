# Phase 7 - Reverse movement and duplicate counting

## Objective and status

Phase 7 adds lifecycle-aware directional counting after the neutral geometric
events emitted by Phase 5.4:

```text
TrackingResult
  -> LiveCrossingResult
  -> LifecycleDirectionalCounter
  -> LiveCountingResult
  -> lifecycle-only directional total
```

Phase 7 lifecycle-aware directional counting infrastructure is implemented;
representative pig duplicate-counting and reverse-movement validation remains
pending.

The total is not a session total, a biological identity count, or a validated
pig count. Phase 8 session management, Phase 10 storage, operator UI, and
empirical accuracy claims are outside this phase.

## Domain boundary

The framework-neutral Phase 7 implementation is under `hogflow.counting`:

- `live_counting_models.py`: immutable configuration, identity, decisions,
  results, snapshots, statistics, and run summaries;
- `live_counting_ports.py`: the small `LiveDirectionalCounter` protocol;
- `live_counting.py`: `LifecycleDirectionalCounter`;
- `live_counting_telemetry.py`: bounded aggregate diagnostics;
- `live_counting_errors.py`: sanitized expected failures.

These modules do not import OpenCV, NumPy, Supervision, Ultralytics, detector
implementations, storage, or UI code. `LiveCountingPipeline` is application
orchestration and composes the existing crossing pipeline without adding a
queue.

## Explicit positive direction

Phase 5.4 preserves neutral geometry:

- `NEGATIVE_TO_POSITIVE`
- `POSITIVE_TO_NEGATIVE`

`LiveCountingConfiguration.positive_direction` explicitly selects which
geometric direction is operationally positive. The opposite direction is
classified as reverse. The configuration records the exact Phase 5.4 crossing
configuration fingerprint.

Reversing the virtual-line endpoints reverses the geometric direction names.
It does not update the Phase 7 policy automatically. Operators must verify both
line endpoint order and the configured positive direction.

## Temporary identity

`TemporaryTrackIdentity` is:

```text
(source_id, crossing_lifecycle_id, tracker_id)
```

The historical Phase 5.4 field `tracker_lifecycle_id` is retained for public
compatibility, but its value identifies the crossing-detector lifecycle.
`LiveCrossingEvent.crossing_lifecycle_id` and
`LiveCrossingResult.crossing_lifecycle_id` provide clear read-only aliases.
Phase 7 gives its own state a separate `counting_lifecycle_id`.

This key is not a biological identity. It is not compared across reconnects or
lifecycles to infer whether observations represent the same physical animal.

## Counting policy

Within one active lifecycle:

1. The first positive event for a temporary identity emits
   `COUNTED_POSITIVE` and increments by one.
2. Another positive event for that identity emits
   `IGNORED_DUPLICATE_POSITIVE` and does not increment.
3. A reverse event emits `IGNORED_REVERSE` and does not increment.
4. A reverse never decrements the total and never removes a counted identity.
5. A positive after a reverse remains a duplicate when the identity was
   already counted.
6. Gaps are accepted when frame sequences remain strictly increasing. No
   trajectory, frame, or event is interpolated.
7. Stale or repeated crossing-result frames are rejected.

Counted identities remain until reset or close. Crossing's absent-track
cleanup does not remove them. This avoids a second increment after temporary
misses, but an incorrectly reused tracker ID within one lifecycle can cause an
undercount.

## Bounded state

`maximum_counted_identities` is a positive configured capacity. Counted
identities are never evicted within a lifecycle because eviction would permit
silent duplicate increments. If a frame would exceed capacity,
`CountingCapacityError` rejects the complete frame before state mutation.

No decision history, crossing history, frame, or image history is retained.
Telemetry stores only counters, gauges, bounded error categories, and latency
aggregates.

## Atomic frame updates

`LifecycleDirectionalCounter.update()`:

1. validates the complete `LiveCrossingResult`;
2. verifies source, crossing lifecycle, crossing fingerprint, line provenance,
   frame identity, timestamps, and event uniqueness;
3. sorts events deterministically by tracker ID;
4. calculates every decision against a prospective copy of state;
5. builds and validates the immutable `LiveCountingResult`;
6. commits the new identity set and frame sequence only after all prior steps
   succeed.

One invalid event prevents all increments in that frame. Valid duplicates and
reverses are decisions, not errors.

## Lifecycle, reset, and reconnect

`start(source_id, crossing_lifecycle_id)` binds one counter instance to one
source and crossing lifecycle. Calling start again with the same binding is
idempotent; a different binding is rejected.

`reset(new_crossing_lifecycle_id)`:

- requires a new crossing lifecycle ID;
- clears the lifecycle total and every counted identity;
- resets stale-sequence state;
- creates a new counting lifecycle ID.

`LiveCountingPipeline` observes the lifecycle on each successful
`LiveCrossingResult`. A tracker reconnect resets Phase 5.4 first; the changed
crossing lifecycle then resets Phase 7 before that result is counted. Totals
are never combined across reconnects.

`close()` clears active domain state and is idempotent. The terminal summary
retains bounded aggregate diagnostics and the final lifecycle total.

## Live integration and failure policy

`LiveCountingPipeline` composes:

```text
LiveTrackingPipeline
  -> LiveCrossingPipeline callback
  -> LifecycleDirectionalCounter
  -> optional result callback / local preview
```

The Phase 5.1 bounded source buffer remains the only queue. Counting is serial
after crossing, so decisions preserve the exact source frame. Counting is
disabled by default and Phase 5.1-6 behavior is unchanged unless explicitly
enabled.

Configuration, input, stale, lifecycle, provenance, capacity, and core output
failures are fatal for that run. The camera, detector, tracker, crossing
detector, counter, and preview still follow normal cleanup. A preview failure
is isolated, recorded, and disables preview while processing continues.

## Telemetry

Bounded diagnostics include:

- crossing results and events processed;
- positives accepted;
- duplicate positives;
- reverses before and after a positive decision;
- current lifecycle directional count;
- current and peak counted identities;
- empty-event frames;
- resets and closes;
- stale requests and lifecycle mismatches;
- failures and preview failures;
- total, average, and maximum counting latency;
- latest frame, error category, and health state.

`lifecycle_directional_count` is a temporary lifecycle total. It is not named
or interpreted as validated pigs, unique animals, or a session count.

## CLI and preview

The existing live CLI adds:

```text
--enable-counting
--positive-direction negative_to_positive|positive_to_negative
--maximum-counted-identities N
```

Counting requires an enabled tracker, complete crossing line, enabled crossing,
and explicit positive direction. Validation occurs before camera creation or
model construction. The structured output reports lifecycle count, reverses,
duplicates, health, closure, and sanitized per-event decisions. It creates no
session or stored result.

The optional OpenCV adapter displays `Lifecycle count`, the latest decision,
positive direction, and lifecycle ID. It does not contain business logic,
record frames, save screenshots, or claim verified pig counts.

## Relationship to earlier phases

- Phase 1 is a finite generic video counter and retains its original API.
- Phase 5.4 emits live neutral geometric crossing events only.
- Phase 6 compares line candidates using those unmodified geometric events.
- Phase 7 converts live events to lifecycle-scoped directional decisions.

Phase 6 schemas, fingerprints, matching, and ranking are unchanged.

## Explicit exclusions

Phase 7 does not implement sessions, sections, loads, SQLite, persistence,
operator UI, count correction, decrement-on-reverse, net count,
re-identification, cross-lifecycle aggregation, cross-camera aggregation, or
Phase 8.
