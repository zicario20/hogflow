# Phase 8.2 - Unloading Session and Phase 7 Counting Lifecycle Integration

## Status and evidence

Phase 8.2 application integration is implemented and validated with synthetic
crossing events. It connects one active Phase 8.1 unloading session to one
isolated Phase 7 counting lifecycle.

This does not validate pig detection, tracking identity, line placement,
duplicate-count accuracy, or plant operation. It adds no camera orchestration,
concurrency, persistence, network, API, or UI capability.

## Boundary

```text
TruckOperation (immutable Phase 8.1 domain)
  -> UnloadingSessionCountingService (Phase 8.2 application coordination)
      -> LiveDirectionalCounter (public Phase 7 protocol)
```

Dependency direction is one-way:

- `hogflow.sessions` may consume `hogflow.domain` and public
  `hogflow.counting` contracts;
- `hogflow.domain` does not import sessions or counting;
- `hogflow.counting` does not import sessions or domain;
- the service imports no detector, tracker implementation, pipeline, adapter,
  camera, storage, network, or UI package.

`UnloadingSessionCountingService` coordinates one `TruckOperation`. Broader
simultaneous multi-dock orchestration is intentionally outside Phase 8.2.

## One session, one lifecycle

The service requires an already active `TruckOperation` with no adopted active
or previously completed session. This ensures the service owns every completed
session count it produces rather than reconstructing undocumented provenance.

Starting a session:

1. validates the prospective immutable domain transition;
2. rejects a crossing lifecycle used by a finalized session;
3. starts the owned `LiveDirectionalCounter`;
4. records source, operation, dock, session, crossing lifecycle, counting
   lifecycle, configuration fingerprint, and aware start time;
5. resets the application-visible current count to zero;
6. commits the new immutable `TruckOperation` only after lifecycle startup
   succeeds.

The same counter object may serve sequential sessions, but Phase 7 creates a
new `counting_lifecycle_id` on every fresh start. `close()` clears counted
identities and frame-order state. Phase 7 telemetry also resets its
current-lifecycle gauges on fresh start while retaining bounded aggregate
diagnostics.

Both crossing and counting lifecycle IDs are checked against prior
finalizations. No two sessions coordinated by one service may reuse them.

## Processing

`update_counting()` accepts one immutable `LiveCrossingResult` and delegates
all positive, reverse, duplicate, capacity, stale-frame, and temporary
identity policy to Phase 7.

The service:

- checks source and crossing lifecycle ownership before invoking Phase 7;
- rejects observations timestamped before the unloading session;
- accepts only a `LiveCountingResult` tied to the exact source, crossing
  lifecycle, counting lifecycle, frame sequence, and timestamp;
- remembers only the latest validated lifecycle total and timestamp.

It does not inspect tracker state, counted IDs, reverse events, or decisions to
recalculate a total.

## Completion and exactly-once transfer

Completing the active session:

1. builds a prospective immutable `TruckOperation` completion using the latest
   validated Phase 7 `lifecycle_directional_count`;
2. validates that completion does not precede the latest counting result;
3. builds immutable terminal lifecycle provenance;
4. closes Phase 7;
5. commits the prospective operation and finalization only after close
   succeeds.

The completed session's `actual_count` is therefore transferred once. A
second completion has no active lifecycle and is rejected. Phase 8.1 also
continues rejecting changes to a completed session count.

If counter close fails, no session count or domain status is committed. The
error is fatal for that application service operation and requires explicit
recovery; success is never fabricated.

## Cancellation

Cancelling an active session follows the same prospective transition and
close-before-commit policy. Its in-progress count is discarded:

- the session becomes `CANCELLED`;
- `actual_count` remains zero;
- terminal provenance uses `finalized_count = None`;
- completed earlier sessions and their counts remain unchanged;
- no Phase 7 lifecycle remains active.

## Reconnect policy

Phase 7 remains the owner of reconnect and counting reset semantics. Phase 8.2
does not manipulate tracker identities or aggregate several Phase 7
lifecycles.

Because this phase requires exactly one crossing/counting lifecycle per active
unloading session, a result from a different crossing lifecycle is rejected.
It is not silently reset or merged. An operational policy for a reconnect that
interrupts one physical session requires a later explicit design; otherwise
combining totals could double-count one physical animal across tracker
lifecycles.

## Bounded state

The service retains:

- one immutable current operation;
- zero or one active lifecycle binding;
- one integer current count;
- one latest timestamp;
- one terminal provenance record per session coordinated by the service.

The terminal tuple is bounded by the operation's finite session definitions.
No frame, image, tracker history, decision history, or crossing history is
stored.

## Explicit exclusions

Phase 8.2 does not implement:

- simultaneous coordination across docks;
- camera, detector, tracker, crossing, or live-pipeline orchestration;
- storage, SQLite, networking, REST, event streaming, or UI;
- threading or asynchronous execution;
- automatic session creation or scheduling;
- cross-reconnect aggregation or biological re-identification;
- Phase 8.3 or any later roadmap capability.
