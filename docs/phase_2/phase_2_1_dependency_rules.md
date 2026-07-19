# Phase 2 Dependency Rules

## Purpose

These rules define the dependency direction after Phase 2.3 integrates the
approved contracts with concrete generic adapters and a synchronous pipeline,
after Phase 3 adds local dataset-inventory infrastructure, after Phase 4.1
adds framework-neutral detection-evaluation infrastructure, and after Phase 4.2
adds local annotation-dataset preparation, and after Phase 4.3 adds the
replaceable baseline detector-training boundary. Phase 5.1 adds a
framework-neutral live-streaming domain and isolates camera frameworks inside
adapters. Phase 5.2 adds framework-neutral live detector ports/results and a
pipeline-level stream-to-detector orchestrator while keeping model and preview
frameworks in adapters. Phase 5.3 adds framework-neutral live tracker
ports/results and a serial detector-to-tracker composition while keeping
Supervision ByteTrack and OpenCV tracking preview code in adapters.
An arrow means that the module on the left may depend on the module on the
right.

Implemented direction:

* `adapters → contracts/models/core/config`
* `pipeline → contracts/models/counting/detection/streaming/core/config`
* `video CLI/output → adapters/pipeline/counting/config/core`
* `contracts → models → core`
* `counting → core/config` only when a concrete need exists
* `data models/validation → core`
* `video metadata infrastructure → data models/validation/core`
* `data inventory CLI → data models/validation/video metadata/core`
* `evaluation models/metrics → models/core`
* `evaluation dataset selection CLI → core`
* `annotation models/policy/YOLO/manifest → evaluation models/models/core`
* `data splitting/frame planning → annotation models/core/data`
* `frame extraction → data planning/annotation models/core/OpenCV`
* `annotation validation → annotation models/YOLO/manifest/core/OpenCV`
* `training contracts/models/configuration → annotation/evaluation/models/core`
* `training dataset/orchestration/reporting → annotation/evaluation/training models/core`
* `YOLO training adapter → training contracts/models/core/Ultralytics`
* `YOLO training CLI → YOLO adapter/training/core`
* `streaming models/contracts/buffering/health/lifecycle → core and standard library`
* `camera adapters → streaming/core/OpenCV`
* `camera diagnostics CLI → camera adapters/streaming/core`
* `live detection models/ports/telemetry → models/streaming/core`
* `live detection pipeline → detection/streaming/models/core`
* `live detector and preview adapters → detection/streaming/models/core/frameworks`
* `live detection CLI → camera/detector/preview adapters/pipeline/streaming/core`
* `live tracking models/ports/telemetry → detection/streaming/models/core`
* `live tracking pipeline → tracking/detection/streaming/models/core`
* `ByteTrack and tracking preview adapters → tracking/detection/streaming/models/core/frameworks`
* `live CLI with tracking → camera/detector/tracker/preview adapters/pipeline/streaming/core`

The current counting module remains independent from CV frameworks and does
not need config or core.

## Package rules

| Package | Responsibility | Allowed internal dependencies | Forbidden examples |
| --- | --- | --- | --- |
| `core` | Shared expected-error types and logging configuration. | Python standard library only. | `adapters`, `config`, `counting`, `data`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `config` | Explicit immutable foundational settings. | `core` | `adapters`, `counting`, `data`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `models` | Canonical immutable communication data. | `core` | `adapters`, `config`, `counting`, `data`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `counting` | Detector-independent counting rules and geometry. | `core` or `config` only with concrete need; currently neither. | `adapters`, `data`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, UI code, CV frameworks |
| `data` | Inventory models/discovery, source-level splitting, frame planning, local extraction, sidecar parsing, suitability, and reporting. | Framework-neutral planning: `annotation`, `core`, `data`; inventory: `core`, `video`; extraction: OpenCV | Adapters, counting, detector/tracker contracts, pipeline, sessions, storage, domain business logic; CV frameworks outside explicit metadata/extraction infrastructure |
| `evaluation` | Immutable detection-evaluation models, deterministic geometry/matching/metrics, and metadata-only local dataset selection. | `models`, `core` | Adapters, video decoding, detector/tracker implementations, pipeline, counting, sessions, storage, UI code, CV frameworks |
| `annotation` | Immutable pig annotation/manifest models, policy geometry, YOLO text serialization, sanitized manifests, and local structural validation. | Domain modules: `evaluation` models, `models`, `core`; validation infrastructure: OpenCV | Detector frameworks, adapters, tracking, counting, pipeline, sessions, storage, UI logic; CV frameworks in models, policy, YOLO, or manifest modules |
| `detection` | Framework-independent finite-video and live detector contracts, immutable live results, bounded telemetry, errors, and deterministic doubles. | `models`, `streaming`, `core` | Adapters, frameworks, video, tracking, counting, pipeline, storage, UI code |
| `tracking` | Framework-independent finite-video `Tracker` plus live tracker contracts, immutable requests/results, configuration, bounded telemetry, errors, and deterministic doubles. | `models`, `detection`, `streaming`, `core` | Adapters, frameworks, video, counting, pipeline, sessions, storage, UI code |
| `adapters` | Concrete OpenCV, Ultralytics, and Supervision integration boundaries, including the Phase 4.3 YOLO trainer, Phase 5.2 live detector/preview, and Phase 5.3 ByteTrack/tracking preview. | `models`, `core`, detection/tracking/streaming contracts, config/training when needed | Data inventory, pipeline orchestration, counting rules, sessions, storage, UI business logic |
| `training` | Framework-neutral detector-training configuration, contracts, prepared-dataset gate, orchestration, metrics reporting, and failure summaries. | `annotation`, `evaluation`, `models`, `core` | Concrete adapters, Ultralytics, Torch, OpenCV, NumPy, Supervision, tracking, counting, pipeline, sessions, storage, UI logic |
| `streaming` | Framework-neutral live-frame contracts, immutable packets, source configuration, bounded buffering, health, lifecycle, reconnect policy, and synthetic source. | `core` and Python standard library | `adapters`, OpenCV, NumPy, Torch, Ultralytics, Supervision, detection, tracking, counting, pipeline, sessions, storage, UI logic |
| `pipeline` | Synchronous generic counting, live detector, and live temporary-ID tracking orchestration with immutable results. | `video`, `detection`, `tracking`, `streaming`, `models`, `counting`; `core/config` when needed | Data inventory, concrete adapters, CV frameworks, persistence, UI logic, sessions, duplicated counting geometry |
| `video` | Framework-neutral source contract plus CLI/output and OpenCV metadata infrastructure. | `models` for contract; `adapters`, `pipeline`, `counting`, `core`, `config` for generic entrypoint/output; `data` models/validation for metadata inspection | Sessions, storage, UI business logic, duplicated counting rules |
| `sessions` | Future operational session lifecycle. | `core`, `domain` | Video, detection, tracking, pipeline, direct UI code |
| `storage` | Future persistence implementations. | `core`, `domain`, `sessions` | Video, detection, tracking, pipeline, direct UI code |
| `domain` | Future operational concepts independent from vision frameworks. | `core` only when necessary | Adapters, CV frameworks, video, detection, tracking, pipeline, sessions, storage |

