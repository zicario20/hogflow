# Phase 9.4 — Live Operator Experience, Video Preview and Diagnostics

## Status

IMPLEMENTED as local, ephemeral operator-preview infrastructure.

Validation is synthetic and headless. No physical camera, pig-specific
detector, representative pig footage, or count-accuracy evidence was used.

## Objective and preserved topology

Phase 9.4 exposes the already-authoritative Phase 9.3 pipeline to the local
operator without redesigning it:

```text
Dock 1 ─┐
Dock 2 ─┤
Dock 3 ─┼── Shared lane ── One source ── One worker/pipeline ── Phase 7
Dock 4 ─┘                                      │
                                               └── one-slot visual channel
                                                       │
                                                       └── Tk UI thread
```

There is still one shared camera, detector, tracker, crossing detector,
counter, lane, and worker. Docks retain only their independent business state.
The preview is not a source of truth and never routes crossing or counting
evidence.

## Latest-frame visual channel

`LatestPreviewFrameChannel` owns exactly one optional `PreviewFrame` reference.
Publication atomically replaces that reference; normal consumption marks it as
delivered but keeps the same one reference available for a final-frame freeze
after local-file EOF. The channel has:

- no `Queue` or `deque`;
- no playback or frame history;
- no recording or filesystem output;
- no wait for the UI;
- bounded aggregate counters only.

A slow or stopped renderer causes newer frames to replace older ones. It
cannot create backlog or slow the serial counting path through UI work.
`PreviewFrame` contains immutable packed RGB24 bytes plus framework-neutral
overlay values. It contains no dock, truck, session, count, or Phase 8
snapshot.

## Overlay model

The camera processor builds immutable diagnostics after successful tracking:

- normalized current track boxes;
- temporary tracker ID;
- class label and confidence;
- configured normalized finite line;
- configured anchor and current geometric side;
- current-frame crossing direction, when an event exists;
- source frame sequence and dimensions.

`build_preview_render_plan()` maps those values to line, rectangle, point, and
text primitives. The Tk adapter renders the RGB frame and primitives on one
canvas. Camera status and pipeline status are supplied separately from current
application snapshots. Color is supplemented by text labels, so it is not the
only semantic indicator.

No overlay performs tracking, crossing, duplicate suppression, reverse
classification, or counting.

## Local-file completion and replay

Normal local-file EOF is an operator-visible completion state, not a fatal
camera failure. The camera displays `Exhausted`, preview displays `End of
Video`, and the final one-slot frame remains visible. `Restart Video` becomes
available only for an exhausted `FILE` source; `Start Pipeline` is also enabled
and routes to the same replay lifecycle. Replay recreates the decoder, resets
tracker/crossing playback state, reuses the already loaded detector/processor,
and preserves the selected source, current shared-lane session, Phase 7 count,
and bounded cumulative diagnostics. Replays can be requested repeatedly.

`--real-time-video` optionally paces local files against embedded source
timestamps inside the existing worker. It creates no thread, queue, frame
history, or UI polling and never applies to USB cameras.

## Thread ownership and UI refresh

The Phase 9.3 worker thread owns source reads and serial
detector→tracker→crossing processing. It performs only an O(1) one-slot
publication and never imports or calls Tkinter.

The Tk thread alone:

- consumes the latest visual slot;
- builds/renders the canvas plan;
- refreshes immutable business and pipeline snapshots;
- handles operator controls and shutdown.

The desktop keeps at most one scheduled `root.after` callback at a time, with
a 200 ms interval. This is a bounded presentation refresh, not a background
worker or busy loop. Closing the view cancels the callback. Manual Refresh
remains available.

## Failure isolation

Overlay preparation/publication failures are recorded as preview diagnostics
and the next valid publication may recover the visual channel. A Tk rendering
failure disables preview for that run, clears the visual slot, and presents:

```text
Live preview rendering stopped; counting continues.
```

Neither category changes camera/pipeline status, invokes Phase 8, nor fabricates
an empty crossing result. Detector, tracker, crossing, source, and counting
failures retain their existing authoritative categories and behavior.

## Bounded source recovery

`CameraRecoveryConfiguration` applies only to the configured live USB source.
Engineering defaults are:

- `max_reopen_attempts = 3` per pipeline run;
- `temporary_failures_before_reopen = 3`;
- `retry_delay_seconds = 0.25`.

Normal local-file exhaustion is never reopened. A temporary live read marks the
camera `DISCONNECTED`. At the configured threshold the controller:

1. clears the visual slot;
2. closes the source;
3. resets tracker and crossing state;
4. waits the configured delay;
5. attempts a bounded reopen;
6. resumes the same serial worker on success;
7. fails safely after the attempt limit.

