# Phase 2 Dependency Rules

## Purpose

These rules make HogFlow's internal dependency direction explicit while Phase 2 is built through audited subphases. They preserve the approved Phase 1 implementation and incorporate the shared models and contracts added in Phase 2.2 without claiming Phase 2.3 integration is implemented.

An arrow means that the module on the left may depend on the module on the right.

The foundational direction can be summarized as:

`counting → config → core`

Counting may also remain directly independent from config and core when it does not need them, as the current Phase 1 counting module does.

Additional intended directions are:

* `video → counting`
* `video → core`
* `video → config`
* `contracts → models → core`
* `detection contract → models`
* `tracking contract → models`
* `video-source contract → models`
* `future pipeline → detection/tracking/counting/video/core/config/domain`
* `future sessions → core/domain`
* `future storage → core/domain/sessions`
* `future UI → pipeline/sessions/storage`

## Package rules

| Package | Responsibility | Allowed internal dependencies | Forbidden examples |
| --- | --- | --- | --- |
| `core` | Shared expected-error types and logging configuration. | None. `core` may use only the Python standard library. | `config`, `counting`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `config` | Explicit, validated, immutable foundational settings. | `core` | `counting`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `models` | Canonical immutable `Frame`, `BoundingBox`, `Detection`, and `Track` contract data. | `core` | `config`, `counting`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `counting` | Detector-independent counting rules and geometry. | `core`; `config` only when a concrete need exists. Current Phase 1 counting remains independent from both. | `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, UI code |
| `video` | Phase 1 video integration plus the Phase 2.2 framework-neutral `VideoSource` contract. | `models` for the contract; `core`, `config`, and `counting` for approved or future integration needs | `pipeline`, `sessions`, `storage`, UI code; duplicated counting business rules |
| `detection` | Phase 2.2 detector contract; concrete implementations are future work. | `models`; `core` or `config` only when a future implementation has a concrete need | `video`, `tracking`, `pipeline`, `sessions`, `storage`, UI code |
| `tracking` | Phase 2.2 tracker contract; concrete adapters are future work. | `models`; `core` or `config` only when a future implementation has a concrete need | `video`, `detection`, `pipeline`, `sessions`, `storage`, UI code |
| `pipeline` | Future orchestration between video input, detection, tracking, counting, and domain-neutral results. | `core`, `config`, `video`, `detection`, `tracking`, `counting`, `domain` | Direct persistence or UI business logic; Phase 2.1 contains no orchestration implementation |
| `sessions` | Future operational session lifecycle. | `core`, `domain` | `video`, `detection`, `tracking`, `pipeline`, direct UI code |
| `storage` | Future persistence implementations. | `core`, `domain`, `sessions` | `video`, `detection`, `tracking`, `pipeline`, direct UI code |
| `domain` | Future operational metadata and domain concepts independent from vision frameworks. | `core` only when necessary | OpenCV, Ultralytics, Supervision, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage` |

## External-library boundary

The approved Phase 1 `video` implementation may continue using external computer-vision libraries directly. Decoupling the existing detector and tracker integration through the Phase 2.2 contracts belongs to Phase 2.3.

The `core`, `config`, `models`, `counting`, and `domain` layers must not import OpenCV, Ultralytics, or Supervision. Phase 2.2 contract modules must not import any computer-vision or model framework, including NumPy and Torch.

## Change policy

These rules are architectural decisions for the current roadmap, not permanent laws. A dependency-direction change requires an explicit technical reason, corresponding documentation, and updated automated boundary checks. Convenience alone is not sufficient justification for a circular or upward dependency.
