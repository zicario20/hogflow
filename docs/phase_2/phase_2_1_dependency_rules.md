# Phase 2 Dependency Rules

## Purpose

These rules define the dependency direction after Phase 2.3 integrates the
approved contracts with concrete generic adapters and a synchronous pipeline.
An arrow means that the module on the left may depend on the module on the
right.

Implemented direction:

* `adapters → contracts/models/core/config`
* `pipeline → contracts/models/counting/core/config`
* `video CLI/output → adapters/pipeline/counting/config/core`
* `contracts → models → core`
* `counting → core/config` only when a concrete need exists

The current counting module remains independent from CV frameworks and does
not need config or core.

## Package rules

| Package | Responsibility | Allowed internal dependencies | Forbidden examples |
| --- | --- | --- | --- |
| `core` | Shared expected-error types and logging configuration. | Python standard library only. | `adapters`, `config`, `counting`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `config` | Explicit immutable foundational settings. | `core` | `adapters`, `counting`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `models` | Canonical immutable communication data. | `core` | `adapters`, `config`, `counting`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `counting` | Detector-independent counting rules and geometry. | `core` or `config` only with concrete need; currently neither. | `adapters`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, UI code, CV frameworks |
| `detection` | Framework-independent `Detector` contract. | `models` | Adapters, frameworks, video, tracking, pipeline, storage, UI code |
| `tracking` | Framework-independent `Tracker` contract. | `models` | Adapters, frameworks, video, detection, pipeline, storage, UI code |
| `adapters` | Concrete OpenCV and Ultralytics integration boundaries. | `models`, `core`; contracts/config when needed | Pipeline orchestration, counting rules, sessions, storage, UI business logic |
| `pipeline` | Synchronous generic orchestration and immutable results. | `video`, `detection`, `tracking`, `models`, `counting`; `core/config` when needed | Concrete adapters, CV frameworks, persistence, UI logic, sessions, duplicated counting geometry |
| `video` | Framework-neutral source contract plus CLI/output infrastructure. | `models` for contract; `adapters`, `pipeline`, `counting`, `core`, `config` for entrypoint/output integration | Sessions, storage, UI business logic, duplicated counting rules |
| `sessions` | Future operational session lifecycle. | `core`, `domain` | Video, detection, tracking, pipeline, direct UI code |
| `storage` | Future persistence implementations. | `core`, `domain`, `sessions` | Video, detection, tracking, pipeline, direct UI code |
| `domain` | Future operational concepts independent from vision frameworks. | `core` only when necessary | Adapters, CV frameworks, video, detection, tracking, pipeline, sessions, storage |

## External-library boundary

External CV libraries are allowed only in concrete infrastructure-facing code:

* OpenCV in the video-source adapter and annotated-output collaborator
* Ultralytics and NumPy in detector/tracker adapters
* Supervision in annotated-output infrastructure

The `core`, `config`, `models`, `counting`, `domain`, contract modules, and
pipeline modules must not import OpenCV, NumPy, Torch, Ultralytics, Supervision,
ByteTrack, BoT-SORT, or another CV framework.

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
