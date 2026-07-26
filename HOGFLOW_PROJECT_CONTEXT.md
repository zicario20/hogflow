# HogFlow Project Context

## Document purpose

This document records the current technical and roadmap context for HogFlow during repository initialization.

Status labels used here:

* HYPOTHESIS: a project claim that still requires representative data and human-verified validation
* PLANNED: a capability or phase that is part of the roadmap but not yet implemented
* OPTIONAL: a capability that is explicitly secondary or conditional in the roadmap

Current repository status: Phase 8.3 synchronous multi-dock runtime
coordination implemented. Four logically active dock runtimes can retain
isolated operations, sources, Phase 8.2 services, and Phase 7 counters. This
does not implement concurrent camera ingestion, persistence, API, or UI.

## Project identity

Project name: HogFlow

HogFlow is an independent computer vision and data analytics research prototype for evaluating automated livestock counting in constrained passage environments.

The intended use case is a narrow alley in which pigs move toward a weighing area. The system concept is to detect pigs, track them across frames, observe directional crossings of a configured virtual line, and estimate unique pig count at the session level.

HogFlow is currently a research prototype / MVP.

It is not a production system, an operational deployment, or a completed pilot.

## Project purpose

The project exists to investigate whether an automated counting pipeline could reduce continuous manual counting effort in a constrained livestock-flow environment.

This purpose is investigatory. It does not establish operational viability, validated accuracy, labor savings, financial savings, commercial value, or production readiness.

## Central hypothesis

HYPOTHESIS:

A computer vision pipeline combining pig detection, multi-object tracking, and directional virtual-line crossing may be able to estimate the number of pigs moving through a constrained alley with sufficiently low count error to reduce continuous manual counting effort.

This hypothesis must be tested with representative data and human-verified ground truth.

## Conceptual pipeline

PLANNED conceptual flow:

VIDEO
→ DETECTOR
→ DETECTIONS
→ TRACKER
→ TRACKER IDS
→ DIRECTIONAL LINE CROSSING
→ SESSION COUNTER
→ EVENT STORAGE
→ OPERATOR UI
→ EVALUATION / ANALYTICS

## Detection, tracking, and generic integration

IMPLEMENTED contract layer in Phase 2.2:

* `Frame`, `BoundingBox`, `Detection`, and `Track` provide immutable framework-neutral communication models.
* `Detector.predict(frame)` accepts one `Frame` and returns a sequence of `Detection` objects.
* `Tracker.update(frame, detections)` accepts one `Frame` and its detections, then returns a sequence of `Track` objects.
* `VideoSource.read()` returns the next `Frame` or `None` at end of input; `close()` defines explicit resource release.
* The contract layer does not import computer-vision frameworks.

IMPLEMENTED generic integration in Phase 2.3:

* `OpenCVVideoSource` converts local OpenCV BGR frames into immutable packed-RGB `Frame` values.
* `UltralyticsDetector` performs one generic class-filtered inference and returns immutable `Detection` tuples.
* `UltralyticsTracker` supplies those external detections directly to ByteTrack and returns immutable `Track` tuples without duplicate inference.
* `GenericCountingPipeline` synchronously coordinates the approved contracts and delegates all count decisions to the Phase 1 `DirectionalLineCounter`.
* The existing generic CLI composes adapters, pipeline, annotated output, and unchanged JSONL crossing events.
* Counting does not directly depend on a specific detector or tracker implementation.

IMPLEMENTED Phase 3 data-acquisition infrastructure:

* Local `data/raw`, `data/interim`, and `data/processed` workspaces are protected from media commits.
* Immutable inventory models and deterministic video discovery remain independent from CV frameworks.
* OpenCV metadata inspection uses bounded samples and records readability, dimensions, FPS, frame count, duration, codec, decode problems, and changing dimensions.
* Feature-based global-motion estimates provide conservative camera-stability review labels.
* Explicit authorization and manual scene-review sidecars control candidate labeling.
* Counting candidacy requires human confirmation of a static camera, clear passage, predominant direction, and usable virtual-line location; metadata alone cannot grant it.
* Local inventory output is available in JSON, CSV, and Markdown without extracting frames or thumbnails.

IN PROGRESS Phase 3 evidence work:

* Real authorized pig-video acquisition and manual review may continue outside Git.
* No real pig dataset is bundled or claimed complete.

IMPLEMENTED Phase 4.1 foundations:

