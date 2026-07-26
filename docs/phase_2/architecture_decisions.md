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

## ADR-038 — Interpret ByteTrack timing in successful tracker updates

Status: Accepted

### Context

The Phase 5.2 latest-frame policy may omit camera frames before detection, so
source sequence numbers can contain gaps. Supervision 0.29.1 increments its
internal frame counter once per tracker update and derives
`max_time_lost = int(frame_rate / 30 * lost_track_buffer)`. Treating camera FPS
as tracker FPS or fabricating updates for sequence gaps would misrepresent the
actual adapter calls.

### Decision

Keep the current contracts and serial pipeline. Define
`ByteTrackConfiguration.frame_rate` as the expected frequency of successful
tracker update calls. Treat `lost_track_buffer` as Supervision's 30-FPS
reference value, converted by that expected update rate into internal update
steps. Preserve source sequence gaps exactly and never synthesize intermediate
detections or tracker updates. Reset timing and identity state after reconnect.

### Consequences

The adapter remains simple, deterministic, and truthful about work performed.
Deployments must configure the expected update rate from measured inference and
tracking throughput; a mismatch changes wall-clock retention. Representative
occlusion and gap behavior remains an empirical validation requirement.

## ADR-039 — Separate live crossing events from the Phase 1 counter

Status: Accepted

### Context

Phase 1 combines finite-segment crossing events with positive-direction
deduplication and accumulated count state. Phase 5.4 is authorized to emit
geometric live events only; Phase 7 still owns reverse and unique-count rules.

### Decision

Add a separate lifecycle-aware `VirtualLineCrossingDetector` that consumes
immutable `TrackingResult` values and emits immutable `LiveCrossingEvent`
values. Reuse the proven finite-segment and near-line concepts, but do not
reuse `DirectionalLineCounter`, `counted_tracker_ids`, or accumulated totals.

### Consequences

The Phase 1 workflow remains compatible, while the live pipeline can observe
both geometric directions without silently implementing Phase 7. A crossing
event is not a pig count.

## ADR-040 — Use normalized finite geometry and bottom-center anchors

Status: Accepted

### Context

Live camera resolutions may differ, full-box centers are weaker ground-plane
proxies, floating-point jitter occurs near a line, and the historical Phase 1
infinite-extension defect must not recur.

### Decision

Configure one oriented finite segment with normalized endpoints. Classify
normalized representative points by signed perpendicular distance and explicit
epsilon; use `BOTTOM_CENTER` by default and support `CENTER` only as a simple
alternative. A side transition emits an event only when the segment between
the two real stable observations intersects the configured finite line
segment. No intermediate frame, timestamp, trajectory, or crossing point is
created.

### Consequences

Geometry is resolution-independent and endpoint reversal predictably reverses
side and direction. Large sequence gaps preserve uncertainty: the current
frame is the observable event time, not an estimated crossing time.

## ADR-041 — Compose live crossing serially and reset it with tracking

Status: Accepted

### Context

Phase 5.3 already runs tracking serially after latest-useful-frame detection
and resets temporary IDs after reconnect. A second queue could misassociate
tracking results and crossing state; reused tracker IDs could inherit a prior
side if crossing state were not reset.

### Decision

Keep the Phase 5.3 path unchanged when crossing is disabled. When explicitly
enabled, `LiveCrossingPipeline` composes `LiveTrackingPipeline`, processes
crossing in its successful-result callback, and mirrors every reported tracker
reconnect reset before the next crossing update. Qualify events with a crossing
lifecycle identifier. Treat configuration, lifecycle, stale-result, contract,
and geometry failures as fatal for that run; isolate preview failures.

### Consequences

There is still one bounded source buffer and no crossing queue or frame
history. A reconnect cannot leak remembered sides, but no cross-lifecycle
biological re-identification or deduplication exists.

## ADR-042 — Evaluate line candidates offline with isolated crossing lifecycles

Status: Accepted

### Context

Phase 6 must compare several line configurations against exactly the same
tracking observations. Evaluating candidates inside the live pipeline would
couple evidence collection to camera scheduling and could allow one
candidate's side state to contaminate another.

### Decision

Add a serial offline evaluator under `hogflow.evaluation`. It depends inward
on immutable tracking results and the Phase 5.4 crossing detector. Every
candidate receives a fresh `VirtualLineCrossingDetector`, processes the same
canonical replay, and closes in a `finally` block. No candidate state is
shared, and candidate input order is canonicalized by opaque ID.

