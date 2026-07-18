# HogFlow

HogFlow is a computer vision research prototype / MVP for evaluating automated
livestock counting in constrained passage environments.

## Project hypothesis

HogFlow is based on the hypothesis that a pipeline combining pig detection,
multi-object tracking, and directional virtual-line crossing may be able to
estimate the number of pigs moving through a constrained alley with
sufficiently low count error to reduce continuous manual counting effort.

This is a research hypothesis, not a validated result.

## Current project status

Current roadmap status: Phase 3 infrastructure implemented; real authorized dataset acquisition and review in progress; Phase 4 not started.

The repository contains Phase 0 documentation, an approved Phase 1 generic
people/vehicle finite-segment proof of concept, and the completed Phase 2
software architecture. Phase 2.3 preserves the Phase 1 CLI while routing generic
video input, detection, tracking, counting, annotation, and event output through
the approved contracts and adapters. Phase 3 adds a local-only authorized-video
inventory, bounded metadata validation, conservative camera-motion estimates,
manual review sidecars, and JSON/CSV/Markdown reports.

Real authorized pig-video acquisition and review may still be ongoing. No real
pig media is committed, and pig-specific detection, tracking validation, and
counting evaluation have not started. HogFlow is not production-ready,
operationally proven, or commercially validated.

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

## High-level pipeline

Implemented generic Phase 2.3 flow:

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

## Roadmap status

* Phase 0: documented
* Phase 1: generic people/vehicle finite-segment proof of concept implemented
* Phase 2: completed through Phase 2.1, Phase 2.2, and Phase 2.3
* Phase 3: inventory infrastructure implemented; real authorized collection and review in progress
* Phase 4 through Phase 16: not started

Phase 3 infrastructure works with an empty directory and synthetic test videos.
The repository contains no real pig video and makes no claim that a suitable
real dataset has been acquired.

## Documentation index

* [AGENTS.md](AGENTS.md)
* [HOGFLOW_PROJECT_CONTEXT.md](HOGFLOW_PROJECT_CONTEXT.md)
* [INVENTION_LOG.md](INVENTION_LOG.md)
* [MARKET_RESEARCH.md](MARKET_RESEARCH.md)

## Current limitations

The generic pipeline has not been validated on pigs. Phase 3 motion estimates
use bounded samples and can be wrong when moving animals dominate image
features. HogFlow has no pig-specific detector, pig-specific tracker evaluation,
sessions, SQLite persistence, operator UI, ground-truth comparison, analytics,
or pilot workflow. Tracker ID switches and fragmentation remain count risks.
Synthetic infrastructure tests do not prove real pig-video or model quality.