The frame sequence remains monotonic and no missing frame is fabricated.
Phase 7's current session count is not reset automatically. Consequently,
temporary tracker-ID reuse after reconnect can suppress a valid new animal or
other tracking instability can affect count accuracy. This remains an
unvalidated operational risk; Phase 9.4 does not invent re-identification.

## Application and presentation API

Presentation consumes only `OperatorApplication`:

- `latest_preview_frame()`;
- `preview_snapshot()`;
- `record_preview_render_failure()`;
- existing `pipeline_snapshot()` and Phase 8 `snapshot()`.

The UI never imports camera infrastructure, OpenCV, detector/tracker adapters,
or Phase 7/8 internals. `--disable-preview` supports explicit diagnostic
disablement. Source opening and preview publication still begin only after the
operator selects Start Pipeline.

## Live diagnostics

The desktop displays:

- effective acquisition FPS;
- frames acquired and processed;
- temporary processing failures;
- stale evidence rejected;
- camera and pipeline state;
- worker alive/stopped;
- bounded recovery attempts;
- preview health, FPS, and failures;
- active crossing lifecycle;
- active dock, session, pig type, live lifecycle count, and completed trucks.

Live count and finalized totals continue to come only from Phase 8 snapshots.

## Scrollable desktop accessibility hotfix

A later desktop usability correction keeps the complete operator page inside
one vertically scrollable Tkinter viewport. The shared-lane status, pipeline
diagnostics, bounded preview, dock panels, totals, all operator actions, status
messages, and exit action move together in that viewport. The vertical
scrollbar is always present; the embedded content width follows the visible
canvas width to avoid unnecessary horizontal scrolling.

Windows mouse-wheel navigation and Up/Down, Page Up/Page Down, and Home/End
navigation are window-scoped and installed once. The multiline session-plan
`Text` widget preserves its own wheel and editing navigation. All owned
bindings and the existing single 200 ms refresh callback are removed during
close. The preview retains only its latest frame and starts at a bounded
16:9 display size; scrolling and rendering remain presentation concerns and
cannot change counting, detector, tracker, or camera-pipeline behavior.

## Ergonomic workstation layout

The desktop uses a dense monitoring hierarchy. Shared-lane status is a compact
horizontal bar, pipeline diagnostics
wrap into a compact dashboard, and the bounded preview aligns with the top of
the grouped operator actions. Truck/session, pipeline/source, and application
controls remain distinct and immediately discoverable. Dock summaries use the
deterministic two-by-two arrangement:

```text
Dock 1    Dock 3
Dock 2    Dock 4
```

At wide workstation sizes the status panels share horizontal space and the
preview/actions remain side by side. Narrow windows reflow totals and actions
above the preview, without horizontal scrolling; the full-page vertical
scroll remains the accessibility fallback. Preview planning keeps one uniform
scale factor, so the reduced display height does not distort frames. This is a
presentation-only arrangement: actions, enabled states, live counts, totals,
camera health, and pipeline health still come from immutable snapshots and
existing public presenter/application operations.

## Demo industrial HMI visual system

A later presentation-only increment applies a centralized dark industrial HMI
theme without changing Phase 9.4 runtime semantics. The header exposes the
truthful mode (`VALIDATION BUILD`, `VALIDATION MODE`, or `LIVE MODE`) plus
system, camera, and pipeline state. Shared-lane ownership and `LIVE COUNT` have
priority over bounded technical diagnostics; the preview uses a restrained
professional frame, while the four docks preserve the existing two-by-two
ergonomic layout.

The visual system uses semantic color together with labels, system fonts,
compact 4/8-based spacing, visible focus, readable disabled controls, and no
animation or remote assets. The UI still consumes immutable snapshots only.
There is no `PRODUCTION MODE`, no production-readiness claim, and no change to
the detector, tracker, crossing, counter, replay, shared lane, session, worker,
or one-slot preview contracts. See
[`hogflow_demo_visual_design.md`](hogflow_demo_visual_design.md) for the full
presentation specification.

## Shutdown

Application shutdown preserves Phase 9.3 ordering:

1. request worker stop;
2. close the source to unblock reads;
3. join the one worker;
4. reject stale evidence;
5. close processor resources;
6. close the visual channel and discard its current frame;
7. close/cancel the active lane according to existing Phase 9.2 rules;
8. cancel the Tk refresh callback and destroy the window.

Repeated stop/close remains safe after successful cleanup.

## Explicit exclusions

Phase 9.4 does not add persistence, database, API, network, cloud, recording,
arbitrary seek/playback controls, frame history, multiple cameras, per-dock resources,
ROI/line editor,
calibration, authentication, reports, exports, hardware integration, model
training, accuracy improvement, Phase 10, or production deployment.
