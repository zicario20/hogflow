# HogFlow — Codex Agent Instructions

## 1. Project identity

Project name: HogFlow

HogFlow is an independent computer vision and data analytics research prototype for evaluating automated livestock counting in constrained passage environments.

The system is intended to detect and track pigs moving through a narrow alley and count unique tracked individuals crossing a configured virtual counting line in the direction of a weighing area.

HogFlow is currently a research prototype / MVP.

It is not a production system.

It is not an operational deployment.

It is not a completed pilot.

Do not describe HogFlow as production-ready, commercially validated, or operationally proven.

---

## 2. Required project documents

Before making architectural, implementation, roadmap, product, or documentation decisions, inspect all project documents that currently exist.

Priority documents include:

* `HOGFLOW_PROJECT_CONTEXT.md`
* `AGENTS.md`
* `INVENTION_LOG.md`
* `MARKET_RESEARCH.md`
* `README.md`

If a listed document does not yet exist, report that clearly.

Do not invent its contents.

`HOGFLOW_PROJECT_CONTEXT.md` is the primary technical and roadmap context.

`AGENTS.md` defines agent behavior and engineering constraints.

`INVENTION_LOG.md` records the chronological evolution of the invention concept.

`MARKET_RESEARCH.md` contains commercial research hypotheses and must remain separate from validated technical results.

---

## 3. Central project hypothesis

The central hypothesis is:

A computer vision pipeline combining pig detection, multi-object tracking, and directional virtual-line crossing may be able to estimate the number of pigs moving through a constrained alley with sufficiently low count error to reduce continuous manual counting effort.

This is a hypothesis.

It must be tested using representative data and human-verified ground truth.

Do not claim:

* operational viability
* validated accuracy
* labor savings
* financial savings
* reduced downtime
* commercial value
* production readiness

unless supported by documented evidence produced by the project.

Clearly distinguish:

* fact
* project hypothesis
* implementation assumption
* experiment result
* market hypothesis

---

## 4. Development strategy

Build HogFlow incrementally.

The roadmap currently contains Phase 0 through Phase 16.

Only implement the phase explicitly requested by the user.

Do not silently continue to the next phase.

Do not combine multiple roadmap phases unless the user explicitly requests it.

Every phase must be independently understandable, runnable, and testable where technically applicable.

Prefer simple, measurable implementations over premature production architecture.

Do not create speculative enterprise infrastructure.

Do not build features because they “may be useful later” unless required by the current phase.

---

## 5. Current roadmap

The current roadmap is:

### Phase 0

Define problem and map process.

### Phase 1

Build generic line-crossing counter using public people or vehicle video.

### Phase 2

Create HogFlow software architecture.

### Phase 3

Acquire legal or public pig video data.

### Phase 4

Build pig detection baseline.

### Phase 5

Add multi-object tracking.

### Phase 6

Implement and evaluate virtual counting line positions.

### Phase 7

Handle reverse movement and duplicate counting.

### Phase 8

Build three-section session manager.

### Phase 9

Build Operator MVP User Interface.

### Phase 10

Store sessions and events in SQLite.

### Phase 11

Evaluate HogFlow against human-verified ground truth.

### Phase 12

Build error analysis and analytics dashboard.

### Phase 13

Create failure review system and review clips.

### Phase 14

Optionally evaluate group-weight consistency as a secondary validation signal.

### Phase 15

Document results as a portfolio case study.

### Phase 16

Prepare an authorized pilot-readiness plan and define validation gates.

Do not renumber, remove, merge, or redefine roadmap phases without explicit user approval.

---

## 6. Required workflow before coding

Before implementing any requested phase:

1. Read `AGENTS.md`.
2. Read `HOGFLOW_PROJECT_CONTEXT.md`.
3. Inspect `INVENTION_LOG.md` if it exists.
4. Inspect `MARKET_RESEARCH.md` if relevant to the task.
5. Inspect the repository structure.
6. Inspect existing code relevant to the requested phase.
7. Inspect existing tests.
8. Identify the current roadmap phase.
9. Identify dependencies from previous phases.
10. Briefly state the intended changes.