* GitHub Actions runs source-only lint, formatting, test, compilation, and dependency checks on pushes and pull requests involving `main`.
* Immutable framework-neutral detection-evaluation models represent explicit pixel or normalized boxes, ground truth, predictions, frames, one-to-one matches, aggregate results, and dataset summaries.
* Deterministic utilities calculate area, intersection, union, IoU, true positives, false positives, false negatives, precision, recall, and F1 with explicit zero-denominator behavior.
* Confidence-first matching uses stable ID tie-breaks and never matches one prediction or ground-truth box more than once.
* Metadata-only dataset selection consumes local Phase 3 inventory JSON without decoding videos and writes an ignored local plan containing opaque clip IDs rather than filenames or paths.
* Local annotation, model, inference-run, and evaluation workspaces are protected from Git; only approved `.gitkeep` placeholders are tracked.

NOT IMPLEMENTED in Phase 4.1:

* real pig annotation
* frame extraction
* a finalized annotation format
* pig detector inference, training, fine-tuning, or validation
* mAP
* tracking evaluation
* counting evaluation

IMPLEMENTED Phase 4.2 tooling:

* Finalized local annotation policy for the single `pig` class and explicit
  `annotated`, `verified_empty`, `needs_manual_review`, and `excluded` states.
* Framework-neutral normalized pig boxes and deterministic YOLO text
  serialization with no detector-framework dependency.
* Seed-controlled source-video-level splitting that never distributes one
  source across train, validation, and test.
* Preparation-only plans and explicit warnings when source diversity is below
  the configured minimum.
* Deterministic fixed-interval, target-count, and bounded-uniform frame planning
  from metadata without decoding video.
* Explicit ignored local source maps separated from sanitized split, frame,
  extraction, manifest, and validation outputs.
* Optional local OpenCV extraction using opaque names, bounded timestamp seeks,
  idempotent writes, and no automatic annotations.
* Sanitized annotation manifests plus JSON, CSV, and Markdown checks for image,
  label, status, checksum, dimension, duplicate, and source-split consistency.

NOT IMPLEMENTED in Phase 4.2:

* completed real pig annotation
* a downloaded, trained, fine-tuned, or validated pig detector
* detector inference or accuracy measurement
* mAP
* tracking or counting evaluation
* Phase 4.3

IMPLEMENTED Phase 4.3 training pipeline:

* Immutable framework-neutral training configuration, result, provenance, and
  failure-analysis models.
* One small `DetectorTrainer` contract for replaceable detector-training
  implementations.
* A mandatory pre-training gate that reuses Phase 4.2 annotation, image,
  label, class-map, and source-split validation.
* Deterministic dataset fingerprinting without source filenames or paths.
* One isolated `YOLOBaselineTrainer` with local train, validate, resume,
  checkpoint export, and framework-result conversion.
* Reuse of Phase 4.1 deterministic precision, recall, F1, and IoU evaluation.
* Explicit separation of framework metrics from HogFlow evaluation metrics.
* Local-only reproducibility metadata and detector failure reports.
* Synthetic contract, adapter, orchestration, privacy, and smoke tests without
  model downloads or real data.

NOT EMPIRICALLY COMPLETED in Phase 4.3:

* completed real pig annotation
* a real pig-detector training run
* a validated pig checkpoint or detector-accuracy result
* pig-specific tracking or counting evaluation
* Phase 5

PLANNED pig-specific evidence work:

* Real annotation, pig-detector training/validation, and later pig-specific
  tracker validation still require authorized representative data. The
  replaceable Phase 4.3 training implementation does not supply that evidence.

Candidate detector families mentioned in project guidance include YOLO, RF-DETR, or another compatible detector. The detector implementation must remain replaceable.

IMPLEMENTED Phase 5.1 live acquisition foundation:

* A framework-neutral `CameraSource` contract with explicit frame,
  temporary-unavailable, EOF, interruption, and stopped read outcomes.
* Immutable stream identities, timestamps, RGB payloads, `FramePacket` values,
  health snapshots, and statistics.
* Lifecycle-scoped monotonically increasing sequence numbers ordered by a
  monotonic clock rather than wall time.
* Thread-safe fixed-capacity buffering with deterministic `drop_oldest` and
  `drop_newest` policies and observable sequence gaps.
* A synchronous acquisition runner with optional producer thread, graceful
  stop, deterministic reconnect backoff, and bounded diagnostics.
* Runtime-only protected RTSP/file locators whose representations, errors,
  logs, health, and statistics expose only opaque source identity.
* Isolated OpenCV adapters for USB/RTSP acquisition and one-pass local
  development files, plus a deterministic synthetic source for CI.
* A headless diagnostic CLI that saves, uploads, previews, detects, tracks, and
  counts nothing.

NOT EMPIRICALLY COMPLETED in Phase 5.1:

