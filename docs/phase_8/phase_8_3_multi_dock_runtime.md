# Phase 8.3 — Multi-Dock Runtime Coordination

## Status

IMPLEMENTED as synchronous, in-memory application infrastructure.

This phase does not prove concurrent camera operation, pig-count accuracy, or
production readiness.

## Objective and scope

Phase 8.3 composes the existing Phase 8.1 aggregate and one Phase 8.2
`UnloadingSessionCountingService` per occupied dock:

```text
MultiDockRuntimeCoordinator
├── Dock 1 → TruckOperation + service + owned counter
├── Dock 2 → TruckOperation + service + owned counter
├── Dock 3 → TruckOperation + service + owned counter
└── Dock 4 → TruckOperation + service + owned counter
```

The coordinator routes commands and immutable Phase 7 results to an explicit
`DockId`. It does not count crossing events, modify tracker identities, or
duplicate aggregate rules.

Phase 8.3 adds no UI, persistence, database, API, networking, camera
acquisition, scheduling, background work, threading, or async execution.

## Dependency direction

The implementation remains in `hogflow.sessions`, the application boundary
introduced by Phase 8.2:

```text
sessions runtime coordinator
        ↓
Phase 8.2 session counting service
        ↓
Phase 8.1 immutable domain + Phase 7 public counting contract
```

`hogflow.domain` and `hogflow.counting` do not import the coordinator or
`hogflow.sessions`. The coordinator imports no OpenCV, Supervision, detector,
tracker implementation, pipeline, storage, network, camera, or UI package.

## Public API

`MultiDockRuntimeCoordinator` exposes explicit synchronous commands:

- `register_operation(dock_id, operation, source_id=...)`
- `start_operation(dock_id, started_at)`
- `start_session(dock_id, session_id, crossing_lifecycle_id, started_at)`
- `process_counting_result(dock_id, crossing_result)`
- `complete_session(dock_id, completed_at)`
- `cancel_session(dock_id, cancelled_at)`
- `complete_operation(dock_id, completed_at)`
- `cancel_operation(dock_id, cancelled_at)`
- `runtime_for(dock_id)`
- `snapshot()`
- `close()`

Callers never receive the mutable counter, service, registry, or private dock
dictionary.

## Counter ownership

Registration uses an injected `CounterFactory`:

```text
counter_factory(dock_id, source_id) → LiveDirectionalCounter
```

The factory must return one enabled, inactive counter for that dock. A counter
is never shared between runtimes and is not started when a truck is merely
registered or its operation starts. Phase 8.2 starts it only when one unloading
session starts.

Phase 7's default lifecycle generator is local to one counter instance.
Therefore, a factory used for simultaneous docks must provide counters whose
reported `counting_lifecycle_id` values are globally distinguishable. The
coordinator validates this requirement and rejects collisions; it does not
silently rewrite Phase 7 provenance.

## Source and lifecycle isolation

Each non-terminal dock runtime reserves one validated source ID. The same
active source cannot be registered at another dock.

The caller always supplies the target `DockId` when routing a
`LiveCrossingResult`. The coordinator checks the active source, crossing
lifecycle, and frame ordering before delegating. Phase 8.2 and Phase 7 retain
their deeper provenance and event validation.

Active and finalized crossing/counting lifecycle IDs are checked across all
current dock records. A new optional lifecycle validator in Phase 8.2 executes
after a counter starts but before the service commits its session. If global
validation fails, Phase 8.2 closes the prospective counter and leaves the
operation/session unchanged.

The same numeric tracker ID may count independently at two docks because Phase
7 identity scope includes source and lifecycle. Repeated positive events
inside one dock/session remain Phase 7 duplicates.

## Atomicity and failure isolation

The coordinator computes prospective immutable domain/registry state before a
mutable service transition. State is installed only after the required
counter/service operation succeeds.

- registration validates occupancy, operation, source, and factory output
  before installing a runtime;
- session startup uses the pre-commit Phase 8.2 lifecycle validator;
- completion and cancellation preserve Phase 8.2 close-before-commit;
- active-truck cancellation prospectively validates both session and operation
  cancellation before closing the counter;
- a dock-local exception does not mutate another dock;
- no global failed state is created for an ordinary dock-local error.

An external counter may fail after changing its own internal state. HogFlow
cannot generally roll back arbitrary collaborator internals. The coordinator
therefore commits no domain change and reports a sanitized error; recovery of
that collaborator remains explicit.

## Operation terminal records

Completing or cancelling a truck makes its dock available while retaining its
immutable terminal current record for diagnostics. Registering the next
planned truck replaces that current terminal record and creates a new counter.
The mutable Phase 8.2 service is released at the terminal truck transition;
only its immutable finalized lifecycle provenance remains in the dock runtime.

There is no in-memory history beyond one current record per dock. Persistence
and historical audit remain Phase 10 responsibilities. Aggregate snapshots can
therefore decrease when a terminal record is deliberately replaced.

## Snapshots and totals

`DockRuntimeSnapshot` exposes only immutable values:

- availability and derived runtime status;
- operation and active-session identity/status;
- active pig type;
- current live session count;
- completed-session truck and pig-type totals;
- source and active lifecycle provenance;
- latest processed frame;
- number of finalized session lifecycles.

`MultiDockRuntimeSnapshot` always orders Dock 1 through Dock 4 and derives:

- occupied and available docks;
- active operations and sessions;
- combined completed-session total;
- combined completed totals for all four pig types;
- coordinator shutdown state.

The current live count is never included in finalized truck or combined totals
until Phase 8.2 completes and transfers that session.

## Shutdown policy

`close()` attempts every current dock even after a local close failure.

- planned or active operations without a session have their inactive counter
  closed;
- active sessions are cancelled through Phase 8.2;
- unfinished live counts are discarded;
- no session or truck is marked completed;
- truck operations are not automatically cancelled;
- successful dock closures remain committed even if another dock fails;
- failures are aggregated in `MultiDockShutdownError`;
- the coordinator rejects all later commands;
- repeated `close()` calls return the same success or repeat the same
  aggregated failure without retrying business transitions.

An active truck whose session was cancelled remains an in-memory active
operation in the terminal diagnostic snapshot. Recovery requires creating a
new coordinator from an authoritative future persistence boundary.

## Concurrency boundary

The synchronous coordinator can maintain four logically active and isolated
dock runtimes. Commands are expected to be serialized by the caller.

It is not thread-safe and does not run four camera streams concurrently.
Actual concurrent ingestion requires a later explicitly authorized runtime
boundary.

## Limitations

- all evidence is synthetic and in-memory;
- no validated pig detector or representative pig tracking was used;
- tracker ID switches, fragmentation, occlusion, and reconnect ambiguity remain;
- lifecycle ID uniqueness depends on the injected counter implementation and
  is enforced, not generated, by the coordinator;
- terminal history is replaced rather than persisted;
- shutdown cancels active sessions and requires external recovery if work is to
  resume;
- no type checker is configured in the repository;
- no UI, API, storage, networking, camera orchestration, or concurrency exists.
