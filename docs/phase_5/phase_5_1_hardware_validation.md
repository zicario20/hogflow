# Phase 5.1 — Real USB Webcam Validation

## Status

Phase 5.1 live acquisition passed a real-hardware validation on one laptop USB
webcam after two hardware-discovered defects were corrected. This evidence is
specific to the tested camera, Windows OpenCV MSMF backend, and local runtime.
It does not establish RTSP compatibility or production readiness.

Validation date: July 18, 2026.

## Hardware and runtime

- Operating system: Windows 11 (\`10.0.26200\`)
- Camera: \`HD User Facing\`, USB device index 0
- Backend: OpenCV MSMF
- Python: 3.12.13
- OpenCV: 4.13.0
- Logical CPU count: 4
- Observed resolution: 640 × 480
- Camera-reported FPS: 30
- Post-fix sustained observed FPS: approximately 30

No preview, image, snapshot, recording, detector, tracker, counter, network
transmission, or media artifact was used or created.

## Hardware-discovered defects and corrections

### Quantized-clock FPS under-reporting

Some consecutive hardware frames received identical monotonic timestamps.
\`StreamHealthMonitor\` added only positive intervals to both the interval sum
and sample count. Zero-duration intervals were omitted from the denominator,
causing a true approximately 30 FPS stream to report approximately 16–17 FPS.

The monitor now counts every non-negative interval. A synthetic regression test
covers repeated timestamps. A post-fix hardware probe measured 30.067 FPS and
reported 29.938 FPS.

### Cross-thread MSMF shutdown

\`LiveStreamRunner.stop()\` immediately released the OpenCV capture from the
consumer thread while the producer could still be inside \`read()\`. On this
camera, MSMF emitted \`can't grab frame\` warnings and release took approximately
10 seconds.

Shutdown now sets the stop request and closes the consumer buffer first. The
producer gets a short cooperative grace period to finish its read and release
the source on its own thread. \`join()\` retains a forced-close fallback for a
genuinely blocked source. Synthetic tests cover both paths.

After correction, hardware shutdown completed in 0.328–0.391 seconds during
five reopen cycles, 0.375 seconds after ten minutes, and 0.391 seconds after
thirty minutes, with no MSMF warning.

## Startup and warm-up

The post-fix bounded probe recorded:

- source-open latency: 3.896 seconds
- ten-frame warm-up duration: 1.385 seconds
- observed resolution: 640 × 480
- camera-reported FPS after open: 30
- resource release: successful

The five repeated lifecycle startup latencies ranged from 4.297 to 8.281
seconds. Camera startup time is hardware/backend dependent and is not a
real-time guarantee.

## Five consecutive reopen cycles

Every cycle used a fresh camera source, runner, and four-frame \`drop_oldest\`
buffer. Each acquired for at least 30 seconds after the first delivered frame.

| Cycle | Frames acquired | Delivered | Dropped | Observed FPS | Startup (s) | Stop (s) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 899 | 697 | 199 | 29.964 | 6.234 | 0.359 |
| 2 | 899 | 682 | 214 | 29.980 | 5.469 | 0.359 |
| 3 | 903 | 695 | 205 | 30.020 | 5.735 | 0.328 |
| 4 | 902 | 715 | 184 | 30.096 | 8.281 | 0.344 |
| 5 | 899 | 735 | 161 | 29.980 | 4.297 | 0.391 |

All five cycles had:

- zero duplicate sequence IDs
- zero non-monotonic sequence IDs
- delivered sequence gaps exactly equal to reported dropped frames
- maximum buffer depth four
- health transitions \`created → opening → running → stopped\`
- successful thread join and camera release
- immediate eligibility for the next open

## Ten-minute continuous run

- duration: 600.015 seconds
- frames acquired: 17,996
- calculated acquisition rate: 29.993 FPS
- health-reported FPS: 29.994
- frames delivered: 14,619
- frames dropped: 3,374
- delivered sequence gaps: 3,374
- pre-stop buffer depth: 3
- maximum buffer depth: 4
- duplicate/non-monotonic IDs: 0 / 0
- temporary/fatal read failures: 0 / 0
- reconnects: 0
- RSS range: 89.656–96.711 MiB
- RSS first/last: 89.656 / 96.652 MiB
- process CPU average: 21.231% of one core, approximately 5.308% of total
  four-core capacity
- system CPU average/maximum: 41.959% / 70.8%
- stop latency: 0.375 seconds
- final health: stopped
- camera release: successful

The intentional slow consumer exercised overflow. The accounting identity
\`delivered + dropped + pending = acquired\` held exactly.

## Thirty-minute continuous run

- duration: 1,800.016 seconds
- frames acquired: 53,997
- calculated acquisition rate: 29.998 FPS
- health-reported FPS: 29.998
- frames delivered: 43,812
- frames dropped: 10,181
- delivered sequence gaps: 10,181
- pre-stop buffer depth: 4
- maximum buffer depth: 4
- duplicate/non-monotonic IDs: 0 / 0
- temporary/fatal read failures: 0 / 0
- reconnects: 0
- RSS range: 85.051–96.199 MiB
- RSS first/last: 89.254 / 89.422 MiB, a 0.168 MiB increase
- process CPU average/maximum: 20.021% / 52.0% of one core
- process CPU average normalized across four logical CPUs: approximately 5.005%
- system CPU average/maximum: 42.327% / 85.2%
- stop latency: 0.391 seconds
- final health: stopped
- camera release: successful

The long-run RSS trend was non-increasing by linear regression and the first
and last samples differed by less than 0.2 MiB. No runaway memory growth,
deadlock, crash, or frame-acquisition instability was observed.

## Interrupt validation

The final interactive validation launched the real USB pipeline in a visible
console with no automatic stop condition. Live statistics showed increasing
frame acquisition and delivery while health remained \`running\`. The operator
then pressed Ctrl+C on the physical keyboard. Python received a real
\`KeyboardInterrupt\`, the normal shutdown path completed, final health was
\`stopped\`, the camera was released, and the pipeline process exited with code
0.

The harness then created a fresh source and runner automatically. The same
camera reopened successfully, acquired 453 frames during the bounded 15-second
run, stopped normally, reached final health \`stopped\`, released the camera,
and left no Python camera process running.

Two detached-process signal experiments exposed limitations of this automated
Windows launcher rather than the acquisition loop:

1. \`CTRL_C_EVENT\` was not delivered to the child; the supervisor timed out and
   the bounded child later exited normally. Camera release and reopen succeeded.
2. \`CTRL_BREAK_EVENT\` terminated the child with Windows status \`0xC000013A\`
   instead of allowing Python to emit its final CLI payload. The operating
   system released the device and immediate reopen succeeded.

An initial visible PowerShell-wrapper run passed every child-process validation
field, but Ctrl+C also caused the outer PowerShell host to return exit code 1.
The validation was repeated by launching Python directly in its own visible
window; the same camera checks passed and the actual pipeline process returned
exit code 0. The detached-process signal experiments above remain documented as
harness limitations, not camera-pipeline failures.

## Warnings and failures

Before correction, five MSMF \`can't grab frame\` shutdown warnings were
observed: four during the initial reopen series and one after the initial
ten-minute run. No such warning occurred in any post-fix hardware rerun.

The only final software-validation warnings were Git's Windows LF-to-CRLF
working-copy notices; \`git diff --check\` still passed. No final hardware run
emitted an OpenCV warning.

## Validation gates and data integrity

- full test suite: 362 passed
- Ruff lint: passed
- Ruff formatting: passed
- package compilation: passed
- dependency consistency: passed
- diff whitespace validation: passed
- active Python camera processes after validation: 0
- tracked forbidden media/model/camera artifacts: 0
- camera capture/debug directories created: 0
- frames, snapshots, recordings, and reports containing frame data: 0

## Evidence boundary

This validates the Phase 5.1 live-stream infrastructure on real hardware only.

It does NOT validate RTSP behavior.

It does NOT validate pig detection.

It does NOT validate tracking.

It does NOT validate counting.

Phase 5.2 has not started.
