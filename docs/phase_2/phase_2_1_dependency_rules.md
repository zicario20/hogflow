# Phase 2 Dependency Rules

## Purpose

These rules define the dependency direction after Phase 2.3 integrates the
approved contracts with concrete generic adapters and a synchronous pipeline,
after Phase 3 adds local dataset-inventory infrastructure, after Phase 4.1
adds framework-neutral detection-evaluation infrastructure, and after Phase 4.2
adds local annotation-dataset preparation, and after Phase 4.3 adds the
replaceable baseline detector-training boundary.
An arrow means that the module on the left may depend on the module on the
right.

Implemented direction:

* `adapters → contracts/models/core/config`
* `pipeline → contracts/models/counting/core/config`
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
| `detection` | Framework-independent `Detector` contract. | `models` | Adapters, frameworks, video, tracking, pipeline, storage, UI code |
| `tracking` | Framework-independent `Tracker` contract. | `models` | Adapters, frameworks, video, detection, pipeline, storage, UI code |
| `adapters` | Concrete OpenCV and Ultralytics integration boundaries, including the Phase 4.3 YOLO trainer. | `models`, `core`, contracts/config/training when needed | Data inventory, pipeline orchestration, counting rules, sessions, storage, UI business logic |
| `training` | Framework-neutral detector-training configuration, contracts, prepared-dataset gate, orchestration, metrics reporting, and failure summaries. | `annotation`, `evaluation`, `models`, `core` | Concrete adapters, Ultralytics, Torch, OpenCV, NumPy, Supervision, tracking, counting, pipeline, sessions, storage, UI logic |
| `pipeline` | Synchronous generic orchestration and immutable results. | `video`, `detection`, `tracking`, `models`, `counting`; `core/config` when needed | Data inventory, concrete adapters, CV frameworks, persistence, UI logic, sessions, duplicated counting geometry |
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

The `core`, `config`, `models`, `counting`, `domain`, contract modules,
framework-neutral `data` models/splitting/planning, annotation models/policy/YOLO/manifest,
`evaluation`, framework-neutral `training`, and pipeline modules must not import
OpenCV, NumPy, Torch, Ultralytics, Supervision, ByteTrack, BoT-SORT, or another
CV framework.

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

No framework object may appear in a contract signature or escape an adapter.
The video CLI chooses concrete implementations; the pipeline depends only on
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