* validation on additional USB camera models or non-MSMF backends
* real RTSP compatibility or interruption testing
* a live pig-camera stream
* pig-detector execution
* pig-specific tracking or counting

IMPLEMENTED Phase 5.2 live detector integration:

* A framework-neutral lifecycle-aware `LiveDetector` contract that consumes
  immutable Phase 5.1 `FramePacket` values and returns immutable
  `FrameDetections` tied to exact source sequence IDs.
* Sanitized model metadata with local artifact filename, SHA-256 fingerprint,
  class mapping, and optional structural provenance fields.
* Latest-useful-frame inference scheduling over the fixed Phase 5.1 source
  buffer, without a second unbounded inference queue.
* Configurable every-N, target-FPS, and maximum-frame-age scheduling with
  explicit inference-skip accounting.
* Separate counters for source-buffer drops, inference skips, and inference
  failures, plus bounded latency percentiles and frame-age telemetry.
* Deterministic empty, scripted, slow, and failing detectors for tests and
  local infrastructure diagnostics.
* One isolated Ultralytics live-inference adapter that requires an explicit
  existing local artifact, validates the pig class policy, and never downloads
  model weights.
* An optional local-only OpenCV preview and a sanitized JSON diagnostic CLI.
* Synthetic end-to-end, scheduling, failure, adapter, privacy, CLI, and
  architecture validation with no camera, GPU, internet, or model requirement.
* One local laptop USB-webcam control-flow smoke test with the deterministic
  empty detector; no frame was persisted and no pig model was involved.

NOT EMPIRICALLY COMPLETED in Phase 5.2:

* real pig inference, because no validated local pig-detector artifact exists
* pig-detector accuracy, latency, or throughput validation
* a Phase 5.2 physical-camera plus real-model validation
* RTSP production readiness
* multi-object tracking, line crossing, or pig counting
* Phase 5.3

IMPLEMENTED Phase 5.3 live multi-object tracking integration:

* A framework-neutral lifecycle-aware `LiveTracker` contract that consumes
  immutable per-frame detection requests and returns immutable tracking
  results tied to exact stream IDs and source frame sequences.
* Temporary track identities expressed through the canonical `Track` model;
  IDs are lifecycle-scoped and are not permanent animal identities or counts.
* One tracker instance per stream lifecycle, cross-stream rejection, explicit
  reset, idempotent close, and reconnect-triggered state reset.
* Immutable ByteTrack configuration, sanitized provenance, bounded tracking
  telemetry, health/error categories, snapshots, and run summaries.
* Deterministic empty, scripted, IoU, slow, and failing tracker doubles for CI
  and local control-flow diagnostics.
* An isolated Supervision 0.29.1 ByteTrack adapter using the installed
  `update_with_detections` and `reset` APIs without leaking NumPy or
  Supervision objects.
* Serial tracking composition after successful Phase 5.2 detection. The fixed
  Phase 5.1 source buffer remains the only queue, so tracking adds no unbounded
  backlog.
* Optional ephemeral OpenCV tracking preview and structured CLI telemetry for
  temporary IDs, visible-track volume, failures, resets, and latency.
* Synthetic lifecycle, identity, frame-gap, multi-stream, adapter, preview,
  CLI, privacy, and architecture tests.
* One local built-in USB-webcam integration validation with synthetic moving
  boxes and the installed ByteTrack adapter: a long run and immediate reopen
  both closed resources cleanly and saved no frames.

NOT EMPIRICALLY COMPLETED in Phase 5.3:

* real pig tracking, because no validated local pig-detector artifact exists
* representative occlusion, dense-group, ID-switch, or fragmentation evaluation
* a claim that temporary tracker IDs correspond to unique biological animals
* RTSP tracking validation or production readiness

IMPLEMENTED Phase 5.4 live virtual-line crossing events:

* Immutable normalized points and one oriented finite line segment with
  explicit `NEGATIVE`, `ON_LINE`, and `POSITIVE` classification.
* Deterministic `BOTTOM_CENTER` and optional `CENTER` representative track
  anchors independent from frame resolution.
* Immutable lifecycle-qualified events in neutral
  `NEGATIVE_TO_POSITIVE` and `POSITIVE_TO_NEGATIVE` directions.
* Finite-segment validation between two real stable observations, explicit
  normalized epsilon, and no fabricated intermediate frame or timestamp.
* Bounded per-track stable-side state, update-based absence cleanup,
  cross-stream rejection, stale-sequence rejection, and reset/reconnect state
  clearing.
* Serial optional `LiveCrossingPipeline` composition after successful tracking,
  with no additional queue and unchanged Phase 5.3 behavior when disabled.
* Bounded diagnostic event telemetry, optional ephemeral OpenCV preview, and
  structured CLI activation using normalized endpoints.