Then:

11. Implement only the requested phase.
12. Add or update relevant tests.
13. Run relevant tests.
14. Run Ruff when configured.
15. Inspect the resulting diff.
16. Report files changed.
17. Report test results.
18. Report known limitations.
19. Identify the recommended next phase.

Do not implement the recommended next phase unless explicitly requested.

Do not replace working code unnecessarily.

Do not refactor unrelated modules without a demonstrated requirement.

---

## 7. Technical stack

Use:

* Python >= 3.10
* OpenCV
* Roboflow Supervision
* SQLite for the MVP
* pytest
* Ruff

Detection models may include:

* YOLO
* RF-DETR
* another compatible detector

The detector implementation must remain replaceable.

Tracking should use a currently supported multi-object tracking implementation.

Before writing code dependent on third-party APIs:

1. inspect the installed dependency version
2. verify the currently available API
3. avoid deprecated examples when a current API is available

Do not assume historical Supervision or ByteTrack APIs remain valid.

---

## 8. Architecture rules

The expected conceptual repository structure is:

hogflow/
├── README.md
├── pyproject.toml
├── AGENTS.md
├── HOGFLOW_PROJECT_CONTEXT.md
├── INVENTION_LOG.md
├── MARKET_RESEARCH.md
├── src/
│   └── hogflow/
│       ├── detection/
│       ├── tracking/
│       ├── counting/
│       ├── sessions/
│       ├── storage/
│       └── video/
├── app/
├── tests/
├── data/
│   ├── raw/
│   └── processed/
├── notebooks/
└── docs/

Apply these rules:

* Detection must be isolated behind a detector interface.
* Tracking must be isolated from detection.
* Counting must not directly depend on a specific detector model.
* Counting must not directly depend on UI code.
* Session management must not depend on video processing.
* Storage logic must remain inside storage modules.
* UI code must not contain core counting business logic.
* Analytics must consume stored or exported results.
* Market research must not be treated as technical validation.
* Invention documentation must not be silently rewritten as ordinary product documentation.
* Do not place the complete application in `main.py` or `app.py`.

The conceptual pipeline is:

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

---

## 9. Detection interface

The rest of HogFlow should interact with detection through a generic abstraction.

Conceptually:

`detections = detector.predict(frame)`

Model-specific loading, inference, and conversion logic should remain inside the detection layer.

Tracking, counting, sessions, storage, and UI must not directly instantiate a specific AI model unless required by a clearly defined integration boundary.

---

## 10. Central counting rules

HogFlow counts unique tracked individuals.

HogFlow does not count frame detections.

A pig appearing in hundreds of frames must not increment the count once per frame.

Maintain session-scoped counted tracker IDs.

Conceptually:

`counted_tracker_ids = set()`

Initial business rule:

A tracker ID may contribute a maximum of one positive count per active session.

Only crossings in the configured direction toward the weighing area may create a positive counting candidate.

Reverse-direction crossings may be recorded as events.

Reverse crossings must not automatically increment the positive count.

Repeated positive crossings from the same tracker ID during the same session must not increment the count again.

A tracker ID is not a permanent biological identity.

The system must treat these as measurable risks:

* ID switches
* lost tracks
* re-identification
* occlusion
* fragmented tracks

Do not hide tracking failures using undocumented heuristics.

When uncertainty cannot be resolved by a validated rule, prefer creating a review event.

---

## 11. Session rules

The prototype models three sequential sections.

Conceptual flow:

IDLE
→ SELECT SECTION
→ START SESSION
→ COUNTING
→ END SESSION
→ REVIEW RESULT
→ CONFIRM OR FLAG FOR REVIEW
→ COMPLETED

Only one session may be active at a time in the MVP.

A session should support:

* section number
* start time
* end time
* AI count
* optional ground-truth count
* status

The initial system is semi-automatic.

The operator manually starts and ends section sessions.

Do not implement automatic gate, door, or section detection unless explicitly requested by a future approved phase.

Session-scoped counted tracker IDs must not leak into a new session.

---

## 12. Operator MVP UI rules

Phase 9 introduces the Operator MVP User Interface.