### Consequences

Results are deterministic and auditable without camera, detector, tracking
framework, media, or internet. `evaluation` may now depend on
framework-neutral `counting` and `tracking` models; neither package depends
back on evaluation. The live line is never selected or changed automatically.

## ADR-043 — Use strict path-free JSON replays and reports

Status: Accepted

### Context

Offline evaluation needs reproducible tracking input, but Python pickle,
framework objects, image payloads, source paths, and private filenames are
unsafe or unnecessary. Existing Phase 4 serializers do not represent live
`TrackingResult` sequences and crossing-event ground truth.

### Decision

Define schema-versioned JSON for candidate plans and tracking replays. Replays
contain only opaque source/lifecycle IDs, aware timestamps, frame dimensions,
canonical tracked boxes, temporary tracker IDs, sanitized provenance, and
optional independent ground-truth crossing events. Reports contain aggregate
results, bounded matches, fingerprints, warnings, and limitations. Loading is
strict; writing is atomic and deterministic for identical values.

### Consequences

Phase 6 inputs can be inspected and tested without executing content or
decoding media. Absolute paths, frames, images, credentials, and private source
references are excluded. Real replay/report files remain local under existing
Git protections.

## ADR-044 — Gate recommendations on crossing-event ground truth

Status: Accepted

### Context

Event volume alone cannot identify the correct virtual-line position. Synthetic
or representative tracking without independent crossing labels can describe
behavior but cannot establish accuracy. Ground-truth matching must remain
simple, deterministic, and dependency-free.

### Decision

Default to `NO_AUTOMATIC_RECOMMENDATION`. With ground truth, match predicted and
reference events one-to-one using deterministic greedy minimum frame distance,
optional direction agreement, and stable identity tie-breaks. Support explicit
ranking by event F1, absolute event-count error, or mean frame offset. Without
ground truth, return no recommended candidate.

### Consequences

Reports cannot silently select the line with the most events. Synthetic
ground-truth ranking is labeled as specific to that replay. The greedy matcher
is auditable but not globally optimal, so that limitation is preserved in
every report.

## ADR-045 — Diagnose endpoint proximity without changing event emission

Status: Accepted

### Context

Phase 5.4 uses finite segments, so short or poorly placed candidates may emit
events near an endpoint. Comparing only total events would hide that
sensitivity.

### Decision

Expose the existing finite movement intersection's normalized line parameter
through `NormalizedLine`. Phase 6 converts that parameter to normalized
distance from the nearest endpoint and records an aggregate diagnostic. It
does not change the Phase 5.4 event decision or estimate an intermediate frame,
timestamp, or trajectory.

### Consequences

Short and long lines can be compared with explicit endpoint evidence while
geometry remains centralized in Phase 5.4. Endpoint proximity remains a
diagnostic, not a business rule or automatic line adjustment.

## ADR-046 - Qualify Phase 7 identities by source and crossing lifecycle

Status: Accepted

### Context

A numeric tracker ID is temporary, may be reused after reconnect/reset, and
does not identify one biological animal globally. Phase 5.4's historical
`tracker_lifecycle_id` field actually identifies its crossing-detector
lifecycle.

### Decision

Define `TemporaryTrackIdentity` as `(source_id, crossing_lifecycle_id,
tracker_id)`. Preserve the Phase 5.4 field for compatibility and expose a clear
`crossing_lifecycle_id` alias. Give Phase 7 state a distinct
`counting_lifecycle_id`. Reset Phase 7 whenever Phase 5.4 emits a new crossing
lifecycle; never combine totals across those lifecycles.

### Consequences

The same numeric tracker ID may contribute once in separate lifecycles without
state leakage. Reconnect may still allow the same physical animal to contribute
again because HogFlow has no biological re-identification or session policy.

## ADR-047 - Use first-positive counting without reverse decrement

Status: Accepted

### Context

Phase 5.4 emits neutral directional events. Phase 7 must make every event
auditable while preventing repeated positive crossings from incrementing
again. A reverse event alone does not prove permanent departure or justify
changing a prior total.

### Decision