* Synthetic geometry, lifecycle, pipeline, preview, CLI, privacy, architecture,
  and regression tests.

NOT EMPIRICALLY COMPLETED in Phase 5.4:

* representative pig crossing validation or calibrated line placement
* event accuracy, count accuracy, ID-switch, fragmentation, or occlusion claims
* accumulated counting, unique-ID deduplication, operational direction,
  sessions, storage, or Phase 7

IMPLEMENTED Phase 6 virtual-line position evaluation infrastructure:

* Immutable, fingerprinted line candidates and non-empty canonical evaluation
  plans with explicit ranking policy.
* Immutable tracking replays that preserve source, aware timestamps, strict
  sequence order, real gaps, lifecycle provenance, and optional independent
  crossing-event ground truth.
* Serial deterministic replay through one isolated
  `VirtualLineCrossingDetector` lifecycle per candidate, reusing Phase 5.4
  finite-segment geometry without OpenCV, Supervision, camera, or model
  dependencies.
* Descriptive event, direction, track, gap, endpoint-proximity, duration, and
  latency metrics that are not labeled as pig counts.
* Optional deterministic one-to-one crossing-event matching with frame-window
  and direction policy, plus TP/FP/FN, precision, recall, F1, frame offsets,
  direction errors, and event-total error.
* Explicit ranking methods. The default without ground truth is
  `NO_AUTOMATIC_RECOMMENDATION` and yields no recommended candidate.
* Strict versioned path-free JSON replay/plan/report serialization, atomic
  report output, an offline CLI, bounded evaluation telemetry, and synthetic
  clean-pass, finite-extension, and jitter/gap fixtures.

NOT EMPIRICALLY COMPLETED in Phase 6:

* evaluation using representative authorized pig video and valid pig tracking
* human-verified representative crossing-event ground truth
* a validated or optimal virtual-line position for pigs
* pig-count accuracy, operational counting, deduplication, or Phase 7

IMPLEMENTED Phase 7 reverse and duplicate counting infrastructure:

* Immutable explicit positive-direction configuration tied to the exact Phase
  5.4 crossing fingerprint.
* `TemporaryTrackIdentity` qualified by source, crossing lifecycle, and numeric
  tracker ID; separate Phase 7 counting lifecycle provenance.
* Atomic `LifecycleDirectionalCounter` frame processing with first-positive
  increment, duplicate-positive suppression, and reverse decisions without
  decrement.
* Counted identities retained for the lifecycle and bounded by a fail-safe
  capacity rather than silent eviction.
* Strict source, lifecycle, stale-sequence, line, frame, and crossing-provenance
  validation.
* Reconnect/reset isolation that clears total and counted identities before the
  next crossing lifecycle.
* Serial optional `LiveCountingPipeline` composition with no additional queue,
  disabled-by-default CLI activation, bounded telemetry, and optional ephemeral
  preview.
* Synthetic policy, atomicity, reconnect, lifecycle, CLI, preview, privacy,
  architecture, and regression tests.

NOT EMPIRICALLY COMPLETED in Phase 7:

* pig-specific duplicate-counting or reverse-movement validation
* biological re-identification or identity continuity across reconnect
* representative ID-switch, fragmentation, dense-group, or occlusion analysis
* session totals, persistence, UI, ground-truth count accuracy, or Phase 8

IMPLEMENTED Phase 8.1 multi-dock unloading domain infrastructure:

* Stable `DockId` values for exactly four physical docks and stable
  `REGULAR`, `OPG`, `P12`, and `NAE` pig types.
* Immutable ordered `UnloadingSession` values and a copy-on-write
  `TruckOperation` aggregate with explicit planned, active, completed, and
  cancelled transitions.
* Variable session quantities, mixed-type trucks, one active session per
  operation, strict sequence order, and terminal-state protection.
* Completed-session truck totals and deterministic totals for all four pig
  types, including zero values.
* An immutable four-dock registry enforcing one non-terminal truck operation
  per dock while preserving independent simultaneous dock state.
* Explicit domain errors and atomic failure semantics independent from camera,
  Phase 7 counting, persistence, networking, and UI.

NOT IMPLEMENTED in Phase 8.1:

* mapping an unloading session to a Phase 7 counting lifecycle
* automatic transfer or finalization of live counts
* persistence, SQLite, API, UI, networking, concurrency, or hardware control
* automatic creation of three sessions or splitting around 60 pigs
* Phase 8.2 or broader multi-dock orchestration

IMPLEMENTED Phase 8.2 unloading-session/counting integration:

