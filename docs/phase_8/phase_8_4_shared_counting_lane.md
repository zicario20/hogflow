# Phase 8.4 — Shared Counting Lane Alignment

## Status

IMPLEMENTED as synchronous, in-memory application infrastructure.

This phase corrects the counting-location assumption used by the initial
Phase 8.3 runtime. It does not validate a physical camera, real pig counting,
operational throughput, or production readiness.

## Operational model

The four docks are operational origins. They identify the truck operation,
ordered unloading session, and pig type whose animals will next traverse the
counting corridor. They are not counting locations.

```text
Dock 1 ─┐
Dock 2 ─┼─→ one shared corridor → one shared source → one Phase 7 counter
Dock 3 ─┤                                      ↓
Dock 4 ─┘                          one active unloading session
```

The authorized physical reference is one corridor approximately 1.5 metres
wide and 20 metres long, with one camera near the scale entrance. These
dimensions are context, not geometry or validation rules in the software.

## Architecture

`SharedCountingLane` owns:

- one opaque source ID;
- one injected public `LiveDirectionalCounter`;
- at most one active crossing/counting lifecycle;
- at most one active binding to dock, operation, and session;
- the current live lifecycle total and last processed frame through Phase 8.2.

`MultiDockRuntimeCoordinator` continues to own exactly four current operational
dock records and the immutable `DockOperationRegistry`. A dock record keeps its
`TruckOperation` and finalized lifecycle provenance only. It never keeps a
counter, camera source, or active Phase 8.2 service.

While the lane is bound, it constructs one short-lived
`UnloadingSessionCountingService` around the shared counter. Completion or
cancellation returns immutable operation/finalization values and removes that
service reference. A later session reconstructs the service with verified
prior terminal provenance and the same shared counter.

Dependency direction remains:

```text
sessions coordinator / shared lane
        ↓
Phase 8.2 service
        ↓
Phase 8.1 domain + Phase 7 public interfaces
```

Neither `hogflow.domain` nor `hogflow.counting` imports `hogflow.sessions`.

## Binding and routing rules

- A truck operation may be planned or active at each of the four docks.
- Starting a truck does not start or reserve the counter.
- Starting a session requires the lane to be idle and the truck active.
- Exactly one dock/session may own the lane.
- A caller must name the target `DockId`; the coordinator never guesses by
  scanning source strings.
- The result source must equal the one shared source.
- The crossing lifecycle and frame ordering must match the active binding.
- A different dock cannot submit results, complete, cancel, or take ownership.
- The lane never switches ownership in place.
- The shared counter remains the sole owner of duplicate suppression, reverse
  handling, counted identities, lifecycle total, and telemetry.

The optional `source_id` accepted by `register_operation` is retained only as a
compatibility check for Phase 8.3 callers. If supplied, it must equal the shared
lane source; it is not stored as dock ownership.

## Completion, cancellation, and identity reset

Session completion uses Phase 8.2 close-before-commit:

1. validate the prospective immutable completed session and count;
2. close the Phase 7 lifecycle;
3. transfer the final positive-direction total exactly once;
4. install immutable operation and finalization provenance;
5. release the lane.

Cancellation follows the same ordering but discards the unfinished live total.
Completed totals from earlier sessions remain in the truck aggregate.

The Phase 7 counter starts a new counting lifecycle for every new binding.
Its counted temporary identities and current total are empty. Therefore, the
same numeric tracker ID may contribute in a later session without leaking the
prior session's duplicate state. This is lifecycle isolation, not biological
re-identification.

## Snapshots and shutdown

`SharedCountingLaneSnapshot` exposes bounded immutable ownership and live
state. `MultiDockRuntimeSnapshot` contains one lane snapshot plus Dock 1–4 in
deterministic order. Its invariant permits zero or one active session globally.
Only the dock that owns the lane exposes current source/lifecycle/count state.
Finalized truck totals remain separate from the current live count.

`close()` is synchronous and idempotent after success:

- idle lane: close the sole counter;
- occupied lane: cancel the active session, discard unfinished count, release
  the binding, then close the counter;
- never complete a session or truck automatically;
- counter close failure leaves the coordinator open and the binding available
  for explicit recovery;
- later runtime commands are rejected after successful close.

Calls must be serialized by the caller. No thread-safety claim is made.

## Migration from the original Phase 8.3 assumption

The former `CounterFactory(dock_id, source_id)` constructor boundary has been
removed from the coordinator. Construction now requires one explicit
`SharedCountingLane`, which itself receives the one shared counter and source.

Phase 8.1 aggregate types, `DockOperationRegistry`, Phase 7 contracts, and the
Phase 8.2 public service remain in place. Phase 8.2 gained only an optional,
strictly validated terminal-provenance adoption input so the lane can release
its service after each session without losing earlier session evidence.

ADR-053 remains historical evidence of the original Phase 8.3 assumption.
ADR-054 supersedes its counter/source ownership decision for the current plant
model.

## Exclusions and limitations

Not implemented:

- camera capture, OpenCV, RTSP, or hardware validation;
- multiple physical counting lanes or cameras;
- concurrent ingestion, threads, async tasks, workers, or scheduling;
- UI, API, networking, persistence, SQLite, or operational history;
- automatic dock/session selection or lane switching;
- pig-specific detector/tracker validation or count accuracy;
- Phase 9.

Future facilities may require multiple physical lanes. That would require a
separate approved resource model; this phase intentionally defines exactly one.