Configure one explicit geometric positive direction. The first positive event
for a lifecycle-qualified identity increments once. Later positive events are
`IGNORED_DUPLICATE_POSITIVE`. Opposite-direction events are
`IGNORED_REVERSE`; they never decrement and never remove an identity from the
counted set.

### Consequences

Behavior is deterministic and conservative within one lifecycle. ID switches
or fragmentation can overcount, while inappropriate ID reuse can undercount.
There is no net count, correction policy, session count, or biological
deduplication.

## ADR-048 - Apply Phase 7 frames atomically in the serial live path

Status: Accepted

### Context

One crossing result may contain events for several tracks. Partially applying a
frame before discovering invalid provenance would corrupt the lifecycle total.
Evicting counted IDs to limit memory would silently permit duplicates. Adding a
counting queue would weaken exact frame correspondence.

### Decision

Validate every event, canonicalize by tracker ID, calculate decisions against a
prospective identity set, validate the complete immutable result, and only then
commit state. Keep counted IDs for the entire lifecycle. Bound them by an
explicit capacity that fails the whole frame instead of evicting. Compose
`LiveCountingPipeline` serially in the Phase 5.4 callback with no new queue.
Treat core counting failures as fatal and preview failures as non-fatal.

### Consequences

Frame updates are all-or-nothing, duplicate suppression survives temporary
misses, memory has a hard limit, and the Phase 5.1 buffer remains the only
queue. Deployments must size capacity for a lifecycle; reaching it stops the
run safely rather than returning a misleading partial count.

## ADR-049 - Keep Phase 8.1 unloading operations in the pure domain

Status: Accepted

### Context

Phase 8.1 needs operational docks, truck operations, and unloading sessions,
but Phase 7 integration, persistence, networking, and UI are later concerns.
Putting these entities in `counting`, `pipeline`, or a concrete service would
couple operational rules to live computer vision before the integration
contract is approved.

### Decision

Implement Phase 8.1 in `hogflow.domain` using frozen, slotted dataclasses and
explicit domain errors. The package may depend only on `hogflow.core` and the
standard library. Phase 8.1 imports no Phase 7, camera, pipeline, persistence,
network, or UI type.

### Consequences

Truck and session rules remain deterministic and testable without models,
camera, database, or live counts. Phase 8.2 must introduce an explicit
application boundary rather than making the domain depend on Phase 7.

## ADR-050 - Use variable ordered sessions and copy-on-write transitions

Status: Accepted

### Context

The physical workflow commonly has three gate sections and roughly 60 pigs per
section, but small and mixed trucks require different session quantities.
Mutable entities would also make partial failure and caller-owned collection
leaks harder to audit.

### Decision

Model a variable tuple of single-pig-type sessions with positive unique
sequence numbers and no maximum. Additions are allowed only while the
operation is planned. One session may be active per operation; lower-sequence
sessions must be terminal before a later one starts. Every transition returns
a new aggregate after full validation.

### Consequences

One, two, three, and more-than-three-session operations are valid. Neither 60
pigs nor three sessions is enforced. Failed additions and transitions preserve
the prior value without rollback machinery.

## ADR-051 - Model four independent current dock occupancies without history

Status: Accepted

### Context

Four physical docks may unload different trucks simultaneously. Phase 8.1
requires occupancy isolation but does not authorize persistence, concurrent
command handling, or broader orchestration.

### Decision

Use one immutable `DockOperationRegistry` holding at most one current
`TruckOperation` record per `DockId`. A non-terminal operation occupies its
dock. Completion or cancellation makes the dock available, and registering a
new planned operation replaces the prior terminal current record.

### Consequences

Dock state cannot leak and occupancy failures are atomic. The registry is not
an audit log; replacing terminal records loses in-memory history by design.
Phase 10 remains responsible for persistence, and concurrency remains outside
Phase 8.1.

## ADR-052 - Coordinate one session and one Phase 7 lifecycle in the application layer

Status: Accepted

### Context

Phase 8.1 owns immutable unloading rules while Phase 7 owns temporary identity,
positive direction, reverse handling, duplicate suppression, capacity, and
counting lifecycle state. Importing Phase 7 into the aggregate would make
domain transitions depend on live processing. Importing sessions into counting
would reverse the established dependency direction. A runtime manager for all
four docks would also introduce Phase 8.3 concerns.

### Decision

