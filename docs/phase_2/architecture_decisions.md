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

## ADR-018 — Use YOLO text as a framework-neutral local annotation format

Status: Accepted

### Context

Phase 4.2 needs one operational bounding-box format before real annotation can
proceed, but the annotation domain must not depend on Ultralytics or another
detector implementation.

### Decision

Use UTF-8 YOLO detection text with the single class `0 = pig`, normalized
coordinates, deterministic line ordering, and strict validation. Treat YOLO as
serialization only; immutable annotation models remain framework neutral.

### Consequences

Local annotation tools can exchange a simple established format without
coupling HogFlow domain code to a model family. Empty labels require an
explicit `verified_empty` status, and malformed or ambiguous labels fail
validation.

## ADR-019 — Split by source video and fall back to preparation-only plans

Status: Accepted

### Context

Adjacent frames from one video are highly correlated. The currently available
authorized source count may be too small for a defensible 70/20/10 experiment.

### Decision

Assign opaque source clip IDs, never frames, to dataset splits. Use
seed-controlled deterministic ranking. Below the configured minimum source
count, assign all clips to `preparation` and emit warnings instead of forcing
train, validation, and test.

### Consequences

Source leakage is prevented and small datasets are not presented as
statistically meaningful. More independent authorized sources may be required
before model evaluation.

## ADR-020 — Separate private source maps from sanitized preparation records

Status: Accepted

### Context

Local frame extraction must resolve opaque clip IDs to real files, while plans,
reports, tests, logs, and Git must not expose those paths or private names.

### Decision

Keep clip-to-path mappings in a separately ignored local source map. Split,
frame, extraction, manifest, and validation outputs retain only opaque IDs and
controlled annotation-workspace-relative paths.

### Consequences

Infrastructure can read authorized local videos without propagating source
information across boundaries. A lost source map must be recreated locally;
sanitized records deliberately cannot recover private paths.

## ADR-021 — Plan timestamps before optional local extraction

Status: Accepted

### Context

Direct frame dumping can create many adjacent duplicates and makes selection
hard to review before media is written.

### Decision

Create a deterministic metadata-only timestamp plan first. Run OpenCV seeking
only through an explicit extraction command, use opaque image names, and make
reruns idempotent while refusing mismatched overwrites.

### Consequences

Selection can be audited without decoding media. Extraction remains optional,
local, bounded, and separate from imports, installation, tests, and CI.

## ADR-022 — Define detector training as a replaceable contract

Status: Accepted

### Context

Phase 4.3 needs one baseline trainer without making the rest of HogFlow depend
on Ultralytics or a YOLO model family.

### Decision

Define one small framework-neutral `DetectorTrainer` Protocol using immutable
training configuration, prepared-dataset, training-output, and
validation-output models. Place Ultralytics loading, training, validation,
checkpoint handling, and result conversion in `YOLOBaselineTrainer` under the
adapter boundary.

### Consequences

Another detector family can replace YOLO by implementing the same contract.
Framework objects never enter training orchestration, reports, evaluation, or
the detector runtime contract. Synthetic tests inject a fake backend and never
download weights.

## ADR-023 — Reuse HogFlow metrics and namespace framework metrics

Status: Accepted

### Context

Ultralytics validation exposes precision, recall, and mAP, while Phase 4.1
already defines HogFlow's deterministic one-to-one precision, recall, F1, and
IoU evaluation.

### Decision

Require trainer adapters to return framework-neutral `DetectionFrame` values.
Run the approved Phase 4.1 evaluator over those values. Export framework
metrics under separate framework namespaces and make no HogFlow mAP claim.

### Consequences

Detector comparisons retain one independent HogFlow evaluation method.
Framework mAP may be recorded as a framework value but cannot be confused with
HogFlow metrics or counting-system evidence.

## ADR-024 — Keep training artifacts local with sanitized provenance

Status: Accepted

### Context

Reproducible training needs seed, configuration, dataset version, code version,
Git commit, checkpoint, metrics, and failure records. Real dataset paths and
outputs must remain local and private.

### Decision

Fingerprint the sanitized manifest, image checksums, and validated label
content. Record only opaque dataset/run IDs, model filename, output-relative
checkpoint path, package version, Git commit, and immutable configuration.
Store checkpoints, runs, framework caches, metrics, and reports under ignored
local output directories.

### Consequences

Local runs are auditable without publishing source filenames or absolute
paths. Reproducing a result still requires the independently retained local
dataset and checkpoint; Git contains neither.

## ADR-025 — Separate live acquisition from the Phase 2 video contract

Status: Accepted

### Context

The Phase 2 `VideoSource` contract represents finite, sequential video input
for the generic counting pipeline. A production-oriented camera source needs
explicit temporary-failure, interruption, reconnect, shutdown, and health
semantics that cannot be represented safely by an ambiguous `None` result.

