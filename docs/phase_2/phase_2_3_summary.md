# Phase 2.3 Summary — Generic Pipeline Integration

## Subphase objective

Phase 2.3 connects the approved Phase 1 generic counter to the Phase 2.2
contracts through concrete adapters and one minimal synchronous pipeline. It
completes the architecture phase without starting pig-specific Phase 3 work.

## Implementation delivered

* `OpenCVVideoSource` for validated local-file decoding into packed RGB `Frame`
  values
* `UltralyticsDetector` for one generic class-filtered inference per frame
* `UltralyticsTracker` using external `Detection` values with the current
  Ultralytics ByteTrack API
* immutable `PipelineFrameResult` and `PipelineRunSummary` models
* `GenericCountingPipeline` for synchronous contract orchestration
* bottom-center conversion from `Track` to the existing counting `Point`
* tracker-state TTL cleanup that preserves counted tracker IDs
* annotated-video output behind an infrastructure-facing callback
* unchanged JSONL event schema behind an event callback
* backward-compatible CLI composition through adapters and pipeline
* architecture checks covering framework-independent pipeline boundaries

## Counting compatibility

`DirectionalLineCounter` remains unchanged and is the only component that
evaluates finite-segment intersections, direction, epsilon behavior, reverse
movement, unique positive IDs, and repeated crossings. The pipeline does not
duplicate geometry or increment counts.

## Validation evidence

The Phase 2.3 test suite covers:

* missing, invalid, and synthetic OpenCV video input
* sequential indexes, timestamp progression, RGB byte length, source end, and
  idempotent source closure
* detector conversion, class/confidence filtering, immutable output, and
  private framework results
* tracker ID/bounding-box conversion, immutable output, external detection
  input, and state reuse
* positive, reverse, repeated, two-tracker, outside-segment, and near-line
  pipeline behavior
* zero detections/tracks, source end, frame limits, callbacks, summaries,
  source cleanup, and tracker TTL behavior
* CLI argument compatibility, validation, composition, and event fields
* a bounded synthetic infrastructure smoke test that decodes input, processes
  fake detections/tracks, writes annotated video, and writes valid JSONL

The completed Phase 2.3 suite contains 130 passing tests with no failures or
skips. Exact validation commands are also recorded in the implementation
completion report and repository history.

## Smoke-test status

The synthetic infrastructure smoke test executed successfully. It validates
video conversion, synchronous control flow, annotation/output writing, event
serialization, and resource cleanup without model inference.

No suitable legal local real-world sample video was present during this task,
so a bounded real-model people/vehicle smoke test was not executed. No media or
model was downloaded for that purpose. This phase does not establish generic
detection accuracy or pig-counting validity.

## Known limitations

* packed-RGB `Frame` conversion introduces array and color-conversion overhead
* ByteTrack IDs remain vulnerable to switches, loss, and fragmentation
* no pig-specific data, detector, or tracker validation exists
* no sessions, SQLite, UI, analytics, or ground-truth evaluation exists
* real-model integration remains untested against a local authorized sample in
  this task

## Phase 2 completion status

Phase 2.1 established the architecture foundation. Phase 2.2 established the
contracts. Phase 2.3 now supplies adapters and generic pipeline integration.

Current roadmap status: Phase 2 completed — architecture foundation, contracts, adapters, and generic pipeline integration implemented; Phase 3 not started.