Implement `UnloadingSessionCountingService` under `hogflow.sessions` for one
`TruckOperation`. The service consumes only immutable Phase 8.1 values and the
public `LiveDirectionalCounter` protocol. It binds one active session to one
crossing/counting lifecycle, tracks only the latest validated Phase 7 total,
closes the counter before committing terminal domain state, and retains one
bounded immutable finalization record per coordinated session.

Reuse one owned counter sequentially so Phase 7 lifecycle generations remain
distinct. Reset current lifecycle telemetry gauges on every fresh Phase 7
start; preserve aggregate diagnostics. Reject prior crossing or counting
lifecycle IDs, and reject a reconnect lifecycle change inside an active session
rather than silently combine totals.

### Consequences

Domain and counting remain independent, sequential sessions cannot share
temporary identity state, and completion transfers one finalized total exactly
once. Cancellation discards unfinished counting. A failed counter close leaves
the immutable domain unchanged. The service deliberately does not coordinate
simultaneous docks, persist results, run cameras, or aggregate reconnect
lifecycles; those require later explicit phases.

## ADR-053 - Coordinate four docks synchronously with one owned service and counter each

Status: Accepted

### Context

Phase 8.1 models four independent current dock occupancies and Phase 8.2 binds
one operation's sessions sequentially to one Phase 7 counter. Phase 8.3 must
coordinate all four without moving rules into a second aggregate, sharing
counter state, guessing result ownership, or introducing unrequested
concurrency infrastructure.

Separate Phase 7 counter instances generate lifecycle IDs in their own local
scope by default. Merely creating four counters therefore does not prove that
their active lifecycle provenance is globally unique.

### Decision

Implement `MultiDockRuntimeCoordinator` in the `hogflow.sessions` application
layer. Keep one private runtime record per current dock, with one explicit
source, injected counter, and Phase 8.2 service. Route every command by typed
`DockId`; never scan docks to infer ownership.

Validate source ownership and active/finalized crossing/counting lifecycle IDs
across all current runtimes. Extend Phase 8.2 startup with an optional
pre-commit lifecycle validator so a global counting-ID collision closes the
prospective counter without committing the immutable session transition.
Require the injected counter factory to provide distinguishable lifecycle IDs;
reject collisions rather than rewriting Phase 7 provenance.

Keep the coordinator synchronous and caller-serialized. Expose immutable
Dock 1–4 snapshots and derived finalized totals, while keeping live session
counts separate. Terminal current records remain readable and are replaced by
the next registration, preserving the Phase 8.1 no-history policy.

Global shutdown attempts every runtime. Active sessions are cancelled through
Phase 8.2, unfinished totals are discarded, trucks are not completed or
cancelled automatically, and close failures are aggregated. Commands are
rejected after shutdown.

### Consequences

Dock operations, counters, tracker identities, current totals, lifecycle
provenance, and failures remain isolated. The same numeric tracker ID may
contribute independently at different docks because Phase 7 source/lifecycle
scope remains authoritative. A local error does not create a global runtime
failure.

The coordinator is not thread-safe and does not run cameras. The factory must
construct counters with globally distinguishable lifecycle identities.
In-memory terminal history is bounded to one current record per dock, and
shutdown of active work is a cancellation boundary requiring external recovery.
UI, persistence, camera orchestration, and true concurrent ingestion remain
later phases.

## ADR-054 - Align four operational docks to one shared counting lane

Status: Accepted; supersedes ADR-053 counter/source ownership

### Context

Phase 8.3 was correct under its original assumption that each unloading dock
was also a counting location. Updated operational information establishes a
different physical topology: four docks feed one approximately 1.5-metre-wide,
20-metre-long corridor, and one camera near the scale entrance performs all
automatic counting. Dock state remains independent, but counter state is a
mutually exclusive physical resource rather than a per-dock resource.

Keeping one counter per dock would model cameras and simultaneous counting
that do not exist. Moving counting state into the domain would break the
Phase 8.1/8.2/7 dependency boundaries.

### Decision

Introduce `SharedCountingLane` in the `hogflow.sessions` application layer.
It owns one explicit source, one injected public `LiveDirectionalCounter`, and
at most one active dock/operation/session binding. `MultiDockRuntimeCoordinator`
continues to own four current dock operations but no dock-owned counter,
source, or service. Starting a session binds the idle lane; completing or
cancelling it releases the lane.

