# Phase 8.1 - Multi-Dock Unloading Domain Model and Rules

## Status

Phase 8.1 pure unloading-domain infrastructure is implemented. Integration
with the Phase 7 counting lifecycle remains explicitly deferred to Phase 8.2.

This is deterministic domain infrastructure backed by synthetic tests. It is
not an operational plant deployment and does not validate pig-count accuracy.

## Objective

Phase 8.1 models truck unloading operations independently across four physical
docks:

- `DOCK_1`
- `DOCK_2`
- `DOCK_3`
- `DOCK_4`

One reusable aggregate is parameterized by `dock_id`; there are no duplicated
dock-specific classes.

```text
DockOperationRegistry
  -> TruckOperation
      -> ordered UnloadingSession values
          -> one explicit PigType
```

The package is pure Python under `hogflow.domain`. It does not import camera,
detection, tracking, counting, pipeline, UI, persistence, networking, or CV
framework modules.

## Supported pig types

The stable internal values are:

| Enum | Internal value |
| --- | --- |
| `PigType.REGULAR` | `regular` |
| `PigType.OPG` | `opg` |
| `PigType.P12` | `p12` |
| `PigType.NAE` | `nae` |

The eventual display label `P-12` does not change the internal `p12` value.
Each session has exactly one pig type. Different sessions in one truck may use
different pig types.

## Operational reference versus rule

The current physical process commonly uses three gate sections and roughly 60
pigs per section. Neither value is a domain invariant:

- an operation may have one, two, three, four, or more sessions;
- sessions are never created automatically;
- sequence numbers need not be contiguous, but must be positive and unique;
- `expected_count` is optional and never controls completion;
- zero and counts above or below 60 are valid finalized counts.

A session containing multiple pig types remains outside Phase 8.1.

## Immutable domain objects

All public domain records are frozen and slotted dataclasses. Aggregate
transitions use copy-on-write: a successful method returns a new value and the
previous value remains unchanged.

### `UnloadingSession`

Fields:

- `session_id`
- `sequence_number`
- `pig_type`
- `status`
- optional `expected_count`
- `actual_count`
- `started_at`
- `ended_at`

`actual_count` is finalized only by completing an active session. It defaults
to zero before completion. This explicit Phase 8.1 policy avoids partially
assigned counts: active, planned, and cancelled sessions cannot carry a
non-zero actual count.

### `TruckOperation`

The aggregate root contains:

- `operation_id`
- `dock_id`
- `status`
- an immutable, canonically sorted session tuple
- `started_at`
- `ended_at`

The aggregate validates unique session IDs, unique sequence numbers, at most
one active session, timestamps, lifecycle consistency, and terminal-state
protection.

### Read models

- `UnloadingSessionSummary` is an immutable session projection.
- `PigTypeTotal` provides one immutable total entry.
- `truck_total` sums completed sessions only.
- `totals_by_pig_type` always returns all four pig types in enum order,
  including zero totals.

Completed sessions continue contributing if the containing truck operation is
later cancelled. Planned, active, and cancelled sessions do not contribute.

## Transition policy

### Adding sessions

Sessions may be added only while the operation is `PLANNED`, and the added
session must itself be `PLANNED`. Additions after activation are rejected.
There is no hardcoded maximum session count.

### Starting an operation

`PLANNED -> ACTIVE` requires at least one planned session and one aware start
timestamp. Repeated start is rejected rather than treated as idempotent.

### Starting sessions

- the operation must be active;
- no other session may be active;
- every lower-sequence session must be `COMPLETED` or `CANCELLED`;
- no unfinished earlier session is skipped.

### Completing sessions

Only an active session can complete. Completion atomically records a
non-negative final `actual_count` and aware end timestamp. A completed session
cannot complete again or have its count changed.

### Completing an operation

Only an active operation can complete. It requires:

- no active session;
- no planned session;
- every non-cancelled session completed;
- at least one successfully completed session.

### Cancellation

A planned or active operation may be cancelled. The transition:

- preserves every already completed session and count;
- converts each unfinished session to `CANCELLED`;
- assigns one consistent aware cancellation timestamp;
- makes the operation terminal and its dock available.

No completed or cancelled operation may be mutated.

## Dock occupancy

`DockOperationRegistry` is an immutable pure-domain registry with at most one
current record per supported dock.

- one non-terminal operation occupies one dock;
- another planned or active operation at that dock is rejected;
- other docks remain independent;
- completion or cancellation makes a dock available;
- a new operation replaces the prior terminal current record at that dock.

The registry is not history or persistence. Replacing a terminal current record
does not preserve an audit log; persistence belongs to Phase 10.

The registry delegates aggregate transitions so a caller receives a new
registry only after the complete operation succeeds. No thread synchronization
or multi-process coordination is provided.

## Atomicity

Because the session, operation, and registry are immutable:

- duplicate IDs or sequences cannot partially insert a session;
- a failed second-session activation changes nothing;
- invalid order or counts preserve prior state;
- premature completion preserves status and totals;
- occupancy conflicts preserve every dock record;
- cancellation builds all replacement sessions before returning a new
  aggregate.

## Real-world examples

### Regular truck

```text
Dock 1
Session 1 -> REGULAR -> 55
Session 2 -> REGULAR -> 61
Session 3 -> REGULAR -> 49
Truck total = 165
```

### Mixed truck

```text
Dock 2
Session 1 -> OPG -> 58
Session 2 -> OPG -> 52
Session 3 -> REGULAR -> 50
Truck total = 160
OPG total = 110
REGULAR total = 50
```

### Small P12 group

```text
Dock 3
Session 1 -> P12 -> 10
Truck total = 10
```

No empty sessions are created for the small group.

## Explicit exclusions

Phase 8.1 does not implement:

- Phase 7 lifecycle integration or automatic count transfer;
- live camera, detection, tracking, crossing, or counting orchestration;
- UI, API, networking, concurrency, persistence, SQLite, or event streaming;
- sessions spanning multiple pig types;
- gate, hardware, ERP, scheduling, authentication, or pig-type recognition;
- automatic three-session creation or 60-pig splitting.

Phase 8.2 is responsible for defining the explicit adapter/application boundary
between one unloading session and one Phase 7 counting lifecycle.
