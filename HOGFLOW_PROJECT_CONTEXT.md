# HogFlow Project Context

## Document purpose

This document records the current technical and roadmap context for HogFlow during repository initialization.

Status labels used here:

* HYPOTHESIS: a project claim that still requires representative data and human-verified validation
* PLANNED: a capability or phase that is part of the roadmap but not yet implemented
* OPTIONAL: a capability that is explicitly secondary or conditional in the roadmap

Current repository status: Phase 2 in progress — Phase 2.1 architecture foundation implemented; Phase 2.2 and Phase 2.3 not started.

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

## Detection and tracking concept

PLANNED:

* Detection should be isolated behind a detector interface.
* The rest of the system should conceptually interact with detection as `detections = detector.predict(frame)`.
* Model-specific inference and conversion logic should stay inside the detection layer.
* Tracking should remain isolated from detection implementation details.
* Counting must not directly depend on a specific detector model.

Candidate detector families mentioned in project guidance include YOLO, RF-DETR, or another compatible detector. The detector implementation must remain replaceable.

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

* Phase 2.1 — architecture foundation
* Phase 2.2 — interfaces and contracts
* Phase 2.3 — existing Phase 1 integration with the approved contracts

Only Phase 2.1 is implemented. This subphase structure does not renumber or change the official Phase 0 through Phase 16 roadmap.

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

Not yet implemented:

* Phase 2.2 contracts
* Phase 2.3 pipeline integration
* Phase 3 through Phase 16
* pig-specific detector
* pig-specific tracking evaluation
* operational session management
* receiving batches or groups
* exception-event management
* SQLite event storage
* operator UI
* pig ground-truth evaluation

Current roadmap status: Phase 2 in progress — Phase 2.1 architecture foundation implemented; Phase 2.2 and Phase 2.3 not started.