Create a short-lived `UnloadingSessionCountingService` for each binding. Permit
that service to adopt a strictly validated tuple of prior terminal lifecycle
provenance so earlier session totals and lifecycle reuse protection survive
release. The same shared Phase 7 counter starts a fresh lifecycle for each
session and therefore resets temporary counted identities.

Keep coordination synchronous and caller-serialized. Preserve the
`register_operation(..., source_id=...)` argument only as an optional migration
check against the shared source; it no longer creates dock source ownership.

### Consequences

Exactly one active unloading session can receive automatic counts. Four truck
operations may remain planned or active independently, but a second session
cannot take the occupied lane or silently change its dock. Live count,
crossing/counting lifecycle, source, and temporary tracker identity state have
one owner.

Completion/cancellation/shutdown release the lane without fabricating counts.
A counter-close failure preserves the active binding and immutable domain
state for explicit recovery. Current snapshots expose zero or one active
session globally and keep live count separate from finalized totals.

ADR-053 remains historical documentation of Phase 8.3 but its per-dock
counter/source factory is no longer the current architecture. Multiple
physical lanes, camera acquisition, concurrency, scheduling, persistence, and
UI remain outside Phase 8.4.

## ADR-055 - Keep the first operator UI snapshot-driven and stateless

Status: Accepted

### Context

Phase 8.4 exposes the complete current four-dock and shared-lane read model
through immutable snapshots and all permitted transitions through public
coordinator methods. A presentation-owned mirror, direct aggregate mutation,
or UI-owned count would create a second source of truth. Camera, persistence,
polling, and production UI concerns are not authorized in Phase 9.1.

### Decision

Add a small `hogflow.application` boundary that translates immutable operator
commands into public `MultiDockRuntimeCoordinator` calls and always returns a
fresh snapshot. Add `hogflow.presentation` above it with immutable display
models, a presenter, and a lazy Tkinter desktop adapter.

The presenter owns no snapshot cache. Live count comes directly from
`SharedCountingLaneSnapshot.current_session_count`, while finalized totals
come directly from the aggregate snapshot. Expected domain/application errors
are displayed and remain observable. Manual refresh is the only refresh
mechanism.

Require the application composition root to inject the crossing-lifecycle ID
factory. The desktop does not open or infer camera/pipeline lifecycle state.

### Consequences

The four dock panels, single lane owner, actions, live count, and finalized
totals can be exercised headlessly without moving Phase 7/8 rules into UI.
Tkinter is optional at runtime and absent from import-time behavior.

The Phase 9.1 desktop cannot acquire frames, update live counts by itself,
poll, persist, or recover across restart. A future explicitly authorized
composition must connect camera lifecycle provenance without weakening this
boundary.

## ADR-056 - Derive operator safety from snapshots and compose resources once

Status: Accepted

### Context

Phase 9.1 exposed valid commands but left every Tkinter button enabled and
required callers to construct the full runtime. That allowed avoidable
operator mistakes and meant `python -m hogflow` was not executable. Copying
Phase 8 rules into presentation or retaining a mutable UI mirror would violate
ADR-055. Camera composition remains explicitly out of scope.

### Decision

Keep Phase 8 authoritative and add only read-only workflow projections to
`DockRuntimeSnapshot`: the next planned session/pig type and booleans stating
whether the operation may start a session or complete. Derive all selected-dock
button states from the latest `MultiDockRuntimeSnapshot`; never cache the
snapshot or duplicate transitions in Tkinter.

Require presentation confirmations before cancelling a session, cancelling a
truck, or exiting with non-terminal work. The presenter requests confirmation,
then delegates the transition to `OperatorApplicationService`. Shutdown uses
the existing coordinator close contract: an active session is cancelled and
its unfinished live count discarded; a truck is not fabricated as complete.

Add one uppermost `hogflow.bootstrap` composition root. It creates one enabled
Phase 7 counter, one shared lane, the coordinator, application, presenter, and
one Tkinter view. Because camera integration is forbidden in Phase 9.2, the
executable uses an explicitly named no-camera crossing fingerprint and local
opaque lifecycle IDs. They are not camera provenance and cannot support real
crossing input. A future camera composition must replace both explicitly.

### Consequences

`python -m hogflow` and `hogflow run` launch a complete manual-refresh desktop.
Controls communicate the next valid selected-dock action; destructive actions
explain discarded state; lane ownership is textual and not color-only.

