# Phase 5.3 Validation

## Automated evidence

The Phase 5.3 suite covers immutable models, configuration validation,
protocol typing, deterministic fake trackers, temporary identity retention,
two-object isolation, brief misses, expiry, frame gaps, reset, close,
multi-stream rejection, telemetry, adapter conversion, malformed framework
output, preview behavior, CLI composition, pipeline failures, reconnect reset,
bounded source buffering, and architecture boundaries.

The full local suite after implementation reports 453 passing tests. The
64-test focused Phase 5.3 and architecture run also passes. Supervision emits
one documented `FutureWarning`: its bundled ByteTrack class is deprecated and
scheduled for removal in Supervision 0.30.

Required commands:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src
python -m pip check
git diff --check
```

Import smoke coverage includes tracking contracts/models, the Supervision
adapter, live tracking pipeline, tracking preview, and the extended CLI. CI
uses no webcam, GPU, internet, pig weights, or real data.

## Synthetic scenarios

- One moving object retains one deterministic temporary ID.
- Two independent objects retain separate temporary IDs.
- A brief miss inside the configured test tolerance retains identity.
- Expiry followed by reappearance receives a new ID.
- Repeated zero-detection frames remain valid.
- A malformed box is rejected before tracker state changes.
- Separate stream-bound tracker instances do not share state.
- Reset clears prior lifecycle state and may reuse IDs.
- Skipped source frame numbers retain exact frame association.
- Detector failure does not fabricate tracker input.
- Slow detector/tracker operation leaves the Phase 5.1 source buffer bounded.
- Synthetic detections pass through the installed Supervision ByteTrack API.

These scenarios validate contracts and deterministic control flow. They do not
prove representative pig identity retention or ByteTrack accuracy.

## Hardware and model status

Phase 5.3 was exercised locally with the built-in USB webcam, the explicit
synthetic moving-box detector, and the real Supervision ByteTrack adapter.
Preview was disabled and no frame was saved.

The final paired validation produced:

- Long run: 2,636 acquired frames at 30.00 observed camera FPS, approximately
  87.9 seconds of frame flow, 2,632 successful tracking updates, 2,501 current
  track emissions, zero source drops, and zero tracking failures.
- Immediate reopen: 1,146 acquired frames at 30.02 observed camera FPS,
  approximately 38.2 seconds of frame flow, 1,145 successful tracking updates,
  1,088 current track emissions, zero source drops, and zero tracking failures.
- Average tracking latency: 2.89 ms in the long run and 2.91 ms after reopen.
- Process sampling across both runs: 26.3% average CPU, 73.9% peak CPU, and
  resident memory between approximately 52 MB and 180 MB.
- Both runs ended with source health `stopped`, camera released, detector
  closed, and tracker closed.

An earlier 15-second wall-clock reopen attempt ended with zero frames because
the Windows camera source was still opening when the duration bound expired.
It released resources cleanly and was not counted as successful evidence. The
extended immediate-reopen run above corrected the validation window without a
code change.

This hardware evidence validates live camera/detector/tracker integration and
lifecycle only. Synthetic boxes are not real detections, and this is not real
pig tracking or tracking-accuracy evidence.

No validated local pig-specific detector weights or matching evaluation
evidence were found. Real pig tracking validation is blocked by that missing
prerequisite. No model was downloaded.

## Acceptance boundary

Phase 5.3 acceptance establishes replaceable live temporary-ID integration.
It does not implement or validate virtual-line crossing, unique-animal
counting, reverse movement, sessions, persistence, or Phase 5.4.
