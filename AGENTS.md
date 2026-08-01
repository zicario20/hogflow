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
* `HOGFLOW_PROJECT_MEMORY.md`
* `AGENTS.md`
* `INVENTION_LOG.md`
* `MARKET_RESEARCH.md`
* `README.md`

If a listed document does not yet exist, report that clearly.

Do not invent its contents.

`HOGFLOW_PROJECT_CONTEXT.md` is the primary technical and roadmap context.

`HOGFLOW_PROJECT_MEMORY.md` is the official living technical and operational
memory. It must be checked against the repository and updated in the same
commit whenever a change alters project knowledge.

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

Authorized Phase 5 subphase:

* Phase 5.4 — Live virtual-line crossing event integration.

Phase 5.4 consumes live tracking results, classifies normalized representative
points against one configured finite directed line, and emits directional
crossing events. It does not maintain an accumulated animal count, deduplicate
animals, apply session rules, persist events, or change the responsibilities
of Phase 6 or Phase 7.

### Phase 6

Implement and evaluate virtual counting line positions.

### Phase 7

Handle reverse movement and duplicate counting.

Phase 7 may maintain an accumulated directional total only inside one explicit
source/crossing lifecycle. Its counted identity is temporary and must include
source, lifecycle, and tracker ID. Reverse events do not decrement the initial
total, repeated positive events do not increment again, and reconnect/reset
starts a new independent total. This lifecycle total is not a session count;
Phase 8 remains responsible for session scope.

### Phase 8

Build three-section session manager.

Authorized Phase 8 subphase:

* Phase 8.1 — Multi-Dock Unloading Domain Model and Rules.
* Phase 8.2 — Unloading Session ↔ Phase 7 Counting Lifecycle Integration.
* Phase 8.3 — Multi-Dock Runtime Coordination.
* Phase 8.4 — Shared Counting Lane Alignment.

Phase 8.1 models exactly four independently occupied docks and a variable
number of ordered single-pig-type unloading sessions per truck operation. The
commonly observed three gate sections and approximately 60 pigs per section
are operational references, not aggregate limits or automatic defaults.
Phase 8.1 is pure domain logic and does not integrate the Phase 7 counting
lifecycle; that application boundary belongs to Phase 8.2.

Phase 8.2 implements that boundary in `hogflow.sessions`: one active unloading
session owns one isolated Phase 7 lifecycle, completion transfers its final
positive-direction total exactly once, and cancellation discards unfinished
counting. Phase 8.2 does not add multi-dock runtime orchestration, persistence,
networking, API, UI, camera orchestration, concurrency, automatic session
generation, or Phase 8.3.

Phase 8.3 introduced a synchronous application coordinator in
`hogflow.sessions`. Its original per-dock counter/source assumption was
superseded by the authorized Phase 8.4 operational correction.

Phase 8.4 preserves four independent dock operations but models one physical
shared counting corridor, one source, and one Phase 7 counter. Exactly one
active unloading session may bind that lane at a time. Completion or
cancellation releases it. Docks never own counters, and the lane cannot switch
owners silently. Calls remain caller-serialized; Phase 8.4 does not implement
camera acquisition, multiple cameras, threading, async execution, persistence,
API, networking, UI, automatic scheduling, Phase 9, or Phase 10.

### Phase 9

Build Operator MVP User Interface.

Authorized Phase 9 subphase:

* Phase 9.1 — Operator MVP User Interface.
* Phase 9.2 — Operator Workflow Safety & Executable Composition.
* Phase 9.3 — Camera Acquisition and Counting Pipeline Integration.
* Phase 9.4 — Live Operator Experience, Video Preview and Diagnostics.

Phase 9.1 introduces a snapshot-driven presentation and application boundary
over the public Phase 8 coordinator. It may register/start/cancel/complete
trucks and unloading sessions, display the four dock records, display the
single shared-lane owner and live lifecycle count, and display finalized
totals. It must not store business state, increment counts, access private
coordinator members, poll, open cameras, persist data, use networking, or
start Phase 10.