## External-library boundary

External CV libraries are allowed only in concrete infrastructure-facing code:

* OpenCV in the video-source adapter and annotated-output collaborator
* Ultralytics and NumPy in detector/tracker adapters
* Supervision in annotated-output infrastructure
* OpenCV and NumPy in the Phase 3 video-metadata infrastructure
* OpenCV in Phase 4.2 local frame extraction and annotation image validation
* Ultralytics and Torch inside the Phase 4.3 YOLO training adapter only
* OpenCV inside the Phase 5.1 USB, RTSP, and development-file camera adapters
* Ultralytics, Torch, NumPy, and OpenCV inside the Phase 5.2 live detector adapter
* OpenCV and NumPy inside the optional Phase 5.2 local preview adapter
* Supervision and NumPy inside the Phase 5.3 ByteTrack adapter
* OpenCV and NumPy inside the optional Phase 5.3 tracking preview adapter

The `core`, `config`, `models`, `counting`, `domain`, contract modules,
framework-neutral `data` models/splitting/planning, annotation models/policy/YOLO/manifest,
`evaluation`, framework-neutral `training`, detector models/ports/telemetry,
and pipeline modules must not import
OpenCV, NumPy, Torch, Ultralytics, Supervision, ByteTrack, BoT-SORT, or another
CV framework.

The framework-neutral `streaming` package follows the same restriction. It
defines explicit camera-source outcomes, immutable RGB packets, buffering,
health, and lifecycle behavior without importing detector, tracker, counting,
pipeline, or adapter packages. Camera adapters may depend inward on streaming;
streaming must never depend outward on adapters.

Phase 4.1 dataset selection consumes inventory metadata only. It must not decode
videos, expose local paths in its output, or infer detector quality from an
inventory suitability label.

Phase 4.2 keeps real paths in an ignored source map consumed only by extraction.
Sanitized split, frame, extraction, manifest, and validation outputs contain
opaque IDs and controlled workspace-relative image paths only. YOLO is a text
serialization boundary, not a detector-framework dependency.

Phase 4.3 keeps model loading, training, validation, framework mAP, and tensor
conversion inside the YOLO adapter. Training orchestration receives only
validated HogFlow dataset records, immutable configuration, checkpoints, and
framework-neutral `DetectionFrame` values. HogFlow metrics reuse the Phase 4.1
evaluator. Framework metrics remain separately named.

Phase 5.2 leaves `streaming` independent from detection. The application-level
live detection pipeline may depend inward on both packages, but neither may
depend on that pipeline. The pipeline has no framework imports, no second
unbounded queue, and no tracking or counting dependency. Framework-specific
inference and preview conversion remain inside adapters.

Phase 5.3 leaves `streaming` independent from both detection and tracking, and
leaves `detection` independent from tracking. The application-level live
tracking pipeline may depend inward on all three packages. Tracking runs
serially after successful detection and adds no queue. The tracking domain
does not import counting, sessions, storage, OpenCV, NumPy, Supervision, or
Ultralytics; only concrete adapters import tracking frameworks.

No framework object may appear in a contract signature or escape an adapter.
Video entrypoints choose concrete implementations; pipelines depend only on
contracts and HogFlow models.

## Future dependency direction

Future roadmap work remains governed by lower-level dependencies:

* `sessions → core/domain`
* `storage → core/domain/sessions`
* `future UI → pipeline/sessions/storage`

These arrows do not mark those packages as implemented.

## Change policy

A dependency-direction change requires an explicit technical reason,
corresponding documentation, and updated automated boundary checks.
Convenience alone does not justify a circular or upward dependency.
