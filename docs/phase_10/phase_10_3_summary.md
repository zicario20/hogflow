# Phase 10.3 — Summary

## Status

Validation infrastructure is implemented. Empirical real-detector validation
is blocked because no compatible local pig-detection model was available.

> REAL DETECTOR VALIDATION COULD NOT BE COMPLETED

## Delivered

- strict exact-file authorization for three local ignored videos;
- bounded metadata inspection and Phase 3 sidecar recovery;
- approved-root, ignored/untracked, compatible-format model gate;
- immutable path-free evidence values, diagnostics, calibration candidates,
  per-video results, and aggregate report;
- deterministic per-video calibration plans that reuse Phase 6 and never make
  an automatic recommendation;
- fixed Video 1 → Video 2 → Video 3 execution order;
- model-present backend port with exact provenance validation;
- explicit ground-truth derivation rules;
- deterministic sanitized JSON and Markdown output;
- local CLI writing only under ignored validation roots;
- synthetic model-present, missing-model, failure, privacy, architecture, and
  governance tests.

## Local evidence

All three exact authorized videos existed, were ignored, were readable, and
were inspected only for bounded metadata. No review sidecars and no compatible
local model were present. Consequently no real detection, tracking, crossing,
or counting evidence was created. Video 3 remains explicitly:

> NOT VALID FOR COUNTING ACCURACY

## Scope preserved

No model was downloaded or trained. No dataset, annotation, frame, screenshot,
video derivative, model weight, database, UI, worker, queue, alternate detector,
tracking heuristic, crossing rule, or count rule was added. Phase 7 and Phase 8
behavior are unchanged. Phase 10.4 and Phase 11 were not started.

## Verification

The final focused suite passed 64 tests. The complete local regression suite
passed 985 tests with one inherited Supervision `ByteTrack` deprecation
warning. These results validate the workflow implementation, not empirical pig
detection or counting accuracy.

## Next evidence prerequisite

Provide one explicitly authorized, compatible, ignored local pig detector and
independent manual ground truth. Then execute the existing model-present
boundary first on Video 1, calibrate Video 2 independently only after structural
success, and use Video 3 solely for detection/tracking stress diagnostics.