Phase 9.2 adds the executable local composition root, snapshot-derived control
availability, explicit next-session guidance, destructive-action
confirmations, operator status feedback, and safe application shutdown.
`python -m hogflow` and `hogflow run` compose one no-camera shared counter/lane,
the Phase 8 coordinator, application service, presenter, and Tkinter view.
This executable does not fabricate camera input: its local lifecycle and
crossing fingerprint are technical placeholders until a future authorized
camera composition replaces them. Phase 9.2 must remain manual-refresh and
must not add camera acquisition, OpenCV preview, YOLO, polling, timers,
threads, networking, persistence, authentication, scheduling, hardware, or
Phase 10.

Phase 9.3 authorizes exactly one configurable local camera/file source, one
controlled background worker, and one detector/tracker/crossing pipeline for
the shared physical lane. The worker may route exact lifecycle-qualified
crossing evidence through a serialized application boundary to the existing
`SharedCountingLane`; the lane remains the sole Phase 7 counter owner. Docks
must not own cameras, detectors, trackers, workers, or counters. Camera work
must never call Tkinter, and immutable snapshots are the only presentation
view of camera/pipeline state. This subphase adds no video preview, overlay,
automatic polling, reconnect loop, persistence, networking, multiple cameras,
Phase 9.4, or Phase 10.

Phase 9.4 authorizes one local, ephemeral, latest-frame-only preview over the
existing shared worker and source. The worker may publish immutable RGB frames
and diagnostic overlay values to one replaceable visual slot, but it must
never call Tkinter or wait for rendering. The Tkinter thread alone consumes
and renders that slot using one bounded, cancellable presentation refresh.
Bounding boxes, temporary track IDs, line geometry, current crossing direction,
camera/pipeline health, FPS, and bounded failure metrics are diagnostics only;
the preview never owns business state or decides counts. USB reopen attempts
may be automatic only under an explicit per-run bound and must reset
tracker/crossing state before resuming. Phase 9.4 adds no recording, frame
history, persistence, networking, multiple cameras, per-dock pipeline,
calibration UI, Phase 10, or production-readiness claim.

### Phase 10

Store sessions and events in SQLite.

Authorized Phase 10 subphase:

* Phase 10.1 — Production Runtime Foundation.

* Phase 10.2 — Pig Detector Integration and Model Runtime Boundary.

* Phase 10.3 — Real-World Detector, Tracking and Counting Validation.

Phase 10.1 adds a synchronous, bounded supervision boundary over the existing
single shared camera/counting runtime. It may expose immutable heartbeats,
component health, process-memory samples, aggregate diagnostics, explicit
recoverable/fatal issues, and controlled camera/pipeline/preview restart. It
must not create another worker, queue, polling loop, camera, counter, detector,
or presentation state. Identity-resetting camera/pipeline restart is blocked
while the shared counting lane is occupied by default; preview restart remains
isolated. Thresholds are engineering configuration, not evidence of
production readiness. Phase 10.1 adds no SQLite persistence, detector, model,
training, pig validation, UI redesign, networking, Phase 10.2, or Phase 11.

Phase 10.2 adds an opt-in, explicitly configured local pig-model runtime over
the existing `LiveDetector` contract and one-worker shared-lane pipeline. Model
paths and weights remain local and ignored; public snapshots expose only
sanitized provenance and bounded scalar detector metrics. Concrete
Ultralytics/Torch/NumPy/OpenCV values remain inside adapters, target classes are
explicit, empty mode remains the default, and no model may download silently.
Phase 10.2 does not train a model, create a dataset, validate pig accuracy,
change Phase 7/8 rules, redesign Phase 9 UI, add workers/queues, persist data,
or begin Phase 10.3 or Phase 11.

