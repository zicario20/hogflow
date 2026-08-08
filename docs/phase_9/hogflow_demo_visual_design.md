# HogFlow Demo UI — Industrial HMI Visual Design

Status: **IMPLEMENTED — PRESENTATION ONLY**

This visual-design increment applies the approved Option A direction to the
existing Phase 9 Tkinter operator workstation. It does not create a new roadmap
phase and does not alter detector, tracker, crossing, counting, session, camera,
replay, or runtime-supervision behavior.

## Design direction

The workstation uses a restrained dark industrial vocabulary intended for
plant-floor readability and an honest manager demonstration:

- deep navy/graphite backgrounds and subtly elevated panels;
- a cool blue primary accent;
- high-contrast system typography using `Segoe UI` with no bundled font assets;
- green for healthy/success, amber for attention, red for critical conditions,
  blue for active/information, and gray for inactive/neutral states;
- every color-coded state retains a readable text label;
- a compact 4/8-based spacing system and visible keyboard focus;
- no animation, remote asset, additional refresh loop, or decorative video
  processing.

The approved Option A hierarchy remains the foundation. Option B contributes
compact secondary diagnostics and a dense pipeline summary. Option C
contributes the prominent `LIVE COUNT` and the stronger framed treatment of the
shared-camera preview. The full density of Option B and oversized preview of
Option C are intentionally excluded.

## Information hierarchy

The rendering priority is:

1. global HogFlow and system state;
2. lifecycle `LIVE COUNT`;
3. shared-lane ownership;
4. camera preview;
5. available operator action;
6. four dock states;
7. technical diagnostics.

The header identifies `HogFlow — AI Livestock Receiving & Counting` and shows
mode, system, camera, and pipeline states. The shared-lane card keeps active
dock, operation, pig type, session, and live lifecycle count together. The
pipeline card retains all existing bounded diagnostics and adds a neutral
presentation flow:

```text
SOURCE → DETECTOR → TRACKER → CROSSING → COUNTER → SHARED LANE
```

This flow is explanatory presentation. It does not fabricate independent
health evidence for stages that the public snapshots do not expose.

## Approved operating-mode language

Mode is derived only from safe source provenance already present in the camera
snapshot:

- no configured source or synthetic composition: `VALIDATION BUILD`;
- local file: `VALIDATION MODE`;
- USB or RTSP camera: `LIVE MODE`.

`PRODUCTION MODE` is not present. It remains reserved for a future version with
representative validation and documented pilot readiness. No accuracy,
certification, production-readiness, or validated-pig-count claim is shown.

## Responsive workstation behavior

The wide layout retains the approved dock order:

```text
Dock 1    Dock 3
Dock 2    Dock 4
```

The bounded 16:9 preview and Operator Actions remain aligned high on the
screen. At narrower widths, actions reflow ahead of the preview and pipeline
metrics wrap into additional rows without shrinking essential text. The
existing single vertically scrollable root remains the fallback for small
windows and Windows display scaling. Initial window sizing uses available
desktop space without requiring permanent maximization.

## Visual state and accessibility rules

- lane ownership uses label, accent border, and card treatment;
- selected docks and lane-owning docks remain distinguishable;
- disabled controls retain readable text and do not appear actionable;
- destructive actions use a restrained critical treatment and keep their
  existing confirmation dialogs;
- the live count is larger than diagnostic metrics and never includes false
  precision;
- empty, stopped, exhausted, degraded, and failed states retain explicit text;
- local-video EOF continues to retain the last frame and expose replay actions;
- preview primitives remain transient, and no image/frame history is retained.

## Architecture boundary

The presentation consumes only immutable `OperatorScreen` data and existing
presenter callbacks. `theme.py` contains immutable presentation tokens and pure
status/mode mappings. The UI still owns no business state, does not calculate
counts, and does not import OpenCV, detector, tracker, counting, storage, or
camera infrastructure.

No new worker, thread, queue, camera, source, counter, persistence component,
or polling loop is introduced. The existing one 200 ms bounded Tk refresh and
one-slot preview channel are unchanged.

## Evidence and limitations

Headless structural tests cover mode truthfulness, semantic status mapping,
theme hierarchy, responsive layout, button state ownership, dock placement,
and preview containment. A real Tk construction smoke test verifies that the
native widgets accept the selected styling. A separately authorized, ignored
local video completed three consecutive empty-detector playbacks with
`VALIDATION MODE`, EOF status, retained final frame, and replay controls. No
frame, model output, or video artifact was retained. Local review screenshots
remain outside the repository and were not committed.

This implementation is visual evidence only. It is not an operator usability
study, physical-camera validation, model validation, pig-counting validation,
or production-readiness evidence.
