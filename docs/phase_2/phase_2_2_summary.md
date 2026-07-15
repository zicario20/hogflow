# Phase 2.2 Summary — Interfaces & Contracts

## Subphase objective

Phase 2.2 creates the stable, framework-independent contract layer required before future detector, tracker, and video-source adapters are implemented. It adds no user-visible processing behavior and does not change the Phase 1 counting engine or generic counter.

## Implementation delivered

* canonical frozen `Frame`, `BoundingBox`, `Detection`, and `Track` data models
* one `Detector` Protocol using `Frame → Sequence[Detection]`
* one `Tracker` Protocol using `Frame + Sequence[Detection] → Sequence[Track]`
* one `VideoSource` Protocol using `read() → Frame | None` and explicit `close()`
* explicit public exports for the three contracts
* architecture enforcement for the shared-model dependency layer
* automated rejection of computer-vision framework imports in contract files
* import-side-effect checks for models and contracts
* immutable-model, public API, type-hint, documentation, and protocol tests
* Phase 2.2 architecture and dependency documentation

## Architecture result

The implemented dependency direction is:

`future implementations → contracts → shared models → core`

The contract layer uses only Python standard-library types and HogFlow shared models. No detector, tracker, source, adapter, orchestrator, factory, service, manager, database, session, UI, or operational-domain implementation was introduced.

## Backward compatibility

At Phase 2.2 completion, the approved Phase 1 counting and video modules and
tests remained unchanged, and the generic counter still used its direct
Ultralytics, Supervision, and OpenCV integration. Phase 2.3 later adapted that
integration while preserving Phase 1 behavior.

## Validation evidence

Phase 2.2 validation covers:

* existing Phase 1 behavior
* Protocol existence and importability
* exactly one public protocol in each contract module
* complete method type hints and public documentation
* frozen shared dataclasses and model invariants
* contract use of shared models
* architecture dependency direction
* absence of CV-framework imports in the contract layer
* absence of import-time output and runtime side effects

## Status at Phase 2.2 completion

At the conclusion of Phase 2.2, Phase 2.3 had not started. Phase 2.3 later
completed the adapter and pipeline integration documented in
[phase_2_3_summary.md](phase_2_3_summary.md).

## Known limitations at Phase 2.2 completion

* pipeline orchestration is not implemented
* no concrete detector is implemented
* no concrete tracker is implemented
* no video adapter is implemented
* the existing Phase 1 integration has not yet been adapted to the contracts
* no pig-specific or operational-domain behavior is implemented
* persistence and user interface behavior are not implemented