* A pure `hogflow.sessions` application service consumes immutable Phase 8.1
  operations and the public Phase 7 `LiveDirectionalCounter` protocol.
* One active unloading session owns one source, crossing lifecycle, and
  counting lifecycle binding with immutable provenance.
* Sequential sessions receive fresh Phase 7 lifecycle generations; counted
  identities, current totals, and frame-order state do not leak.
* Phase 7 remains solely responsible for positive direction, duplicate
  suppression, reverse decisions, counted identities, capacity, and stale
  requests.
* Completion closes Phase 7 and transfers the last validated lifecycle total
  exactly once into the immutable completed session.
* Cancellation closes Phase 7, discards unfinished counting, and preserves
  previously completed sessions.
* Prospective domain transitions are committed only after lifecycle start or
  close succeeds.
* Reused lifecycle IDs and crossing results outside the active source,
  lifecycle, or timestamp boundary are rejected.

NOT IMPLEMENTED in Phase 8.2:

* simultaneous coordination across docks
* camera or live-pipeline orchestration
* aggregation across reconnect lifecycles inside one physical session
* persistence, SQLite, API, UI, networking, threading, or async execution
* automatic session creation, scheduling, or Phase 8.3

IMPLEMENTED Phase 8.3 multi-dock runtime coordination:

* A synchronous `MultiDockRuntimeCoordinator` manages exactly the four typed
  docks through one private runtime record per current dock.
* Every occupied runtime owns one explicit source, injected Phase 7 counter,
  and Phase 8.2 service after operation startup.
* Commands and crossing results route by explicit `DockId`; no source scanning
  or ownership guessing occurs.
* Active sources and active/finalized crossing/counting lifecycle IDs are
  validated across current dock records.
* A Phase 8.2 pre-commit validator closes a prospective counter and preserves
  immutable session state when a global lifecycle collision is found.
* Live session totals remain separate from completed-session truck and
  aggregate pig-type totals.
* Terminal current records remain readable and replaceable without pretending
  to be historical persistence.
* Shutdown attempts all docks, cancels active sessions through Phase 8.2,
  discards unfinished totals, aggregates close failures, and never completes
  or cancels a truck automatically.
* Dock snapshots are immutable and always ordered Dock 1 through Dock 4.

NOT IMPLEMENTED in Phase 8.3:

* camera acquisition or four concurrent camera streams
* thread safety, async execution, workers, queues, or scheduling
* persistence/history, SQLite, API, networking, or UI
* automatic truck/session generation or hardware control
* Phase 9 or Phase 10

## Unique tracker counting concept

IMPLEMENTED per-lifecycle policy and session transfer:

* HogFlow counts unique tracked individuals, not per-frame detections.
* A pig seen across many frames must not increment the count once per frame.
* Phase 7 maintains lifecycle-qualified counted identities for one crossing
  lifecycle.
* Phase 8.2 may finalize one Phase 7 total as one unloading-session
  `actual_count`; that transfer does not make it a validated biological count.

## Directional crossing and reverse movement rules

IMPLEMENTED Phase 7 lifecycle rules:

* Only crossings in an explicitly configured positive geometric direction may
  increment the lifecycle total.
* Reverse-direction crossings may be recorded as events.
* Reverse crossings must not automatically increment the positive count.
* Repeated positive crossings from the same lifecycle-qualified tracker
  identity do not increment again.
* Reverse events do not decrement or remove counted identities.

Tracking uncertainty remains a measured risk rather than something to hide. Relevant risks include ID switches, lost tracks, re-identification, occlusion, and fragmented tracks.

When uncertainty cannot be resolved by a validated rule, the project preference is to create a review event instead of applying undocumented heuristics.

## Multi-dock unloading workflow and session model

IMPLEMENTED Phase 8.1 pure domain, Phase 8.2 application integration, and
Phase 8.3 synchronous runtime coordination:

The operational reference commonly uses three gate sections and approximately
60 pigs per section, but neither value is a domain rule. Phase 8.1 models
exactly four docks, each with one independent truck operation containing a
variable number of ordered sessions.

Conceptual session flow:

IDLE
→ SELECT SECTION
→ START SESSION
→ COUNTING
→ END SESSION
→ REVIEW RESULT
→ CONFIRM OR FLAG FOR REVIEW
→ COMPLETED

Session constraints:

* Only one session may be active within one truck operation.
* Different docks may operate independently at the same time.
* Each session has one explicit pig type; one truck may contain several types.
* Sessions are added only while an operation is planned.
* The operator will eventually start and end sessions through later layers.
* Phase 8.2 maps each started session to one isolated Phase 7 lifecycle.
* Automatic gate, door, or section detection remains out of scope.