The composition root may import inward from counting, sessions, application,
and presentation, but lower layers do not import it. No camera, CV framework,
polling, timer, thread, network, persistence, authentication, scheduling, or
hardware dependency is introduced. Executable operation remains in-memory and
does not validate plant usability or pig-count accuracy.

## ADR-057 - Use one shared camera worker and one serialized lane gateway

Status: Accepted

### Context

Phase 8.4 established one physical corridor, one source, and one Phase 7
counter shared by four dock business contexts. Phase 9.2 deliberately composed
no camera. Camera acquisition and detector/tracker work cannot block Tkinter,
but the shared lane and multi-dock coordinator are caller-serialized. Reusing
`LiveCountingPipeline` directly would create a second Phase 7 counter and
violate the shared-lane ownership rule.

### Decision

Add one application-level `CountingPipelineController` with one controlled
non-daemon worker. The worker owns source acquisition and serial
detector/tracker/crossing processing. It routes only immutable
`LiveCrossingResult` evidence to `SharedCountingLane`; that lane remains the
sole counter owner.

Add `SerializedMultiDockRuntimeAccess` as the single mutation/read gateway for
operator commands, lane-binding snapshots, and camera evidence. Expensive
computer-vision work runs outside its lock. Before routing, the gateway
revalidates the exact dock, source, and crossing lifecycle captured for the
frame. A delayed result is stale evidence and cannot increment a later session.

Permit `VirtualLineCrossingDetector` to receive an optional lifecycle-ID
factory so camera crossing provenance can exactly match the active Phase 8
session. Its existing generated lifecycle IDs remain the default, preserving
Phase 5.4 compatibility.

The executable composition uses existing empty detector/tracker adapters by
default. This validates acquisition, lifecycle, shutdown, and routing
infrastructure without fabricating pig detections. A validated local detector
can be injected through the same public contracts in a separately authorized
configuration.

### Consequences

Exactly one source, worker, detector, tracker, crossing detector, and shared
counter exist in the executable composition. Docks remain independent
business contexts and never own computer-vision resources. Tkinter is never
called from the worker, and imports/help do not open a source.

There is no queue or unbounded frame history in this orchestration: the worker
processes one acquired frame at a time. Manual UI refresh remains authoritative
for display. Physical camera behavior, pig-specific detection, calibrated line
placement, preview, reconnect loops, and production concurrency remain
unvalidated or out of scope.

## ADR-058 - Use one replaceable visual slot and UI-thread rendering

Status: Accepted

### Context

Phase 9.3 deliberately keeps camera, detector, tracker, crossing, and Phase 8
routing on one worker outside Tkinter. Phase 9.4 must expose current video and
diagnostics without allowing a slow renderer to create backlog, call Tkinter
from the worker, retain frame history, or become a second counting path. Live
USB interruption also needs bounded recovery rather than an endless reconnect
loop.

### Decision

Add one framework-neutral `LatestPreviewFrameChannel` with exactly one
replaceable frame slot. The camera processor publishes immutable RGB24 and
vector-overlay values after successful tracking; publication never waits for
consumption. The Tk thread alone consumes and renders the current slot through
the public application boundary. It maintains one cancellable 200 ms
`root.after` callback and no presentation worker.

Treat visual preparation and rendering as optional failure-isolated work.
Rendering failure disables preview for that run while camera/counting
continues. Keep business snapshots separate from visual frames.

For USB sources only, allow a validated per-run `CameraRecoveryConfiguration`.
After a bounded number of temporary failures, clear the visual slot, close the
source, reset tracker/crossing state, and attempt at most the configured number
of reopens. Never reopen a normally exhausted file, fabricate frames, change
the Phase 8 session binding, or reset the Phase 7 session count.

### Consequences

Preview memory remains bounded to one channel frame plus the one frame
currently rendered by Tk. Rendering cannot create acquisition backpressure,
and the worker never touches widgets. Source recovery is observable through
disconnected/opening/running states and aggregate attempt counters, and cannot
loop forever.

Resetting tracker state while retaining the active Phase 7 session lifecycle
does not solve identity continuity. Tracker-ID reuse after reconnect can still
cause undercount, while fragmentation/ID switches can cause overcount. Real
camera reopen, UI throughput, pig tracking, and count accuracy remain pending
empirical validation.
