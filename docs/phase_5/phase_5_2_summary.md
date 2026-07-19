# Phase 5.2 — Summary

## Status

Phase 5.2 live detector integration tooling is implemented. Phase 5.1 camera
acquisition remains intact. No valid local pig-detector weights with complete
provenance were available, so real pig inference is blocked and no detector
accuracy or pig-detection claim is made. Phase 5.3 has not started.

## Delivered

* immutable framework-neutral model metadata, frame-result, scheduling,
  telemetry, shutdown, and run-summary models;
* an explicit lifecycle-aware `LiveDetector` Protocol and local preview port;
* empty, scripted, slow, and failing deterministic detectors for CI;
* bounded detector telemetry with separate camera-drop and inference-skip
  accounting;
* latest-useful-frame synchronous inference orchestration over the existing
  Phase 5.1 producer and fixed-capacity source buffer;
* every-N, target-FPS, and maximum-frame-age scheduling;
* temporary/fatal detector failure isolation and cooperative cleanup;
* an explicit-local-file Ultralytics YOLO adapter with pig-class policy,
  SHA-256 fingerprinting, optional structural provenance, output clipping, and
  no automatic model download;
* an optional ephemeral OpenCV preview adapter;
* a headless local CLI with periodic and final sanitized JSON telemetry; and
* deterministic synthetic, fake-framework, privacy, CLI, performance, and
  architecture tests.

## Validation evidence

The implementation test suite uses no real camera, model, or media. A slow
synthetic detector running behind a faster synthetic source confirms fixed
buffer capacity, observable source drops, explicit inference skips, stage
accounting, and clean shutdown. Framework-fake tests confirm box conversion,
class/confidence filtering, frame clipping, malformed-output rejection,
fingerprint stability, provenance handling, and resource release.

At completion, the full repository suite passes 401 tests. Ruff lint and
format checks, Python compilation, dependency consistency, and Git whitespace
validation also pass.

Real pig inference was not executed. A local USB-camera hardware smoke used
the deterministic empty detector only. The 60-second bounded run acquired
1,381 frames at approximately 30.02 observed camera FPS, inferred 1,353,
explicitly skipped 27, reported zero source-buffer drops and zero inference
failures, ended in stopped health, and released both camera and detector. An
immediate 15-second reopen also succeeded: it acquired 85 frames after camera
startup/warm-up, inferred 83, skipped one, reported zero source drops and
inference failures, observed approximately 30.03 camera FPS while frames were
flowing, peaked near 93.27 MiB RSS, and averaged about 59.87 percent process CPU
during the sampled run. The reopen ended stopped with both resources released.

The empty detector has effectively zero inference work, so these measurements
do not predict real-model latency, throughput, CPU, memory, or pig-detection
behavior. Preview was disabled and no frame was persisted.

## Evidence boundary

This phase validates live detector integration only. It does not validate
multi-object tracking, pig counting, line crossing, RTSP production readiness,
or detector accuracy. No tracking or counting class was added.

## Roadmap boundary

Phase 5 is in progress through Phase 5.2. Real pig inference requires a valid
local pig detector artifact and supporting evidence. Phase 5.3 has not started.