### Decision

Define a small framework-neutral `CameraSource` contract in
`hogflow.streaming`. Each read returns an explicit status and an optional
immutable source frame. Keep the existing `VideoSource` contract unchanged for
backward compatibility.

### Consequences

Live acquisition can distinguish file EOF from temporary or fatal camera
conditions without changing Phase 1 or Phase 2 behavior. Future consumers can
adapt `FramePacket` values deliberately, while camera infrastructure remains
independent of detection, tracking, and counting.

## ADR-026 — Use immutable RGB packets and monotonic stream ordering

Status: Accepted

### Context

OpenCV produces mutable BGR arrays, but the streaming boundary must not expose
OpenCV or NumPy objects. Wall-clock adjustments also make civil time unsafe for
ordering a continuous stream.

### Decision

Copy acquired images into immutable packed RGB bytes before they leave an
adapter. Assign lifecycle-scoped sequence numbers and monotonic timestamps in
the runner. Retain a timezone-aware acquisition timestamp only as descriptive
metadata.

### Consequences

Stream packets are framework-neutral and safely retainable, and ordering does
not depend on wall-clock changes. The adapter incurs a color conversion and
copy; real-camera throughput remains unvalidated.

## ADR-027 — Bound latency with an explicit frame-drop policy

Status: Accepted

### Context

A live camera can produce frames faster than a downstream consumer. An
unbounded queue would convert consumer lag into increasing memory use and
minutes of stale video.

### Decision

Use a fixed-capacity, thread-safe in-memory buffer. Support `drop_oldest` and
`drop_newest`, defaulting to `drop_oldest` so a future real-time consumer sees
recent frames. Expose submitted, delivered, dropped, depth, maximum-depth, and
sequence-gap statistics.

### Consequences

Memory and latency remain bounded at the cost of intentionally discarded
frames. Drops are observable and must not be mistaken for complete frame
delivery.

## ADR-028 — Use synchronous acquisition with deterministic reconnection

Status: Accepted

### Context

Phase 5.1 needs continuous acquisition and optional producer/consumer
separation, but no distributed stream framework, asynchronous application, or
inference scheduler is required.

### Decision

Implement a synchronous `LiveStreamRunner` with an optional single producer
thread. Use configurable bounded exponential backoff for live-source
reconnection, injectable monotonic clock and sleep functions for deterministic
tests, and never reconnect a development file after normal EOF. On requested
shutdown, allow the producer a short cooperative read-completion period before
falling back to cross-thread source close for a genuinely blocked read.

### Consequences

Lifecycle, shutdown, and reconnect behavior remain small and testable without
physical cameras. Backend blocking-read interruption remains best effort and
must be validated with each real camera/backend combination later.

## ADR-029 — Keep camera locators runtime-only and expose opaque identities

Status: Accepted

### Context

RTSP locators may contain usernames, passwords, hosts, ports, and private
deployment paths. Dataclass representations, logs, exceptions, and diagnostic
reports can accidentally disclose those values.

### Decision

Store locators in a protected runtime wrapper whose string and representation
contain only source type and opaque stream ID. Public models, health reports,
statistics, and CLI output use `StreamIdentity`; adapter exceptions use static
sanitized messages.

### Consequences

The normal public surface does not serialize camera secrets or private paths.
Callers remain responsible for supplying and protecting runtime credentials;
Phase 5.1 does not add a credential manager.

## ADR-030 — Add a lifecycle-aware live detector port without changing the finite-video contract

Status: Accepted

### Context

The approved Phase 2 `Detector` receives a finite-video `Frame` through one
`predict` call. Phase 5.2 needs explicit local model loading, sanitized artifact
metadata, inference over `FramePacket`, and deterministic cleanup while
preserving the older contract and Phase 1 behavior.

### Decision

Keep `Detector` unchanged. Add the small framework-neutral `LiveDetector` port
with `load`, `metadata`, `infer`, and `close`. Require immutable
`FrameDetections` to preserve source ID, sequence, dimensions, timestamps, and
model identity. Keep the interface serial and make no thread-safety guarantee.

### Consequences

Finite-video compatibility remains intact while live model lifecycle is
explicit. Future detector frameworks can replace Ultralytics through one
adapter. Two contracts exist for genuinely different finite and continuous
lifecycles, so callers must choose the appropriate composition root.

## ADR-031 — Reuse the source buffer as the only inference backlog

Status: Accepted

### Context

Camera acquisition can outrun detector inference. A second unbounded queue
would increase memory and frame age even though Phase 5.1 already supplies a
fixed-capacity real-time boundary.

### Decision

Run acquisition independently and let `LiveDetectionPipeline` drain currently
available source packets before each inference, retaining only the newest
useful frame. Support every-N, target-FPS, and maximum-age gates without
sleeping in or blocking acquisition. Count source-buffer drops separately from
inference-stage skips and failures.

