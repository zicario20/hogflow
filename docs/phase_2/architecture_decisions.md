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