The terminal and technical logs remain available for development and diagnostics.

They should not be the normal operator interface after the Operator MVP UI exists.

The UI may use Streamlit or another simple compatible framework.

The UI must consume existing project modules.

The UI must not duplicate counting logic.

The UI must not directly increment the AI count.

Minimum UI information and controls:

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

`START SESSION` must use session-management logic.

The displayed count must reflect the real session counter.

`END SESSION` must stop active session counting.

`CONFIRM SESSION` must close the session through session logic.

`FLAG FOR REVIEW` must record a review request.

It must not silently modify the AI count.

Technical errors should be logged and shown to the operator in understandable language.

Do not build a production UI during Phase 9.

Do not add enterprise authentication, proprietary camera integration, plant-system integration, or gate controls unless explicitly approved in a future phase.

---

## 13. Storage rules

Use SQLite for the MVP.

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

Preserve clear event history and session relationships.

Do not silently overwrite AI counts to make them match ground truth.

Ground truth and AI output must remain distinguishable.

---

## 14. Evaluation priority

The primary product KPI is count error.

Do not optimize or report the project only through object-detection metrics.

Primary counting-system metrics should support:

* Exact Count Rate
* Mean Absolute Count Error
* Count Error Rate
* Undercount Rate
* Overcount Rate

Conceptually:

Absolute Count Error = abs(AI Count - Ground Truth)

Count Error Rate = abs(AI Count - Ground Truth) / Ground Truth

Detection precision and recall are diagnostic metrics.

They are not sufficient evidence that HogFlow counts correctly.

The final technical evaluation must measure HogFlow as a counting system.

---

## 15. Failure analysis

The project must identify and measure failures.

Important failure categories include:

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

Do not hide failures.

Do not manually remove difficult test examples merely to improve reported metrics.

Review events should preserve uncertainty for later analysis.

---

## 16. Testing philosophy

Core business logic must be testable without:

* an AI model
* a GPU
* a camera
* a real pig video

Use unit tests for:

* unique tracker counting
* duplicate crossing prevention
* directional crossing rules
* reverse movement
* session isolation
* single-active-session rules
* session reset behavior

Minimum conceptual test cases:

Pig crosses once:
Expected positive count = 1.

Pig approaches the line and turns without crossing:
Expected positive count = 0.

Pig crosses toward the scale and returns:
Positive count remains 1 for the same tracker ID during the active session.

Same tracker crosses toward the scale multiple times:
Positive count remains 1.

Two unique trackers cross:
Expected positive count = 2.

A person or non-pig detection is rejected before pig counting:
Expected positive pig count = 0.

A new session begins:
The new session has independent counted tracker ID state.

A tracker ID switch:
Expected behavior must be observable or reviewable rather than silently hidden.

Do not require computer vision integration to test counting and session business rules.

---

## 17. Data governance and confidentiality

Do not assume access to:

* JBS data
* employer videos
* facility cameras
* proprietary systems
* company source code
* internal operational documents
* confidential count records
* private network infrastructure

Development must use:

* public data
* synthetic data
* explicitly authorized data

Do not create code that depends on confidential employer infrastructure.

Do not place confidential employer information in:

* source code
* tests
* fixtures
* documentation
* screenshots
* sample databases
* Git history

Do not make unsupported claims about a named company's:

* counting errors
* losses
* productivity
* labor costs
* downtime
* financial performance

If a requested implementation appears to require confidential or unauthorized information, stop and report the dependency.

Do not invent substitute information.

---

## 18. Invention log rules

`INVENTION_LOG.md` is a chronological invention-development record.

Do not silently rewrite previous invention entries.

Do not delete historical entries because the architecture later changes.

When the user explicitly requests an invention-log update:

1. preserve previous entries
2. add a new dated entry
3. describe the newly conceived concept or material design change
4. distinguish concept from implemented functionality
5. identify whether the change is experimental, planned, or implemented
6. avoid unsupported legal conclusions about patentability, ownership, inventorship, or freedom to operate

Do not claim that the invention log creates patent protection.

Do not describe the project as patented or patent pending unless documented evidence supports that status.