### Consequences

Memory and backlog remain bounded, and recent camera state is prioritized over
historical completeness. Not every acquired frame is inferred. Camera and
inference stages have separate accounting invariants rather than one
misleading cross-stage equality.

## ADR-032 — Require explicit local artifacts and structural provenance

Status: Accepted

### Context

Ultralytics accepts model nicknames that may trigger downloads. A loaded model
also does not by itself establish that its classes, dataset, evaluation, or
purpose are appropriate for pig detection.

### Decision

Accept only an existing local model file, calculate its SHA-256 fingerprint,
validate the pig class mapping, and optionally validate a matching local
provenance record. Expose only the artifact filename, hash, opaque identifiers,
class mapping, and known metadata. Label provenance as structurally complete,
not as detector-quality validation. Never infer missing provenance.

### Consequences

Phase 5.2 cannot silently download a generic model or call it a pig detector.
Real pig inference remains blocked until an appropriate local artifact exists.
The local model and provenance files remain ignored and independently managed.

## ADR-033 — Keep preview optional, local, and failure-isolated

Status: Accepted

### Context

Local diagnostics benefit from boxes and telemetry overlaid on current frames,
but GUI behavior must not enter the domain, become required in headless CI, or
compromise camera/detector cleanup.

### Decision

Define a small framework-neutral preview port and one OpenCV adapter. Disable
preview by default, prohibit persistence, and interpret q/Escape as a
cooperative stop request. If preview fails, record the failure, close the
window, and continue headless inference.

### Consequences

Headless operation and framework boundaries remain intact. Preview failure is
observable but does not become a camera or detector failure. The preview is a
local diagnostic, not an operator UI or remote service.

## ADR-034 — Add a lifecycle-aware live tracker without replacing the finite-video contract

Status: Accepted

### Context

The Phase 2 `Tracker` contract supports finite generic video integration, but
live tracking requires explicit startup, stream binding, reset, reconnect, and
cleanup semantics. Changing the approved finite-video contract would risk
Phase 1 and Phase 2 compatibility.

### Decision

Keep `Tracker` unchanged. Add a small framework-neutral `LiveTracker` contract
whose instance is bound to one opaque stream lifecycle and exposes `start`,
`update`, `reset`, and `close`. Reuse canonical `Detection` and `Track` models
inside immutable live request and result wrappers.

### Consequences

Live resources and temporary identity state have explicit ownership without
altering the finite-video pipeline. Track IDs remain lifecycle-scoped and may
be reused after reset; they are not permanent animal identities or counts.

## ADR-035 — Use one tracker instance per stream lifecycle

Status: Accepted

### Context

Stateful multi-object trackers can mix identities if one backend instance
receives detections from unrelated cameras. A global stream-keyed registry
would also need abandonment and cleanup policy beyond this phase.

### Decision

Bind each live tracker instance to exactly one stream ID and reject cross-stream
requests. A pipeline owns that instance for one source lifecycle. Reset the
instance after an observed source reconnect; use another instance for another
stream or a new pipeline lifecycle.

### Consequences

Stream state cannot leak accidentally, cleanup remains explicit, and no
unbounded tracker registry is introduced. Future multi-camera orchestration
must compose independent pipeline/tracker pairs.

## ADR-036 — Track serially after latest-useful-frame detection

Status: Accepted

### Context

Phase 5.2 already bounds latency by keeping the Phase 5.1 source buffer as the
only backlog. Adding an independent tracking queue could retain stale detection
results and complicate exact frame association and shutdown.

### Decision

Run tracking synchronously in the successful detector-result callback. Keep
the original source ID and frame sequence in every request and result. Do not
invoke tracking after detector failure, and do not fabricate intermediate
detections for source frame gaps.

### Consequences

There is no additional unbounded queue, stale detections cannot be applied to
newer frames, and detector/tracker failures remain distinct. Slow tracking can
reduce inference throughput while acquisition continues to follow the source
buffer's documented drop policy.

## ADR-037 — Isolate the installed Supervision ByteTrack API behind one adapter

Status: Accepted

### Context

The installed and pinned `supervision==0.29.1` exposes ByteTrack through
`update_with_detections` and `reset`, but marks that bundled class deprecated
for removal in 0.30. Domain code must not depend on that unstable API.

### Decision

Use a lazy-loading `SupervisionByteTrackAdapter` that accepts only HogFlow
tracking requests, calls the verified 0.29.1 API, and returns only HogFlow
tracking results. Expose only constructor fields actually supported by that
version. Keep framework objects private and document migration as technical
debt.

### Consequences

Phase 5.3 has a usable real tracker adapter without coupling the domain or
pipeline to Supervision. A future dependency upgrade may replace this one
adapter while preserving contracts, tests, and orchestration.