Phase 10.3 authorizes only the three exact local videos listed in its phase
documentation and processes them in Video 1, Video 2, Video 3 order. It adds a
headless, offline, path-free validation/reporting boundary and reuses Phase 6
line candidates plus public Phase 10.2/Phase 5–7 contracts. Real inference is
hard-gated on one compatible ignored and untracked local model. Missing model
or ground truth must remain explicit `UNKNOWN` evidence; Video 3 is detection/
tracking stress only and is never counting-accuracy evidence. Phase 10.3 adds
no download, training, dataset, frame/media retention, UI, worker, queue,
storage, counting-rule change, Phase 10.4, or Phase 11 work.

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
3. Read `HOGFLOW_PROJECT_MEMORY.md`.
4. Inspect `INVENTION_LOG.md` if it exists.
5. Inspect `MARKET_RESEARCH.md` if relevant to the task.
6. Inspect the repository structure.
7. Inspect existing code relevant to the requested phase.
8. Inspect existing tests.
9. Identify the current roadmap phase.
10. Identify dependencies from previous phases.
11. Briefly state the intended changes.

Then:

12. Implement only the requested phase.
13. Add or update relevant tests.
14. Run relevant tests.
15. Run Ruff when configured.
16. Inspect the resulting diff.
17. Report files changed.
18. Report test results.
19. Report known limitations.
20. Identify the recommended next phase.

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

The original prototype concept models three sequential physical sections. The
authorized Phase 8.1 domain generalizes this into a variable number of ordered
sessions because a small or future unloading group must not require three empty
records.

Conceptual flow:

IDLE
→ SELECT SECTION
→ START SESSION
→ COUNTING
→ END SESSION
→ REVIEW RESULT
→ CONFIRM OR FLAG FOR REVIEW
→ COMPLETED

Only one session may be active at a time within one truck operation. Different
docks may each have one active truck operation and session independently.

A session should support:

* sequence number
* dock ID
* pig type
* start time
* end time
* AI count
* optional ground-truth count
* status

The initial system is semi-automatic.

The operator manually starts and ends section sessions.

Do not implement automatic gate, door, or section detection unless explicitly requested by a future approved phase.

Session-scoped counted tracker IDs must not leak into a new session.

Phase 8.1 does not import Phase 7. Phase 8.2 connects them through the
application-oriented `sessions` package: every started unloading session owns
one fresh Phase 7 lifecycle, completed lifecycle totals transfer exactly once,
and cancelled lifecycle totals are discarded. Domain and counting packages
must not depend back on this integration layer.

Phase 8.4 aligns Phase 8.3 to the physical workflow: the same application
package composes four operational dock records with one `SharedCountingLane`.
The lane owns the sole source and sole injected counter and creates a
short-lived Phase 8.2 service only for its active dock/session binding. It must
not duplicate aggregate or Phase 7 counting rules. A fresh session lifecycle
clears temporary tracker identity state; no second dock may count while the
lane is occupied.

---

## 12. Operator MVP UI rules

Phase 9 introduces the Operator MVP User Interface.

The terminal and technical logs remain available for development and diagnostics.

They should not be the normal operator interface after the Operator MVP UI exists.

The UI may use Streamlit or another simple compatible framework.

The UI must consume existing project modules.

The UI must not duplicate counting logic.

The UI must not directly increment the AI count.

Phase 9.1 is the authorized first subset. Phase 9.2 adds executable composition
and workflow safety. Phase 9.3 adds one shared-lane camera/file acquisition
worker and immutable camera/pipeline status through the public application
boundary. Phase 9.4 adds one latest-frame preview slot, UI-thread overlays,
bounded visual diagnostics, and bounded USB reopen. Phase 8 snapshots remain
authoritative for business state; the worker never invokes Tkinter and preview
failures never alter counting. Phase 9.4 contains no recording, frame history,
calibration/editor, last-event review workflow, persistence, network
integration, multiple cameras, per-dock pipeline, or Phase 10.

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

For every approved implementation or governance change, complete this
publication workflow unless the user explicitly withholds push authorization:

1. run the required tests and quality gates;
2. inspect scope, privacy, the diff, and project-memory impact;
3. update `HOGFLOW_PROJECT_MEMORY.md` when project knowledge changed;
4. create one descriptive commit;
5. push to the authorized branch;
6. verify local `HEAD` equals `origin/<authorized-branch>`;
7. report the SHA, message, branch, push result, and actual CI status.

Never claim that GitHub Actions is green without retrieving its result. Never
leave a local-only commit without stating that fact clearly.

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