Each implemented Phase 8.1 session supports:

* session ID
* positive sequence number
* pig type
* start time
* end time
* optional expected count
* domain-assigned actual count
* status

Phase 8.2 starts that session and its counter lifecycle together, delegates
crossing results to Phase 7, and transfers the final positive-direction total
only when completion closes the lifecycle successfully. Cancellation closes
the lifecycle without transferring its unfinished total.
Phase 8.3 composes one such service per occupied dock, preserves cross-dock
source/lifecycle isolation, and derives read-only combined finalized totals.
Calls remain synchronous and must be serialized by the caller.

## Operator MVP User Interface

PLANNED in Phase 9:

The Operator MVP UI is intended to become the normal operator interface once it exists, while terminal logs remain available for development and diagnostics.

Minimum planned UI information and controls:

* CURRENT SECTION
* SESSION STATUS
* LIVE / PROCESSED VIDEO VIEW
* CURRENT AI COUNT
* START SESSION
* END SESSION
* CONFIRM SESSION
* FLAG FOR REVIEW
* LAST COUNTING EVENT
* REVIEW RECOMMENDED STATUS

The UI must consume project modules and must not duplicate counting logic or directly increment the AI count.

## SQLite conceptual data model

PLANNED in Phase 10:

SQLite is the MVP storage target.

Conceptual entities:

### loads

* id
* created_at
* total_count
* status

### sessions

* id
* load_id
* section_number
* started_at
* ended_at
* ai_count
* ground_truth_count
* status

### count_events

* id
* session_id
* tracker_id
* timestamp
* direction
* confidence

### review_events

* id
* session_id
* timestamp
* reason
* frame_reference

Ground truth and AI output must remain distinguishable. AI counts must not be silently overwritten to match ground truth.

## Evaluation priorities

PLANNED evaluation priority:

The primary KPI is count error, not raw object-detection performance alone.

Counting-system metrics should include:

* Exact Count Rate
* Mean Absolute Count Error
* Count Error Rate
* Undercount Rate
* Overcount Rate

Conceptual formulas:

* Absolute Count Error = `abs(AI Count - Ground Truth)`
* Count Error Rate = `abs(AI Count - Ground Truth) / Ground Truth`

Detection precision and recall are diagnostic metrics. They are not sufficient evidence that HogFlow counts correctly as a counting system.

## Failure analysis priorities

PLANNED failure categories to preserve and measure:

* pig occlusion
* multiple pigs crossing together
* false detections
* missed detections
* tracker ID switches
* lost tracks
* re-identification
* duplicate counting
* reverse movement
* dense animal groups
* poor camera angle
* poor lighting
* camera vibration
* domain mismatch
* non-pig objects crossing the line

Failure cases should be documented, not hidden or manually filtered out to improve reported results.

## Data governance restrictions

Development must use only public, synthetic, or explicitly authorized data.

Do not assume access to:

* employer videos
* facility cameras
* proprietary systems
* company source code
* internal operational documents
* confidential count records
* private network infrastructure

Do not place confidential employer information in source code, tests, fixtures, documentation, screenshots, sample databases, or Git history.

Real-world deployment, recording, camera installation, or facility-data use requires explicit authorization.

## Current roadmap

The roadmap currently spans Phase 0 through Phase 16.

| Phase | Description |
| --- | --- |
| Phase 0 | Define problem and map process. |
| Phase 1 | Build generic line-crossing counter using public people or vehicle video. |
| Phase 2 | Create HogFlow software architecture. |
| Phase 3 | Acquire legal or public pig video data. |
| Phase 4 | Build pig detection baseline. |
| Phase 5 | Add multi-object tracking. |
| Phase 6 | Implement and evaluate virtual counting line positions. |
| Phase 7 | Handle reverse movement and duplicate counting. |
| Phase 8 | Build three-section session manager. |
| Phase 9 | Build Operator MVP User Interface. |
| Phase 10 | Store sessions and events in SQLite. |
| Phase 11 | Evaluate HogFlow against human-verified ground truth. |
| Phase 12 | Build error analysis and analytics dashboard. |
| Phase 13 | Create failure review system and review clips. |
| Phase 14 | Optionally evaluate group-weight consistency as a secondary validation signal. |
| Phase 15 | Document results as a portfolio case study. |
| Phase 16 | Prepare an authorized pilot-readiness plan and define validation gates. |

Phase 2 is executed through audited subphases:

* Phase 2.1 — architecture foundation — completed
* Phase 2.2 — interfaces and contracts — completed
* Phase 2.3 — existing Phase 1 integration with the approved contracts — completed

