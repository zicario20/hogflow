# HogFlow

[![CI](https://github.com/zicario20/hogflow/actions/workflows/ci.yml/badge.svg)](https://github.com/zicario20/hogflow/actions/workflows/ci.yml)

HogFlow is a computer vision research prototype / MVP for evaluating automated
livestock counting in constrained passage environments.

## Project hypothesis

HogFlow is based on the hypothesis that a pipeline combining pig detection,
multi-object tracking, and directional virtual-line crossing may be able to
estimate the number of pigs moving through a constrained alley with
sufficiently low count error to reduce continuous manual counting effort.

This is a research hypothesis, not a validated result.

## Current project status

Current roadmap status: Phase 7 lifecycle-aware directional counting
infrastructure implemented - explicit positive direction, reverse and duplicate
decisions, atomic frame updates, and reconnect-isolated lifecycle totals are
implemented; representative pig duplicate-counting and reverse-movement
validation remains pending; Phase 8 has not started.

## Official project memory

The living technical and operational memory for HogFlow is maintained in
[HOGFLOW_PROJECT_MEMORY.md](HOGFLOW_PROJECT_MEMORY.md). Future
architecture-relevant changes must update that memory in the same commit.

The repository contains Phase 0 documentation, an approved Phase 1 generic
people/vehicle finite-segment proof of concept, and the completed Phase 2
software architecture. Phase 2.3 preserves the Phase 1 CLI while routing generic
video input, detection, tracking, counting, annotation, and event output through
the approved contracts and adapters. Phase 3 adds a local-only authorized-video
inventory, bounded metadata validation, conservative camera-motion estimates,
manual review sidecars, and JSON/CSV/Markdown reports.

Real authorized pig-video acquisition, annotation, and review may still be
ongoing. No real pig media is committed. Phase 4.3 supplies a replaceable local
training pipeline, but no real pig baseline was trained during implementation.
Pig-specific tracking and counting evaluation have not been completed. HogFlow is not
production-ready, operationally proven, or commercially validated.

Phase 4.1 adds source-only CI, framework-neutral detection-evaluation models,
deterministic basic detection metrics, metadata-only dataset selection, and a
protected local annotation workspace. It introduces no detector implementation
or accuracy result.

Phase 4.2 adds deterministic source-video splitting, timestamp planning, local
frame extraction, a finalized pig bounding-box policy, framework-neutral YOLO
label support, sanitized manifests, and local dataset validation. It does not
train or run a detector.

Phase 4.3 adds framework-neutral trainer contracts, mandatory prepared-dataset
validation, one isolated Ultralytics YOLO trainer, deterministic configuration,
local checkpoint/provenance output, reuse of Phase 4.1 evaluation metrics, and
local failure reporting. The training pipeline is operational, but no real pig
checkpoint or accuracy result was produced during implementation.

Phase 5.1 adds framework-neutral continuous acquisition models and contracts,
runtime-only protected camera locators, isolated OpenCV USB/RTSP and local-file
adapters, a deterministic synthetic source, fixed-capacity buffering,
reconnection and health state, and a headless diagnostic CLI. It performs no
detection, tracking, counting, recording, upload, or remote telemetry.

Phase 5.2 connects that bounded stream to a lifecycle-aware, replaceable live
detector contract. It adds latest-frame inference scheduling, explicit
camera-drop/inference-skip telemetry, deterministic detector doubles, one
explicit-local-file Ultralytics adapter, an optional local OpenCV preview, and
a structured headless CLI. No valid local pig-detector weights were available,
so real pig inference remains blocked and no pig-detection accuracy claim is
made. One local USB-webcam smoke test used only the empty detector and saved no
frames. Tracking, line crossing, and counting remain outside this phase.

Phase 5.3 adds a separate lifecycle-aware live tracker contract, immutable
tracking results tied to exact source sequences, one-stream-per-tracker state,
bounded tracking telemetry, deterministic tracker doubles, and an isolated
Supervision 0.29.1 ByteTrack adapter. It composes serially after successful
Phase 5.2 inference without adding another queue. The optional local preview
may show temporary track IDs, but active tracks are not counts. No validated
pig detector was available, so real pig tracking remains unvalidated and no
ID-switch, occlusion, or tracking-accuracy claim is made.
One local USB-webcam integration test used synthetic moving boxes with the
installed ByteTrack adapter, completed a long run and immediate reopen, and
saved no frames. It validates lifecycle and data flow only, not real pig
tracking.

Phase 5.4 adds normalized finite-line geometry, explicit side and neutral
direction models, bottom-center track anchors, lifecycle-qualified crossing
events, bounded side-state cleanup, reconnect reset alignment, and serial
integration after successful tracking. Crossing is disabled by default. It
emits geometric events only: there is no accumulated pig total, one-ID-one-count
rule, operational direction, session, persistence, or accuracy claim.

Phase 6 adds a serial offline evaluator that replays the same immutable
`TrackingResult` sequence through one isolated Phase 5.4 crossing lifecycle per
line candidate. It provides deterministic candidate plans and fingerprints,
descriptive gap/endpoint diagnostics, optional one-to-one crossing-event
ground-truth matching, explicit ranking policies, strict path-free JSON, and a
technical CLI. Synthetic fixtures validate the infrastructure; no
representative pig ground truth was evaluated and no production line placement
is recommended.

Phase 7 consumes Phase 5.4 crossing events through a separate lifecycle-aware
counter. The first positive event for a source/lifecycle/tracker identity
increments once; repeated positives and reverse events remain explicit
zero-increment decisions. Reconnect creates a fresh total and counted-identity
set. This is a lifecycle diagnostic, not a session result or validated
biological pig count.

## Phase 0 documentation

* [Problem statement](docs/phase_0/problem_statement.md)
* [Current process](docs/phase_0/current_process.md)
* [Proposed solution](docs/phase_0/proposed_solution.md)
* [Process map](docs/phase_0/process_map.md)
* [Assumptions and unknowns](docs/phase_0/assumptions_and_unknowns.md)
* [Phase 0 summary](docs/phase_0/phase_0_summary.md)

## Phase 1

Phase 1 implements a generic people/vehicle proof of concept that reads a local
video, obtains generic detections and tracker IDs, evaluates bottom-center
movement against an arbitrary finite directional segment, counts each eligible
tracker ID at most once, logs valid segment-crossing events, and writes an
annotated video. It does not validate pig counting.

The Phase 1 CLI arguments, finite-segment semantics, JSONL schema, annotation
content, generic class filtering, and default model remain compatible after the
Phase 2.3 architecture migration.

* [Phase 1 design](docs/phase_1/phase_1_design.md)
* [Phase 1 usage](docs/phase_1/phase_1_usage.md)
* [Phase 1 summary](docs/phase_1/phase_1_summary.md)

## Phase 2

Phase 2.1 establishes the foundation:

* explicit module responsibilities and dependency rules
* shared errors and centralized logging configuration
* immutable foundational settings
* automated architecture checks

Phase 2.2 establishes the contracts:

* immutable `Frame`, `BoundingBox`, `Detection`, and `Track` models
* replaceable `Detector`, `Tracker`, and `VideoSource` Protocols
* framework-independent communication boundaries

Phase 2.3 provides generic integration:

* OpenCV video-source adapter
* Ultralytics generic detector adapter
* Ultralytics ByteTrack adapter consuming external detections without duplicate
  inference
* synchronous generic counting pipeline
* CLI composition through the approved architecture
* synthetic infrastructure integration tests

* [Phase 2.1 architecture foundation](docs/phase_2/phase_2_1_architecture_foundation.md)
* [Phase 2 dependency rules](docs/phase_2/phase_2_1_dependency_rules.md)
* [Phase 2.2 interfaces and contracts](docs/phase_2/phase_2_2_interfaces.md)
* [Phase 2.2 summary](docs/phase_2/phase_2_2_summary.md)
* [Phase 2.3 integration design](docs/phase_2/phase_2_3_integration_design.md)
* [Phase 2.3 usage](docs/phase_2/phase_2_3_usage.md)
* [Phase 2.3 summary](docs/phase_2/phase_2_3_summary.md)
* [Architecture decisions](docs/phase_2/architecture_decisions.md)

## Phase 3

Phase 3 implements local dataset-acquisition infrastructure without bundling
media or beginning model work:

* immutable framework-neutral inventory and review models
* deterministic local video discovery
* bounded OpenCV metadata and decode validation
* feature-based camera-motion estimates with conservative labels
* explicit authorization and manual scene-review sidecars
* optional clip-boundary manifests
* JSON, CSV, and Markdown inventory reports
* Git safeguards for videos, frames, outputs, and model weights

Automatic labels are inventory aids only. Counting candidacy requires manual
confirmation of authorization, camera stability, a clear passage, predominant
direction, and a usable virtual-line location. It does not validate counting.

* [Phase 3 data acquisition](docs/phase_3/phase_3_data_acquisition.md)
* [Phase 3 video inventory](docs/phase_3/phase_3_video_inventory.md)
* [Phase 3 usage](docs/phase_3/phase_3_usage.md)
* [Phase 3 summary](docs/phase_3/phase_3_summary.md)
* [Local data workspace](data/README.md)

## Phase 4

Phase 4 remains in progress. Phase 4.1 implements evaluation foundations:

* GitHub Actions CI using synthetic/source-only tests
* immutable ground-truth, prediction, frame, match, result, and dataset models
* explicit pixel and normalized bounding-box coordinates
* area, intersection, union, IoU, deterministic one-to-one matching, precision,
  recall, and F1
* metadata-only Phase 3 inventory selection with opaque clip IDs
* local annotation, model, inference-run, and evaluation workspaces protected by Git

Phase 4.2 implements local annotation-dataset preparation tooling:

* source-video-level train/validation/test planning with preparation-only handling for small datasets
* fixed-interval, target-count, and bounded-uniform frame planning
* explicit local source-map privacy boundary and opaque frame names
* idempotent local JPEG/PNG extraction without automatic labels
* finalized `0 = pig` bounding-box and explicit frame-status policy
* deterministic YOLO parsing/serialization independent from detector frameworks
* sanitized dataset manifests and JSON/CSV/Markdown validation reports

Phase 4.3 implements the replaceable baseline-training workflow:

* immutable training configuration and `DetectorTrainer` contract
* mandatory Phase 4.2 dataset, split, image, label, and class-map gate
* isolated `YOLOBaselineTrainer` with train, validate, and resume behavior
* deterministic seed configuration and a bounded 30-epoch maximum
* local best-checkpoint and reproducibility metadata export
* Phase 4.1 precision, recall, F1, and IoU evaluation reuse
* separately labeled framework metrics, including framework mAP when available
* local false-positive, false-negative, small-object, empty-frame, and
  occlusion-limitation reports

CI validates code quality and deterministic synthetic behavior. It does not
validate real pig-video quality, annotation quality, detector accuracy, or
counting performance. No mAP implementation is claimed.

* [Phase 4.1 CI and detection foundation](docs/phase_4/phase_4_1_ci_and_detection_foundation.md)
* [Detection evaluation foundation](docs/phase_4/phase_4_detection_evaluation.md)
* [Phase 4.1 summary](docs/phase_4/phase_4_1_summary.md)
* [Phase 4.2 local annotation dataset](docs/phase_4/phase_4_2_local_annotation_dataset.md)
* [Final annotation policy](docs/phase_4/phase_4_annotation_policy.md)
* [Source-video dataset splitting](docs/phase_4/phase_4_dataset_splitting.md)
* [Frame planning and extraction](docs/phase_4/phase_4_frame_extraction.md)
* [Phase 4.2 summary](docs/phase_4/phase_4_2_summary.md)
* [Phase 4.3 local training](docs/phase_4/phase_4_3_training.md)
* [Phase 4.3 summary](docs/phase_4/phase_4_3_summary.md)

## Phase 5

Phase 5 is implemented through the authorized Phase 5.4 live crossing scope:

* stream-first USB and RTSP production-input architecture
* explicit live, development-file, and synthetic source types
* immutable ordered `FramePacket` values with packed RGB bytes
* thread-safe bounded buffering with observable frame drops
* deterministic live-source reconnect policy and bounded health reporting
* credential-safe source identities and local-only camera data policy
* headless diagnostics without automatic frame persistence
* explicit detector load/infer/close lifecycle and immutable per-frame results
* latest-useful-frame scheduling without an unbounded inference queue
* separate source-drop, inference-skip, and inference-failure accounting
* deterministic empty, scripted, slow, and failing detector doubles
* explicit local Ultralytics artifact adapter with sanitized provenance
* optional ephemeral local OpenCV preview
* framework-neutral live tracker lifecycle and immutable per-frame results
* one tracker instance per source lifecycle with explicit reset and cleanup
* deterministic empty, scripted, IoU, slow, and failing tracker doubles
* isolated Supervision ByteTrack adapter with framework conversion boundaries
* tracking telemetry for updates, failures, visible tracks, resets, and latency
* optional ephemeral local preview of temporary track IDs
* normalized finite virtual-line configuration and bottom-center track anchors
* lifecycle-qualified directional crossing events without accumulated counting
* bounded crossing state, telemetry, reconnect reset, and optional local preview

Prerecorded videos remain development, training, and validation tools only.
No valid local pig detector was available or executed. Temporary-ID tracking
integration is implemented, but real pig tracking is not validated and the
live Phase 5.4 path has only synthetic event validation and performs no
accumulated counting.

* [Phase 5.1 live streaming](docs/phase_5/phase_5_1_live_streaming.md)
* [Phase 5.1 real hardware validation](docs/phase_5/phase_5_1_hardware_validation.md)
* [Phase 5.1 summary](docs/phase_5/phase_5_1_summary.md)
* [Phase 5.2 live detection](docs/phase_5/phase_5_2_live_detection.md)
* [Phase 5.2 summary](docs/phase_5/phase_5_2_summary.md)
* [Phase 5.3 live tracking](docs/phase_5/phase_5_3_live_tracking.md)
* [Phase 5.3 validation](docs/phase_5/phase_5_3_validation.md)
* [Phase 5.3 summary](docs/phase_5/phase_5_3_summary.md)
* [Phase 5.4 live crossing](docs/phase_5/phase_5_4_live_crossing.md)
* [Phase 5.4 validation](docs/phase_5/phase_5_4_validation.md)
* [Phase 5.4 summary](docs/phase_5/phase_5_4_summary.md)

## Phase 6

Phase 6 provides an offline, framework-neutral line-position evaluation
workflow. Candidate order cannot alter results, each candidate receives an
isolated crossing lifecycle, gaps remain observable, and finite-segment
geometry is reused from Phase 5.4. Without crossing-event ground truth, the
default report makes no automatic recommendation.

* [Phase 6 line-position evaluation](docs/phase_6/phase_6_line_position_evaluation.md)
* [Phase 6 validation](docs/phase_6/phase_6_validation.md)
* [Phase 6 summary](docs/phase_6/phase_6_summary.md)

## Phase 7

Phase 7 provides framework-neutral, atomic directional decisions over live
crossing events. Positive direction is explicit, counted identities are
qualified by source and crossing lifecycle, reverses never decrement, and
duplicates never increment again within that lifecycle. Counting remains
disabled by default.

* [Phase 7 reverse and duplicate counting](docs/phase_7/phase_7_reverse_duplicate_counting.md)
* [Phase 7 validation](docs/phase_7/phase_7_validation.md)
* [Phase 7 summary](docs/phase_7/phase_7_summary.md)

## High-level pipeline

Production input through lifecycle directional decisions implemented through
Phase 7:

LIVE CAMERA
→ CAMERA SOURCE ADAPTER
→ ORDERED FRAME PACKET
→ BOUNDED FRAME BUFFER
→ LATEST-FRAME INFERENCE SCHEDULER
→ REPLACEABLE LIVE DETECTOR
→ STRUCTURED FRAME DETECTIONS
→ REPLACEABLE LIVE TRACKER
→ STRUCTURED TEMPORARY TRACKS
→ NORMALIZED FINITE VIRTUAL LINE
→ DIRECTIONAL CROSSING EVENTS
→ LIFECYCLE DIRECTIONAL DECISIONS / LOCAL TELEMETRY

Session totals, biological re-identification, persistence, and operator UI are
not implemented in the live pipeline.

Implemented generic Phase 2.3 development/video flow:

VIDEO SOURCE
→ FRAME
→ GENERIC DETECTOR
→ DETECTIONS
→ TRACKER
→ TRACKS
→ FINITE-SEGMENT DIRECTIONAL COUNTER
→ ANNOTATED VIDEO / JSONL EVENTS

Planned later-roadmap flow adds pig-specific validation, session management,
storage, operator UI, and evaluation only in their approved phases.

Implemented Phase 6 offline evaluation flow:

TRACKING REPLAY
→ VALIDATED LINE CANDIDATES
→ ISOLATED PHASE 5.4 CROSSING LIFECYCLES
→ PER-CANDIDATE CROSSING EVENTS
→ DESCRIPTIVE / OPTIONAL GROUND-TRUTH METRICS
→ EXPLICIT RANKING
→ SANITIZED REPORT

## Roadmap status

* Phase 0: documented
* Phase 1: generic people/vehicle finite-segment proof of concept implemented
* Phase 2: completed through Phase 2.1, Phase 2.2, and Phase 2.3
* Phase 3: inventory infrastructure implemented; real authorized collection and review in progress
* Phase 4: implementation completed through Phase 4.3; real annotation and empirical detector validation may still be incomplete
* Phase 5: implemented through authorized Phase 5.4 event-only live crossing; empirical pig validation remains absent
* Phase 6: evaluation infrastructure implemented; representative pig line-position evaluation remains pending
* Phase 7: lifecycle-aware directional counting infrastructure implemented; representative duplicate/reverse validation remains pending
* Phase 8 through Phase 16: not started

Phase 3 infrastructure works with an empty directory and synthetic test videos.
The source-controlled repository contains no real pig video and makes no claim
that a suitable real dataset has been acquired.

## Documentation index

* [AGENTS.md](AGENTS.md)
* [HOGFLOW_PROJECT_CONTEXT.md](HOGFLOW_PROJECT_CONTEXT.md)
* [INVENTION_LOG.md](INVENTION_LOG.md)
* [MARKET_RESEARCH.md](MARKET_RESEARCH.md)

## Current limitations

The generic pipeline has not been validated on pigs. The live-camera foundation
has been validated on one laptop USB webcam through OpenCV MSMF, but not on
RTSP, another camera model, or another backend. Phase 5.2 live detector control
flow is validated synthetically and with one local USB-webcam-to-empty-detector
smoke test, but no valid local pig-detector artifact was available and real pig
inference was not validated. Phase 5.3 temporary-ID integration is validated
with deterministic synthetic detections and the installed Supervision adapter,
but not with representative pig detections; ID-switch, fragmentation, and
occlusion behavior remain unmeasured. Phase 5.4 crossing logic is validated
only with synthetic tracks; line placement, event accuracy, and count accuracy
have not been measured on pigs. Phase 6 compares candidate lines reproducibly,
but its evidence remains synthetic: representative tracking replay and
human-verified crossing-event ground truth are absent, so it establishes
neither an optimal line nor pig-count accuracy. Phase 7 policy mechanics are
validated synthetically, but ID switches, fragmentation, ID reuse, reconnect
boundaries, real reverse movement, and duplicate-count accuracy have not been
evaluated with representative pigs. The lifecycle total is not a session total
and reverses do not decrement it. Real pig annotation may be incomplete, and no
real pig detector was trained or validated during Phase 4.3
implementation. Phase 3 motion estimates use bounded samples and can be wrong
when moving animals dominate image features. HogFlow has no pig-specific
tracking evaluation, sessions, SQLite persistence, operator UI, live counting
ground-truth comparison, analytics, or pilot workflow. Tracker ID switches and
fragmentation remain count risks. OpenCV backend support, timeouts, and camera
setting compliance vary by platform. Synthetic CI, training, and streaming
tests do not prove real pig-video, model, camera, tracking, or counting quality.
