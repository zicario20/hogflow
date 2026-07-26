# Phase 9.3 — Camera Acquisition and Counting Pipeline Integration

## Status

IMPLEMENTED as deterministic camera/pipeline infrastructure.

Representative pig detection and real pig-counting validation remain pending.
The executable default uses `EmptyDetector` and `EmptyTracker`; it exercises
source and lifecycle integration without fabricating detections.

## Physical topology

```text
Dock 1 ─┐
Dock 2 ─┤
Dock 3 ─┼── Shared hallway ── One camera ── One pipeline ── Scale
Dock 4 ─┘
```

Four docks retain independent business records. They do not own cameras,
detectors, trackers, crossing state, or counters. `SharedCountingLane` remains
the sole owner of the Phase 7 counter, and at most one active unloading
session owns the lane.

## Architecture

```text
TkOperatorView
    ↓ public OperatorApplication
OperatorApplicationService
    ↓
CountingPipelineController ── one worker
    ↓
CameraSource → LiveDetector → LiveTracker → LiveCrossingDetector
    ↓ LiveCrossingResult
SerializedMultiDockRuntimeAccess
    ↓
MultiDockRuntimeCoordinator → SharedCountingLane → Phase 7 counter
```

`hogflow.camera` defines immutable camera/pipeline snapshots, lifecycle errors,
ports, the one-worker controller, and
`DetectorTrackingCrossingProcessor`. The processor calls existing public
detector, tracker, and crossing contracts. It does not duplicate ByteTrack,
Ultralytics, line geometry, directional counting, duplicate suppression, or
reverse handling.

`LiveCountingPipeline` is intentionally not composed here because it owns a
counter. Phase 8.4 already establishes that `SharedCountingLane` owns the sole
Phase 7 counter. Phase 9.3 therefore routes geometric `LiveCrossingResult`
evidence into that lane.

## Source configuration

The public application accepts:

- local non-negative camera indexes;
- existing local video files.

Both become the existing protected `StreamConfiguration` only inside camera
orchestration. Snapshots expose sanitized source identity/type, never the
local path. OpenCV remains lazy inside `hogflow.adapters`; importing
`hogflow`, `hogflow.application`, `hogflow.presentation`, or `hogflow.camera`
does not import `cv2` or open a source.

Examples:

```console
python -m hogflow run --camera 0
python -m hogflow run --video local-validation.mp4
hogflow --help
```

`--camera` and `--video` are mutually exclusive. A source is configured at
composition time but opens only after `Start Pipeline`. The previous
no-source mode remains available.

## Worker and serialization ownership

Exactly one non-daemon worker named
`hogflow-shared-counting-pipeline` exists per executable composition. It:

1. opens one source;
2. starts one detector/tracker processor;
3. reads one frame;
4. processes detection and tracking serially;
5. activates crossing only for the current lane lifecycle;
6. routes immutable crossing evidence;
7. repeats until stop, EOF, or failure;
8. closes processor and source.

There is no queue, worker per dock, unbounded frame history, Tkinter callback,
async task, or multiprocessing boundary. At most one `FramePacket` is retained
by the worker.

`SerializedMultiDockRuntimeAccess` owns one `RLock`. Operator commands,
Phase 8 snapshots, lane-binding reads, and crossing-result routing use that
same boundary. Expensive detector/tracker/crossing work occurs outside the
lock. The worker never calls Tkinter.

The coordinator and shared lane remain caller-serialized rather than being
silently relabeled thread-safe.

## Session lifecycle and stale evidence

For each frame the worker captures an immutable binding:

```text
(dock_id, source_id, crossing_lifecycle_id)
```

The frame processor activates crossing with that exact lifecycle. Before
mutation, the runtime boundary verifies that the same dock, source, and
lifecycle still own the lane and that the returned `LiveCrossingResult`
matches them.

If completion, cancellation, reconnect-style lifecycle replacement, or a new
session occurs while a frame is being processed, the delayed result is
rejected as stale. It does not increment the old or new session. Timestamp
comparison alone is never used for this protection.

When the lane becomes idle or changes lifecycle, the processor clears crossing
side state and resets temporary tracker identity state. Phase 7 independently
starts a fresh counted-identity lifecycle for each Phase 8 session.

## State machines

Camera states:

- `NOT_CONFIGURED`
- `CLOSED`
- `OPENING`
- `RUNNING`
- `ENDED`
- `FAILED`

Pipeline states:

- `STOPPED`
- `STARTING`
- `RUNNING`
- `STOPPING`
- `FAILED`

`CameraSnapshot` and `CountingPipelineSnapshot` expose bounded counters,
source exhaustion, last successful frame time, current crossing lifecycle,
worker liveness, and sanitized failure category/message. No framework object,
frame data, path, credential, or stack trace is exposed.

## Failure policy

- invalid configuration/lifecycle commands are explicit application errors;
- camera open/read failures move the pipeline to `FAILED`;
- fatal detector, tracker, or crossing errors move it to `FAILED`;
- temporary detector/tracker errors skip that frame and remain observable as
  bounded temporary failure telemetry;
- delayed results are rejected and counted as stale evidence, without failing
  a healthy worker;
- unexpected worker exceptions become a sanitized `INTERNAL` failure;
- source/processor cleanup always runs;
- a shutdown timeout is an explicit fatal shutdown error.

No failure is converted into an empty successful count.

## Shutdown

Application shutdown:

1. requests worker stop;
2. releases the source to unblock reads;
3. joins the one worker;
4. ensures stale results cannot route;
5. closes detector/tracker/crossing resources;
6. closes/cancels the active shared-lane binding using existing Phase 9.2
   behavior;
7. closes the coordinator and UI.

Stop and shutdown are idempotent after successful cleanup. No worker remains
alive after a successful close.

## Presentation

The manual-refresh Tkinter view adds:

- Configure/Open Source;
- Start Pipeline;
- Stop Pipeline;
- source identity;
- camera and pipeline status;
- acquired/processed frame totals;
- last safe error;
- active crossing lifecycle.

Button availability derives from immutable pipeline snapshots. There is no
video preview, image rendering, overlay, automatic polling, or worker-to-Tk
call.

## Limitations

- The default executable detector/tracker are empty technical adapters.
- No validated pig-specific weights were found or added.
- No physical camera was opened during Phase 9.3 validation.
- No real pig detections, tracking, crossing events, or count evidence were
  produced.
- The configured vertical line is an engineering composition default, not a
  calibrated production line.
- USB blocking behavior depends on the local OpenCV backend; shutdown has a
  bounded timeout and explicit failure.
- Reconnection loops, RTSP credential management, preview, calibration,
  persistence, Phase 9.4, and Phase 10 remain out of scope.
