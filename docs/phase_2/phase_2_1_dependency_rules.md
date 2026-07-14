# Phase 2.1 Dependency Rules

## Purpose

These rules make HogFlow's internal dependency direction explicit while Phase 2 is built through audited subphases. They preserve the approved Phase 1 implementation and define boundaries for future work without claiming those future modules are implemented.

An arrow means that the module on the left may depend on the module on the right.

The foundational direction can be summarized as:

`counting → config → core`

Counting may also remain directly independent from config and core when it does not need them, as the current Phase 1 counting module does.

Additional intended directions are:

* `video → counting`
* `video → core`
* `video → config`
* `future detection → core/config`
* `future tracking → core/config`
* `future pipeline → detection/tracking/counting/video/core/config/domain`
* `future sessions → core/domain`
* `future storage → core/domain/sessions`
* `future UI → pipeline/sessions/storage`

## Package rules

| Package | Responsibility | Allowed internal dependencies | Forbidden examples |
| --- | --- | --- | --- |
| `core` | Shared expected-error types and logging configuration. | None. `core` may use only the Python standard library. | `config`, `counting`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `config` | Explicit, validated, immutable foundational settings. | `core` | `counting`, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, `domain` |
| `counting` | Detector-independent counting rules and geometry. | `core`; `config` only when a concrete need exists. Current Phase 1 counting remains independent from both. | `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage`, UI code |
| `video` | Phase 1 video input, generic detector/tracker integration, event output, and annotation. | `core`, `config`, `counting` | `pipeline`, `sessions`, `storage`, UI code; duplicated counting business rules |
| `detection` | Future detector contracts and implementations. | `core`, `config` | `video`, `tracking`, `pipeline`, `sessions`, `storage`, UI code |
| `tracking` | Future tracker contracts and adapters. | `core`, `config` | `video`, `detection`, `pipeline`, `sessions`, `storage`, UI code |
| `pipeline` | Future orchestration between video input, detection, tracking, counting, and domain-neutral results. | `core`, `config`, `video`, `detection`, `tracking`, `counting`, `domain` | Direct persistence or UI business logic; Phase 2.1 contains no orchestration implementation |
| `sessions` | Future operational session lifecycle. | `core`, `domain` | `video`, `detection`, `tracking`, `pipeline`, direct UI code |
| `storage` | Future persistence implementations. | `core`, `domain`, `sessions` | `video`, `detection`, `tracking`, `pipeline`, direct UI code |
| `domain` | Future operational metadata and domain concepts independent from vision frameworks. | `core` only when necessary | OpenCV, Ultralytics, Supervision, `video`, `detection`, `tracking`, `pipeline`, `sessions`, `storage` |

## External-library boundary

The approved Phase 1 `video` implementation may continue using external computer-vision libraries directly. Decoupling the existing detector and tracker integration through future contracts belongs to Phase 2.3, after contracts are introduced in Phase 2.2.

The `core`, `config`, `counting`, and `domain` packages must not import OpenCV, Ultralytics, or Supervision.

## Change policy

These rules are architectural decisions for the current roadmap, not permanent laws. A dependency-direction change requires an explicit technical reason, corresponding documentation, and updated automated boundary checks. Convenience alone is not sufficient justification for a circular or upward dependency.