If code implementation differs from an earlier invention concept, preserve the historical entry and document the later change separately.

---

## 19. Market research rules

`MARKET_RESEARCH.md` contains market hypotheses.

It is not technical validation.

Do not convert market estimates into facts without updated evidence.

The current preliminary research identifies approximately 18–27 candidate facilities among major U.S. pork processors.

This is a working research range.

It is not a validated TAM or SAM.

Do not state that all candidate facilities:

* receive live hogs
* use the same alley workflow
* manually count pigs
* have counting discrepancies
* need HogFlow
* would purchase HogFlow

Facility qualification should distinguish:

* Tier A: confirmed or strongly supported live-hog processing candidate
* Tier B: likely relevant but workflow requires verification
* Tier C: not an initial HogFlow target

A facility should enter a validated serviceable market only after relevant workflow assumptions are verified.

Revenue scenarios in market research are hypothetical models.

Do not describe them as forecasts, valuation, pipeline, contracts, or expected revenue.

Keep market research separate from experiment results.

---

## 20. Optional weight consistency analysis

Weight is a secondary validation signal.

It is not part of the primary counting algorithm.

Do not invent a universal valid pig-weight range.

Any weight-based analysis must use an explicitly defined, authorized, public, or synthetic reference distribution.

Weight consistency may recommend review.

It must not silently rewrite the AI count without a validated business rule.

Clearly label this functionality as optional and experimental unless evidence supports a stronger status.

---

## 21. Pilot readiness rules

Phase 16 prepares HogFlow for a possible future authorized pilot.

Phase 16 does not mean a pilot has occurred.

Pilot-readiness documentation should address:

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

Define evidence required before recommending a real-world pilot.

Any real-world deployment, recording, camera installation, or facility-data use must be treated as requiring explicit authorization.

HogFlow remains a research prototype until representative validation evidence supports a different documented status.

Do not claim production readiness merely because Phase 16 is completed.

---

## 22. Documentation integrity

Documentation must reflect actual implementation status.

Clearly distinguish:

* IMPLEMENTED
* EXPERIMENTAL
* PLANNED
* OPTIONAL
* HYPOTHESIS

Never document an unimplemented feature as completed.

Never change reported experimental results merely to align with project goals.

If a result is poor, document the poor result and relevant failure analysis.

The README should eventually cover:

* Problem
* Current Process
* Proposed Solution
* System Architecture
* Detection Pipeline
* Tracking Strategy
* Counting Logic
* Session Management
* Operator UI
* Data Model
* Evaluation Methodology
* Results
* Failure Analysis
* Limitations
* Privacy and Data Governance
* Market Research Status
* Pilot Readiness Status
* Future Work

---

## 23. Git and change discipline

Keep changes scoped to the requested phase.

Prefer small, reviewable commits.

Do not mix unrelated refactors with roadmap implementation.

Do not delete project documentation without explicit justification.

Before reporting completion:

* inspect the diff
* confirm no confidential data was added
* confirm no unrelated phase was implemented
* confirm tests relevant to the phase were executed

Do not claim tests passed if they were not run.

If a test cannot run, report:

* the command attempted
* the reason it could not run
* the resulting uncertainty

---

## 24. Final response after every coding task

End every implementation task with:

### Phase completed

State the roadmap phase worked on.

### Status

State one of:

* COMPLETE
* PARTIALLY COMPLETE
* BLOCKED

### Changes made

Briefly explain the implementation.

### Files changed

List files created, modified, or deleted.

### Tests and validation

List commands executed and results.

### Architecture check

State whether the implementation follows HogFlow module-separation rules.

### Data governance check

State whether public, synthetic, or authorized data was used and whether any confidential dependency was identified.

### Known limitations

State current limitations honestly.

### Invention log impact

State one of:

* No invention-log update recommended.
* Invention-log update may be appropriate because a new material concept was introduced.

Do not modify the invention log unless explicitly requested.

### Market research impact

State whether the implementation changes any market assumption.

Do not modify market estimates without evidence and explicit task scope.

### Recommended next phase

Identify the logical next roadmap phase.

Do not implement it unless explicitly requested.