Phase 2.1, Phase 2.2, and Phase 2.3 are implemented. This subphase structure does not renumber or change the official Phase 0 through Phase 16 roadmap.

Phase 3 inventory infrastructure is implemented. Real authorized dataset acquisition and review may still be ongoing, so this status does not claim that a representative pig dataset has been completed or validated.

Phase 4 implementation is complete through Phase 4.3. The local replaceable
training pipeline is operational, but real annotation may still be incomplete
and no real detector-performance result was produced during implementation.
Phase 5 is implemented through the authorized Phase 5.4 scope. The live acquisition foundation has
synthetic, fake-backend, and one real laptop USB-webcam validation record. Live
detector integration has deterministic synthetic/fake-framework evidence and
one USB-webcam-to-empty-detector control-flow result, but no valid local
pig-detector artifact was available for real pig inference.
Live temporary-ID tracking has deterministic synthetic and installed-adapter
evidence, but no representative pig-detection input or real pig-tracking
accuracy evidence. Event-only virtual-line crossing has deterministic synthetic
evidence but no representative line calibration or event-accuracy result.
Phase 6 offline evaluation infrastructure has deterministic synthetic evidence,
but representative pig replay, human crossing-event ground truth, and line
calibration remain pending. Phase 7 lifecycle counting has deterministic
synthetic evidence only; representative reverse/duplicate validation and RTSP
production validation remain pending. Phase 8.1 pure unloading-domain
infrastructure, Phase 8.2 sequential session/counting integration, and Phase
8.3 synchronous multi-dock coordination are implemented with synthetic
evidence. Concurrent camera ingestion has not started.

## Pilot readiness phase

PLANNED in Phase 16:

Pilot readiness means preparation for a possible future authorized pilot. It does not mean a pilot has already happened.

Pilot-readiness documentation is expected to address:

* pilot objective
* pilot scope
* representative environment requirements
* camera placement assumptions
* hardware and compute requirements
* data collection plan
* human-verified ground-truth procedure
* pilot session procedure
* count-error acceptance criteria
* failure and review procedure
* privacy and data governance
* operational safety constraints
* manual counting continuity
* rollback procedure
* pilot success criteria
* pilot failure criteria
* post-pilot review plan

HogFlow remains a research prototype until representative validation evidence supports a different documented status.

## Current implementation status

IMPLEMENTED at repository level:

