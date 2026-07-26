# Phase 9.2 — Operator Workflow Safety & Executable Composition

## Status and evidence

Phase 9.2 implements an executable, manual-refresh Operator MVP and prevents
invalid workflow actions through snapshot-derived control availability and
explicit destructive-action confirmations.

It remains a research-MVP desktop. It has no camera, automatic count input,
preview, persistence, network, authentication, background execution, or
production usability evidence.

## Executable composition

Run either:

```text
python -m hogflow
hogflow run
```

The uppermost `hogflow.bootstrap` module creates and wires:

```text
LifecycleDirectionalCounter
    ↓
SharedCountingLane
    ↓
MultiDockRuntimeCoordinator
    ↓
OperatorApplicationService
    ↓
OperatorPresenter
    ↓
TkOperatorView
```

No lower package imports bootstrap. `hogflow.__main__` only parses the bounded
`run` command and invokes that composition.

## No-camera runtime

Phase 9.2 is explicitly forbidden from opening a camera or executing crossing
inference. The executable therefore creates an enabled but idle counter with:

- source ID `shared_operator_lane`;
- a deterministic fingerprint explicitly named
  `NO_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT`;
- locally generated opaque crossing lifecycle IDs.

These values allow Phase 8 lifecycle transitions to execute without fabricating
frames or detections. They are not camera/crossing provenance and must not be
used to claim real counting. A future authorized camera composition must
replace the fingerprint and lifecycle factory with values from the real
crossing pipeline.

## Operator workflow

```text
Register Truck
→ Start Truck
→ Start Next Session
→ Shared Lane Occupied
→ Manual Snapshot Refresh
→ Complete Session
→ Shared Lane Released
→ Complete Truck
```

The dock panel displays the next planned session and pig type. Selecting a dock
requests a fresh snapshot; this is an explicit user interaction, not polling.

## Snapshot-only safety

Phase 8 remains authoritative. `DockRuntimeSnapshot` adds read-only projections
for:

- next planned session ID;
- next planned pig type;
- whether a session may start;
- whether the truck operation may complete.

The presenter combines those fields with selected-dock status and shared-lane
ownership. It never calls a private coordinator attribute and never replays a
domain transition to guess eligibility.

| Selected-dock state | Register | Start truck | Start session | Complete/cancel session | Complete truck | Cancel truck |
| --- | --- | --- | --- | --- | --- | --- |
| Available/current terminal record | Enabled | Disabled | Disabled | Disabled | Disabled | Disabled |
| Planned truck | Disabled | Enabled | Disabled | Disabled | Disabled | Enabled |
| Active truck, lane idle, planned session exists | Disabled | Disabled | Enabled | Disabled | Disabled | Enabled |
| Active session owns lane | Disabled | Disabled | Disabled | Enabled | Disabled | Enabled |
| Active truck, all sessions terminal, at least one complete | Disabled | Disabled | Disabled | Disabled | Enabled | Enabled |
| Coordinator closed | Disabled | Disabled | Disabled | Disabled | Disabled | Disabled |

Rules are selected-dock scoped. Another available dock may still register a
truck while the shared lane belongs to a different dock. Only session start is
globally blocked by lane occupancy.

## Confirmations and shutdown

Confirmation is required before:

- cancelling an active session;
- cancelling a truck;
- exiting while the lane is occupied or a non-terminal truck record exists.

Messages identify the dock/session/operation and explain that an unfinished
live count is discarded. Completed session totals remain unchanged.

Accepted exit delegates to `OperatorApplicationService.shutdown()` and the
public coordinator close path. If a session owns the lane, it is cancelled and
the live count is discarded. The truck remains unfinished; HogFlow does not
fabricate completion. With no persistence, planned/active in-memory records do
not survive process exit.

Declining confirmation performs no application command.

## Status and lane indicators

The status area reports bounded presentation messages such as:

- Ready;
- Truck Registered;
- Truck Started;
- Session Started — Lane Occupied;
- Session Completed — Lane Released;
- Session Cancelled — Unfinished live count discarded;
- Truck Completed;
- Operation Cancelled;
- Action Not Confirmed;
- Application Closed;
- Error.

The lane owner is shown textually in both the shared-lane panel and the dock
panel (`LANE OWNER` / `Owns Shared Lane: YES`). Color is not the only semantic
indicator.

## Form validation

Registration input is parsed before calling `OperatorApplicationService`.
Presentation rejects:

- missing operation ID;
- empty session plan;
- missing or duplicate session IDs;
- non-positive or duplicate sequence numbers;
- unsupported pig types;
- malformed or invalid expected counts.

Phase 8 still performs authoritative domain validation when the immutable
command is constructed and applied.

## Manual refresh and state ownership

There is no timer, polling loop, worker, thread, async task, or hidden snapshot
cache. Every render is rebuilt from one fresh
`MultiDockRuntimeCoordinator.snapshot()`. Tkinter retains only form/widget text
and one presenter reference, never truck, session, lane, counter, or snapshot
business state.

## Future camera integration

A future explicitly authorized composition may replace the no-camera
fingerprint and lifecycle factory, route real crossing results into Phase 8,
and request manual refresh after updates. Phase 9.2 does not implement that
composition and does not define concurrency.

## Explicit exclusions

Phase 9.2 does not implement camera acquisition, OpenCV preview, YOLO,
detection, tracking, video, automatic refresh, persistence, SQLite, API,
networking, authentication, scheduling, hardware, operator usability
validation, or Phase 10.
