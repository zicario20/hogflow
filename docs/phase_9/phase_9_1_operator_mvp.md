# Phase 9.1 — Operator MVP User Interface

## Status and evidence

Phase 9.1 implements the first local operator-facing presentation and
application workflow. It is a functional research-MVP desktop boundary backed
by synthetic tests.

It is not a production GUI and does not open a camera, process frames, persist
records, or establish real pig-count accuracy.

## Architecture

```text
TkOperatorView
    ↓
OperatorPresenter
    ↓
OperatorApplication
    ↓
MultiDockRuntimeCoordinator
    ↓
Phase 8 domain/session integration
    ↓
Phase 7 public counter
```

`hogflow.presentation` depends only on the public `hogflow.application`
boundary and its own immutable display models. It does not import domain,
sessions, counting, pipelines, CV frameworks, storage, networking, or
filesystem code.

`hogflow.application` translates operator intent into public coordinator
calls. It may construct validated immutable Phase 8 input values, but it owns
no truck, session, lane, counter, or snapshot state. Phase 7 and Phase 8 do not
import either Phase 9 package.

## Snapshot-driven state

`MultiDockRuntimeCoordinator.snapshot()` remains the sole source of display
state. Every successful command and every manual refresh obtains a new
`MultiDockRuntimeSnapshot`.

The presenter creates one transient `OperatorScreen` and immediately sends it
to the view. It does not cache that screen. Widget strings are render output,
not a second business-state store.

The shared-lane live count is copied directly from
`SharedCountingLaneSnapshot.current_session_count`. Finalized totals are copied
from `aggregate_completed_pig_count` and
`aggregate_totals_by_pig_type`. The completed-truck display uses the additive,
read-only `MultiDockRuntimeSnapshot.completed_operation_count` projection.
The UI never increments or recomputes these totals.

## Desktop layout

The unstyled Tkinter adapter provides:

- top: shared lane status, dock, truck, pig type, session, and live count;
- left: immutable Dock 1–4 panels;
- right: one dock selector, truck/session input, and explicit operator actions;
- bottom: finalized total, totals by pig type, current completed-truck records,
  and active trucks.

Tkinter is loaded only when `run_operator_desktop()` is called. Importing
`hogflow.presentation` does not create a window or require a display server.
There is no timer, polling loop, worker, thread, second window, preview, or
automatic refresh.

## Operator workflow

The supported actions are:

1. Register a truck with one or more explicitly planned sessions.
2. Start the truck.
3. Start one selected session and bind the shared lane.
4. Manually refresh the immutable snapshot.
5. Complete or cancel the active session.
6. Complete or cancel the truck.

Registration accepts newline-separated session rows in the desktop:

```text
session-1,1,opg,60
session-2,2,regular
```

The fourth value is an optional expected count. Phase 8 remains authoritative
for identifier, sequence, pig-type, lifecycle, occupancy, ordering, count, and
terminal-state validation.

## Command boundary

`OperatorApplicationService` delegates only to public coordinator methods:

- `register_operation`
- `start_operation`
- `start_session`
- `complete_session`
- `cancel_session`
- `complete_operation`
- `cancel_operation`
- `snapshot`

The service receives an injected aware clock and an injected
crossing-lifecycle ID factory. Phase 9.1 does not invent camera lifecycle
provenance. A future authorized camera composition root must supply an ID that
matches the real crossing pipeline.

## Errors

Expected HogFlow domain and application errors are:

1. shown through `OperatorView.show_error()`;
2. re-raised by the presenter so callers and tests can observe the failure;
3. handled at the desktop callback boundary only after they have been shown.

Unexpected exceptions are not converted into success. No fallback state or
fabricated count is rendered.

## Future camera integration point

The desktop receives an already composed `OperatorApplication`; it does not
construct a source, detector, tracker, crossing pipeline, counter, lane, or
coordinator.

A later explicitly authorized integration may:

- compose the shared camera pipeline and the existing shared lane;
- supply crossing lifecycle provenance to `OperatorApplicationService`;
- route real successful crossing results through Phase 8;
- invoke manual snapshot refresh after those updates.

That work is not part of Phase 9.1.

## Explicit exclusions

Phase 9.1 does not implement:

- camera acquisition, preview, video rendering, OpenCV windows, or streaming;
- real or simulated automatic frame ingestion;
- business logic inside presentation;
- polling, timers, threads, async execution, or scheduling;
- persistence, SQLite, filesystem output, API, networking, or authentication;
- review events, confirmation workflow, manual count override, or dashboards;
- Phase 10 or later phases.
