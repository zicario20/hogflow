# HogFlow Architecture Decisions

This lightweight decision record captures the current rationale for Phase 2 architecture choices. Decisions may change when evidence or an approved requirement provides explicit architectural justification.

## ADR-001 — Preserve approved Phase 1 modules during foundation work

Status: Accepted

### Context

The Phase 1 finite-segment counter and generic video integration are approved and tested. Moving them during foundational work would add migration risk without changing behavior.

### Decision

Phase 2.1 preserves the existing counting and video module paths, imports, tests, and command-line interface.

### Consequences

Architecture foundations are added around working code. Contract-based adaptation is deferred to Phase 2.3, after Phase 2.2 defines the relevant contracts.

## ADR-002 — Keep core counting independent from CV frameworks

Status: Accepted

### Context

Counting business rules need deterministic tests without an AI model, GPU, camera, or video.

### Decision

The `counting` package must remain independent from OpenCV, Ultralytics, Supervision, and video integration.

### Consequences

Counting logic remains portable and directly testable. Integration code is responsible for converting tracked observations into counting inputs.

## ADR-003 — Use standard-library logging

Status: Accepted

### Context

Phase 2.1 needs consistent logging setup but does not require structured-log infrastructure or another runtime dependency.

### Decision

Use Python's `logging` module with explicit entrypoint configuration and named library loggers.

### Consequences

Logging remains simple and dependency-free. Importing modules does not configure root logging, and future entrypoints must opt into configuration.

## ADR-004 — Use frozen dataclasses for initial settings

Status: Accepted

### Context

Only logging-level and top-level runtime settings have a current foundational purpose.

### Decision

Represent the initial settings with frozen, slotted dataclasses and validate them during construction.

### Consequences

Settings are explicit and immutable without adding Pydantic or configuration loaders. Feature-specific settings wait for the phase that needs them.

## ADR-005 — Delay detector and tracker contracts until Phase 2.2

Status: Accepted

### Context

Phase 2.1 defines boundaries, while the approved execution plan assigns interfaces and contracts to Phase 2.2.

### Decision

Detection and tracking packages contain responsibility documentation only in Phase 2.1.

### Consequences

No premature protocol is designed around untested assumptions. Existing Phase 1 integrations remain unchanged until the approved adapter work in Phase 2.3.

## ADR-006 — Separate operational domain from vision/counting

Status: Accepted

### Context

Future authorized workflows may require truck, grouping, weighing, configurable category, partial-load, and exception-event concepts. Those concerns are distinct from detection, tracking, and crossing geometry.

### Decision

Reserve a domain boundary for future operational metadata without implementing entities in Phase 2.1. Domain code must remain independent from CV frameworks and infrastructure packages.

### Consequences

Future operational concepts can evolve without contaminating the counting core. The current examples are generic future concerns, not universal workflow claims or implemented behavior.

## ADR-007 — Avoid speculative abstractions

Status: Accepted

### Context

Premature services, managers, factories, repositories, event buses, or dependency-injection layers would add maintenance cost before their responsibilities are known.

### Decision

Create only the packages and shared foundations required by Phase 2.1. Add abstractions later only when an approved phase has a concrete use for them.

### Consequences

The architecture remains small and auditable. Future changes may introduce additional structures when evidence and explicit requirements justify them.

## ADR-008 — Use one framework-neutral shared-model module for contracts

Status: Accepted

### Context

Video-source, detector, and tracker contracts need one canonical language. Placing shared models inside any one component package would force the other contracts to depend sideways or upward, while framework-owned image and result types would couple the architecture to an implementation.

### Decision

Phase 2.2 defines frozen, slotted `Frame`, `BoundingBox`, `Detection`, and `Track` dataclasses in `hogflow.models`. Contract packages depend on this module, and the shared-model module depends only on `core` for expected input-data errors. `Frame` uses immutable packed RGB bytes rather than a NumPy, OpenCV, Torch, or model-framework object.

### Consequences

Future adapters must convert private framework objects at their boundaries. Contract consumers receive immutable values and do not need a computer-vision dependency. The conversion cost and canonical RGB representation are explicit tradeoffs; Phase 2.2 makes no throughput or real-time guarantee.

## ADR-009 — Define component Protocols without pipeline execution

Status: Accepted

### Context

Phase 2.2 must make future detectors, trackers, and video sources replaceable, while pipeline execution and adaptation of the approved Phase 1 integration belong to Phase 2.3.

### Decision

Define one small `Detector` Protocol, one small `Tracker` Protocol, and one small `VideoSource` Protocol. Do not define an orchestrator, service, manager, factory, dependency-injection container, or pipeline runner.

### Consequences

The component boundaries can be tested independently of implementations. No user-visible workflow changes in Phase 2.2, and Phase 2.3 must supply adapters and composition without changing the contracts casually.

## ADR-010 — Use adapters for framework integration

Status: Accepted

### Context