* documentation foundation
* Phase 0 problem definition and process mapping
* Phase 1 generic finite-segment directional line-crossing core
* Phase 1 generic detector/tracker/video proof-of-concept integration
* Phase 2.1 package foundation
* shared error hierarchy
* centralized logging configuration
* foundational immutable settings
* documented dependency rules
* architecture-boundary tests
* framework-independent immutable contract models
* Detector, Tracker, and VideoSource Protocols
* contract API, immutability, import-side-effect, and framework-independence tests
* Phase 2.3 framework adapters for local video, generic Ultralytics detection, and ByteTrack
* synchronous generic pipeline orchestration
* CLI composition through the approved contracts and adapters
* synthetic pipeline and video-output integration tests
* Phase 3 local data-workspace and Git media safeguards
* immutable video inventory, review, manifest, and summary models
* deterministic supported-video discovery
* bounded OpenCV metadata and decode validation
* conservative feature-based camera-motion labeling
* authorization/manual-review sidecar and optional clip-manifest validation
* JSON, CSV, and Markdown dataset inventory output
* synthetic Phase 3 video-infrastructure tests
* source-only GitHub Actions continuous integration
* Phase 4.1 immutable detection-evaluation models
* deterministic bounding-box geometry and one-to-one basic detection metrics
* privacy-preserving metadata-only detection dataset selection
* protected local annotation/model/run/evaluation workspaces
* synthetic Phase 4.1 evaluation, selection, CI, architecture, and Git-hygiene tests
* Phase 4.2 finalized annotation policy and normalized pig annotation models
* deterministic YOLO label parsing and serialization
* source-video split and metadata-only frame-selection planning
* local frame extraction with opaque output names and sanitized reports
* annotation manifest construction and local dataset validation
* synthetic Phase 4.2 preparation, privacy, architecture, and end-to-end tests
* Phase 4.3 framework-neutral detector-training contract and immutable models
* validated local prepared-dataset training gate and deterministic fingerprint
* isolated Ultralytics YOLO baseline trainer with resume and checkpoint export
* reuse of Phase 4.1 metrics with separate framework metric reporting
* local reproducibility metadata and detection failure-analysis output
* synthetic Phase 4.3 training adapter and orchestration tests
* Phase 5.1 framework-neutral continuous camera models and `CameraSource` contract
* protected runtime source locators and sanitized camera identity
* isolated OpenCV USB/RTSP and development-file stream adapters
* deterministic scripted synthetic camera source
* bounded thread-safe frame buffering and observable real-time drop policies
* synchronous live-stream lifecycle runner, reconnect policy, health, and statistics
* headless no-persistence camera diagnostic CLI
* synthetic Phase 5.1 lifecycle, latency, privacy, adapter, and architecture tests
* Phase 5.2 immutable live inference, model provenance, telemetry, and run-summary models
* lifecycle-aware framework-neutral `LiveDetector` and local preview contracts
* latest-useful-frame detector orchestration over the bounded Phase 5.1 stream
* explicit source-drop, inference-skip, and detector-failure accounting
* deterministic empty, scripted, slow, and failing live detector doubles
* isolated explicit-local-file Ultralytics live detector adapter
* optional ephemeral OpenCV detection preview and sanitized JSON CLI
* synthetic Phase 5.2 scheduling, latency, privacy, adapter, and architecture tests
* one local Phase 5.2 USB-webcam smoke test using the empty detector only
* Phase 5.3 framework-neutral live tracker lifecycle and immutable results
* one-stream-per-tracker state isolation, explicit reset, and cleanup
* deterministic empty, scripted, IoU, slow, and failing live tracker doubles
* isolated Supervision 0.29.1 ByteTrack adapter over structured detections
* serial detector-to-tracker orchestration without a second queue
* bounded tracking health, failure, visible-track, reset, and latency telemetry
* optional ephemeral OpenCV temporary-ID preview and extended structured CLI
* synthetic Phase 5.3 identity, lifecycle, adapter, pipeline, privacy, and architecture tests
* normalized finite-line models and lifecycle-qualified live crossing events
* bounded crossing state, reset/reconnect alignment, telemetry, preview, and CLI
* synthetic Phase 5.4 geometry, lifecycle, pipeline, privacy, and architecture tests
* immutable Phase 6 line candidates, evaluation plans, tracking replays, and reports
* serial isolated reuse of Phase 5.4 crossing geometry for each candidate
* descriptive gap/endpoint metrics and optional deterministic event-ground-truth matching
* explicit evidence-aware ranking with no default recommendation without ground truth
* strict sanitized JSON replay/report IO and offline technical CLI
* synthetic Phase 6 clean-pass, finite-extension, jitter/gap, matching, ranking, privacy, and architecture tests
* immutable Phase 7 configuration, temporary identity, decision, result, snapshot, and summary models
* atomic lifecycle-aware first-positive, duplicate-positive, and reverse policy
* bounded counted-identity capacity and reconnect-isolated counting lifecycle
* serial Phase 7 live composition, optional preview, telemetry, and technical CLI
* synthetic Phase 7 policy, atomicity, reconnect, privacy, architecture, and regression tests
* immutable Phase 8.1 dock, pig-type, session, total, and operation models
* copy-on-write truck-operation transitions with variable ordered sessions
* one-active-session, terminal-state, timestamp, and completed-total rules
* immutable four-dock occupancy registry with independent current operations
* synthetic Phase 8.1 lifecycle, mixed-truck, atomicity, isolation, and architecture tests
* immutable Phase 8.2 session/counting lifecycle and finalization provenance
* one-operation sequential `UnloadingSessionCountingService`
* exactly-once final count transfer and cancellation discard behavior
* fresh Phase 7 current gauges and identity state for sequential sessions
* synthetic Phase 8.2 lifecycle, transfer, reuse, cancellation, failure, and architecture tests
* synchronous Phase 8.3 four-dock runtime coordinator and immutable snapshots
* one injected Phase 7 counter and Phase 8.2 service per current dock runtime
* cross-dock source/lifecycle uniqueness, routing, isolation, and terminal replacement
* separated live and finalized totals with deterministic Dock 1-4 aggregate views
* Phase 8.3 shutdown cancellation, partial-close reporting, and architecture tests

Not yet implemented:

* representative pig line-position evaluation and calibrated line selection
* representative pig reverse-movement and duplicate-counting validation
* Phase 9 through Phase 16
* a completed or validated real authorized pig-video dataset
* completed real pig annotations
* a real trained and validated pig-specific detector checkpoint
* pig-specific tracking evaluation
* true concurrent camera ingestion for several docks
* receiving batches or groups
* exception-event management
* SQLite event storage
* operator UI
* pig ground-truth evaluation

Current roadmap status: Phase 8.3 synchronous multi-dock runtime coordination
implemented with synthetic evidence. Representative pig validation,
cross-reconnect session policy, concurrent camera ingestion, persistence, and
operator UI remain pending. Phase 9 and Phase 10 have not started.
