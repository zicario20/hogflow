# Phase 10.1 — Production Runtime Foundation

## Status

IMPLEMENTED as a synthetic, deterministic runtime foundation. This phase does
not establish production readiness or representative pig-counting validity.

## Objective and scope

Phase 10.1 adds long-running supervision around the existing Phase 9.4 shared
runtime without changing detection, tracking, crossing, counting, sessions, or
presentation behavior.

```text
caller cadence
    → ProductionRuntimeSupervisor
        → RuntimeHealthManager
            → immutable camera/pipeline snapshot
            → immutable shared-lane/four-dock snapshot
            → process-memory sample
        → immutable RuntimeHeartbeat
```

There is still exactly one source, one processing worker, one detector/tracker/
crossing chain, one preview slot, one shared lane, and one Phase 7 counter.

## Public runtime contracts

- `ProductionRuntimeConfiguration`: frozen/slotted thresholds and bounded
  capacities with deterministic SHA-256 fingerprint.
- `RuntimeHeartbeat`: uptime, exact last processed frame, latest observed
  successful lifecycle/finalized count, FPS, memory, queue/slot capacities,
  worker state, component health, current issues, and aggregate diagnostics.
- `RuntimeDiagnosticsSnapshot`: lifetime scalar aggregates plus a bounded tuple
  copied from the fixed-capacity warning deque.
- `RuntimeHealthManager`: synchronous snapshot observer; it creates no thread.
- `ProductionRuntimeSupervisor`: explicit heartbeat and restart boundary.
- `SupervisedCountingPipeline`, `SupervisedRuntimeAccess`, and
  `ProcessMemoryProbe`: small injectable ports used by the supervisor.

## Health and failure policy

The manager distinguishes recoverable and fatal issues:

| Observation | Initial disposition |
| --- | --- |
| Pipeline stall or stale frame | Recoverable |
| Single source/detector failure | Recoverable |
| Repeated source/detector failures at configured threshold | Fatal |
| Dead active worker | Fatal |
| Tracker or crossing state failure | Fatal |
| Preview failure | Recoverable; counting remains independent |
| Closed lane with an active worker | Fatal |

The categories are sanitized and contain no frame data, paths, credentials, or
third-party exception objects. Threshold defaults are engineering defaults and
must be tuned per deployment.

## Heartbeat cadence and threading

`heartbeat_interval_seconds` documents the intended external cadence; Phase
10.1 does not schedule it. The executable may request a heartbeat manually or
a later authorized composition may schedule it on an existing control cadence.
No monitor thread, async task, worker pool, or polling loop was added.

The camera worker remains the only background worker. Snapshot reads and lane
state remain behind the existing serialized application boundary.

## Restart policy

- Camera restart and pipeline restart both stop, recreate, and start the same
  existing source/processor/worker composition.
- The two commands have separate telemetry but intentionally share the low-level
  operation because those resources have one lifecycle in Phase 9.4.
- By default they are rejected while the shared lane is occupied. Resetting
  tracker/crossing state during an active count could corrupt temporary-ID
  continuity.
- Preview restart only resets the one-slot visual channel and is allowed during
  counting.
- Manual restarts have a configurable per-supervisor bound.
- A failed restart is surfaced and is not recorded as successful.

This phase does not implement transparent active-session failover. An operator
must first resolve/cancel the active workflow through existing rules.

## Long-running diagnostics

Diagnostics include heartbeat count; current/average/minimum/maximum FPS;
processing sample count and average/maximum latency; source reconnects;
camera, pipeline, worker, and preview restarts; source, detector, tracker,
crossing, and preview failures; dropped frames; stale evidence; and warning
totals.

No complete history is stored. Pipeline processing has no queue, so its size
and capacity are both zero. Preview capacity remains exactly one frame.

## Memory safety

- no heartbeat history;
- no frame/image history;
- no new queue;
- no image copies in runtime snapshots;
- one previous pipeline/preview observation;
- one fixed-capacity warning `deque`;
- scalar running aggregates only;
- standard-library resident-memory sampling without `tracemalloc` history.

On unsupported platforms or probe failure, memory is explicitly unavailable;
runtime counting continues.

## Explicit exclusions

No detector, model, training, dataset, pig recognition, database, persistence,
network, API, authentication, report, UI redesign, additional worker, async
execution, Phase 10.2, or Phase 11 was implemented.

No `ui-ux-pro-max` design step was needed because no visual component or
operator interaction changed.