Phase 2.2 contracts exchange only immutable HogFlow models, while OpenCV and Ultralytics require framework-specific arrays and result objects.

### Decision

Place concrete video, detector, and tracker integrations in `hogflow.adapters`. Convert framework objects to or from `Frame`, `Detection`, and `Track` only at adapter boundaries. Use the installed Ultralytics ByteTrack API with externally supplied detections so detection runs once per frame.

### Consequences

Framework objects do not leak into contracts, models, counting, or pipeline orchestration. Adapter tests can isolate dependencies with fakes. Concrete framework upgrades remain localized.

## ADR-011 — Keep the CLI as the composition root

Status: Accepted

### Context

The existing Phase 1 CLI already owns user configuration and output-path choices. A separate container, factory, or service locator would add infrastructure without another current consumer.

### Decision

Keep `hogflow.video.generic_counter` as a thin composition root that parses unchanged arguments, constructs concrete adapters, counter, pipeline, and output collaborators, and translates expected errors for CLI users.

### Consequences

Library modules remain independently testable and the command remains compatible. Another entrypoint can compose the same contracts later without changing the pipeline.

## ADR-012 — Preserve the Frame bytes contract despite conversion overhead

Status: Accepted

### Context

OpenCV decodes mutable BGR arrays and Ultralytics accepts arrays, while the approved `Frame` contract stores packed immutable RGB bytes.

### Decision

Preserve packed RGB bytes. Convert BGR to RGB in the source adapter and reconstruct detector input at the detector boundary. Do not weaken `Frame` to expose NumPy.

### Consequences

The framework-neutral contract remains stable and immutable. Phase 2.3 accepts measurable memory-copy and color-conversion overhead and makes no real-time performance claim.

## ADR-013 — Use synchronous orchestration for Phase 2.3

Status: Accepted

### Context

The generic pipeline needs deterministic sequential frame processing and has no demonstrated need for concurrency, buffering, or distributed execution.

### Decision

Use one small synchronous `GenericCountingPipeline`. Process one frame at a time, invoke each component once, forward immutable results through callbacks, and guarantee source cleanup.

### Consequences

Control flow and failure behavior remain explicit and directly testable. Async execution, queues, multiprocessing, streaming infrastructure, and general workflow abstractions remain outside scope.

## ADR-014 — Run source-only continuous integration

Status: Accepted

### Context

The repository needs repeatable validation on pushes and pull requests, while
all real videos, annotations, inventory outputs, model weights, and evaluation
artifacts are local-only data that must never enter GitHub Actions.

### Decision

Run CI on Ubuntu with Python 3.12, read-only repository permissions, the
repository's development installation, and source/synthetic quality gates only.
Do not upload media-bearing artifacts or access local dataset paths.

### Consequences

CI provides evidence that source code, synthetic tests, formatting,
compilation, and declared dependencies are healthy. It provides no evidence
about real pig-video quality, annotation quality, detector accuracy, tracking,
or counting.

## ADR-015 — Reuse the canonical bounding box through an explicit evaluation wrapper

Status: Accepted

### Context

HogFlow already has a validated framework-neutral `BoundingBox`, but detection
evaluation must distinguish pixel coordinates from normalized coordinates.
Duplicating box geometry would create two competing canonical representations.

### Decision

Use the existing `hogflow.models.BoundingBox` inside an immutable
`EvaluationBoundingBox` that adds an explicit coordinate-space value and the
additional validation required by evaluation.

### Consequences

Core coordinates stay canonical and framework independent. Evaluation APIs
cannot silently mix normalized and pixel boxes, and future adapters remain
responsible for coordinate conversion.

## ADR-016 — Use deterministic confidence-first one-to-one matching

Status: Accepted

### Context

Basic precision, recall, and F1 require reproducible assignment between
predictions and ground truth without introducing a partial or misleading mAP
implementation.

### Decision

Within each frame, evaluate predictions by descending confidence and then
stable prediction ID. Match each prediction to the unmatched same-class ground
truth with the highest qualifying IoU, breaking equal-IoU ties by stable ground
truth ID. Each endpoint may be matched at most once.

### Consequences

Duplicate predictions become false positives and repeated runs are
deterministic. The method supplies threshold-specific basic metrics only; it is
not mAP and does not prove detector quality.

## ADR-017 — Keep dataset selection metadata-only and path-private

Status: Accepted

### Context

Phase 4.1 must prepare a future detection dataset from Phase 3 inventory data
without decoding media or publishing private filenames and source references.

### Decision

Select only readable, explicitly authorized detection candidates without fatal
validation errors. Emit deterministic opaque clip IDs, decisions, criteria,
and rejection reasons; omit local paths, filenames, review notes, and source
references. Write plans only to ignored local workspaces.

### Consequences

Selection is reproducible without accessing video bytes and cannot turn a
counting-candidate label into a detector-performance claim. Authorized local
inventory data remains outside source control, and later annotation work must
resolve opaque IDs locally.
