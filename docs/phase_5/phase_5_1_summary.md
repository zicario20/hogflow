# Phase 5.1 — Summary

## Status

Phase 5.1 live-camera acquisition foundation implemented. The production input
architecture is stream-first, but no real camera compatibility, pig detection,
tracking, counting, or production readiness is claimed. Phase 5.2 has not
started.

## Delivered

- immutable framework-neutral stream, frame, timestamp, health, statistics,
  buffering, and configuration models;
- a small synchronous `CameraSource` contract with explicit read outcomes;
- protected runtime RTSP/file locators and opaque safe source identities;
- an isolated OpenCV USB/RTSP adapter with best-effort settings and timeouts;
- a non-live one-pass OpenCV file source for development only;
- deterministic scripted synthetic source for CI and failure/reconnect tests;
- thread-safe fixed-capacity buffering with drop-oldest and drop-newest policy;
- lifecycle-scoped sequence IDs and observable sequence gaps;
- synchronous `LiveStreamRunner` plus a small producer-thread wrapper;
- deterministic reconnection backoff and stable-operation reset;
- bounded health and statistics without raw error histories;
- headless diagnostic CLI with no recording or frame persistence;
- credential, media, capture, recording, and debug-output Git protections; and
- synthetic lifecycle, OpenCV-fake, reconnection, latency, privacy,
  architecture, CLI, and end-to-end tests.

## Synthetic result

The bounded end-to-end synthetic test acquires 50 frames into a four-frame
drop-oldest buffer while the consumer remains slow. The buffer retains only
sequences 46–49, reports 46 drops, never exceeds depth four, closes the source,
and lets the consumer drain and terminate cleanly. This validates control flow
and bounded memory only; it does not validate a physical camera or pig stream.

## Roadmap boundary

Phase 5 is in progress through Phase 5.1. Pig-specific tracking has not been
implemented, and Phase 5.2 has not started. Prerecorded files remain local
development and validation tools rather than the production input model.
