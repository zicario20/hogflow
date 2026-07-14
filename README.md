# HogFlow

HogFlow is a computer vision research prototype / MVP for evaluating automated livestock counting in constrained passage environments.

## Project hypothesis

HogFlow is based on the hypothesis that a pipeline combining pig detection, multi-object tracking, and directional virtual-line crossing may be able to estimate the number of pigs moving through a constrained alley with sufficiently low count error to reduce continuous manual counting effort.

This is a research hypothesis, not a validated result.

## Current project status

Current roadmap status: Phase 1 implemented — generic line-crossing pipeline created; pig-specific implementation not started

The repository contains Phase 0 documentation and a Phase 1 generic people/vehicle line-crossing proof of concept. Pig-specific detection, tracking evaluation, and counting validation have not started.

HogFlow should not currently be described as production-ready, operationally proven, or commercially validated.

## Phase 0 documentation

* [problem_statement.md](docs/phase_0/problem_statement.md)
* [current_process.md](docs/phase_0/current_process.md)
* [proposed_solution.md](docs/phase_0/proposed_solution.md)
* [process_map.md](docs/phase_0/process_map.md)
* [assumptions_and_unknowns.md](docs/phase_0/assumptions_and_unknowns.md)
* [phase_0_summary.md](docs/phase_0/phase_0_summary.md)

## Phase 1

Phase 1 implements a generic people/vehicle proof of concept that reads a local video, obtains generic detections and tracker IDs, evaluates bottom-center points against an arbitrary directional line, counts each eligible tracker ID at most once, logs crossing events, and writes an annotated video.

Phase 1 does not validate pig counting.

* [Phase 1 design](docs/phase_1/phase_1_design.md)
* [Phase 1 usage](docs/phase_1/phase_1_usage.md)
* [Phase 1 summary](docs/phase_1/phase_1_summary.md)

## High-level conceptual pipeline

PLANNED conceptual flow:

VIDEO
→ DETECTOR
→ DETECTIONS
→ TRACKER
→ TRACKER IDS
→ DIRECTIONAL LINE CROSSING
→ SESSION COUNTER
→ EVENT STORAGE
→ OPERATOR UI
→ EVALUATION / ANALYTICS

## Roadmap status

The defined roadmap spans Phase 0 through Phase 16, from problem definition through a possible future pilot-readiness plan.

Phase 0 status:

* documented

Phase 1 status:

* implemented as a generic people/vehicle proof of concept

Not yet implemented:

* Phase 2: HogFlow software architecture
* Phase 3: Pig video data acquisition
* Phase 4: Pig detection baseline
* Phase 5: Multi-object tracking
* Phase 6: Virtual counting line evaluation
* Phase 7: Reverse movement and duplicate counting
* Phase 8: Three-section session manager
* Phase 9: Operator MVP User Interface
* Phase 10: SQLite session and event storage
* Phase 11: Ground-truth evaluation
* Phase 12: Error analysis and analytics dashboard
* Phase 13: Failure review system
* Phase 14: Optional group-weight consistency analysis
* Phase 15: Results case study
* Phase 16: Pilot-readiness plan and validation gates

## Documentation index

* [AGENTS.md](AGENTS.md)
* [HOGFLOW_PROJECT_CONTEXT.md](HOGFLOW_PROJECT_CONTEXT.md)
* [INVENTION_LOG.md](INVENTION_LOG.md)
* [MARKET_RESEARCH.md](MARKET_RESEARCH.md)

## Current repository scope

The repository preserves persistent project context and implements only the Phase 1 generic line-crossing proof of concept beyond Phase 0 documentation.

It does not implement pig-specific detection, the Phase 2 architecture, sessions, storage, UI, evaluation, or pilot workflow code.
