# HogFlow Project Context

## Document purpose

This document records the current technical and roadmap context for HogFlow during repository initialization.

Status labels used here:

* HYPOTHESIS: a project claim that still requires representative data and human-verified validation
* PLANNED: a capability or phase that is part of the roadmap but not yet implemented
* OPTIONAL: a capability that is explicitly secondary or conditional in the roadmap

Current repository status: Phase 5 in progress — Phase 5.1 live-camera acquisition foundation implemented and validated on one laptop USB webcam using OpenCV MSMF; RTSP, pig detector execution, pig tracking, and pig counting remain unvalidated; Phase 5.2 not started.

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
* Phase 5.2

## Unique tracker counting concept

PLANNED business concept:

* HogFlow counts unique tracked individuals, not per-frame detections.
* A pig seen across many frames must not increment the count once per frame.
* Session-scoped counted tracker IDs should be maintained conceptually as `counted_tracker_ids = set()`.
* A tracker ID may contribute at most one positive count per active session.

## Directional crossing and reverse movement rules

PLANNED counting rules:

* Only crossings in the configured direction toward the weighing area may create a positive counting candidate.
* Reverse-direction crossings may be recorded as events.
* Reverse crossings must not automatically increment the positive count.
* Repeated positive crossings from the same tracker ID during the same session must not increment the count again.

Tracking uncertainty remains a measured risk rather than something to hide. Relevant risks include ID switches, lost tracks, re-identification, occlusion, and fragmented tracks.

When uncertainty cannot be resolved by a validated rule, the project preference is to create a review event instead of applying undocumented heuristics.

## Three-section workflow and session model

PLANNED prototype workflow:

The MVP models three sequential sections.

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

* Only one session may be active at a time in the MVP.
* The operator manually starts and ends section sessions.
* Session-scoped counted tracker IDs must reset between sessions.
* Automatic gate, door, or section detection is out of scope unless explicitly approved in a future phase.

Each session should support at least:

* section number
* start time
* end time
* AI count
* optional ground-truth count
* status

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
Phase 5 is in progress through Phase 5.1. The live acquisition foundation has
synthetic, fake-backend, and one real laptop USB-webcam validation record.
RTSP, Phase 5.2, and pig-specific tracking have not started.

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

Not yet implemented:

* Phase 5.2 and remaining pig-specific tracking work
* Phase 6 through Phase 16
* a completed or validated real authorized pig-video dataset
* completed real pig annotations
* a real trained and validated pig-specific detector checkpoint
* pig-specific tracking evaluation
* operational session management
* receiving batches or groups
* exception-event management
* SQLite event storage
* operator UI
* pig ground-truth evaluation

Current roadmap status: Phase 5 in progress — Phase 5.1 live-camera acquisition foundation implemented and validated on one laptop USB webcam using OpenCV MSMF; RTSP, pig detector execution, pig tracking, and pig counting remain unvalidated; Phase 5.2 not started.
