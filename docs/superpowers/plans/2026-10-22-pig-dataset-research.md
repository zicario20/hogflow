# Pig Dataset Research & Integration Readiness Implementation Plan

> **For agentic workers:** This plan is for the documentation-only research task. It must not alter the frozen V2 detector, reserved evaluation videos, or production pipeline.

**Goal:** Produce a verified Spanish landscape of pig datasets, HogFlow compatibility analysis, a staged data-integration plan, and a bounded V3 experiment proposal without downloading data or training a model.

**Architecture:** Treat external datasets as source-level development inputs behind future adapters. Preserve HogFlow's existing YOLO/annotation-manifest/trainer/evaluator contracts, source-aware splits, and one detector → ByteTrack → crossing → counter lane. Keep V2 and all formal validation evidence immutable.

**Tech Stack:** Markdown documentation, existing Python/YOLO11/Ultralytics/ByteTrack contracts as inspected context, official dataset pages and repositories only.

**Spec:** User request “CODEX — HOGFLOW: PIG DATASET RESEARCH & INTEGRATION READINESS”.

## Global Constraints

- Do not train V3 or download complete datasets.
- Do not modify V2 weights, SHA, frozen parameters, pipeline, counting algorithm, sessions, or historical evidence.
- Do not select or inspect Video C.
- Keep the four-dock / one-shared-lane architecture.
- Separate verified facts, inference, and authorization requirements.
- Do not claim external metrics transfer to JBS or production readiness.

### Task 1: Architecture and baseline audit

**Files:** Read-only inspection of `HOGFLOW_PROJECT_CONTEXT.md`, `HOGFLOW_PROJECT_MEMORY.md`, Phase 10.3A/B/C-A docs, detector/training/evaluation contracts, and V2 provenance.

- [x] Confirm branch, HEAD, remote, working tree, active V2 identity/configuration, and existing dataset/training/evaluation boundaries.
- [x] Confirm no media/model artifacts are tracked.

### Task 2: Official-source research

**Files:** Research notes remain in the four deliverables; no downloaded dataset files.

- [x] Verify PigLife portal, datasheet/license constraints, size and published annotation scope.
- [x] Verify PigDetect Zenodo metadata, README formats, split strategy, file sizes, and license visibility.
- [x] Verify Edinburgh Pig Behavior official page, temporal labels, boxes, persistent IDs, RGB-D format, and scale.
- [x] Verify additional relevant sources such as PigTracking, OinkTrack, PigTracker, FaroPigSeg, and infrared alternatives, recording license/access uncertainty explicitly.

### Task 3: Documentation deliverables

**Files:**
- Create: `docs/research/pig-dataset-landscape.md`
- Create: `docs/research/pig-dataset-compatibility.md`
- Create: `docs/research/pig-data-integration-plan.md`
- Create: `docs/research/v3-experiment-proposal.md`

- [x] Write a fact/inference matrix with URLs, license status, scale, modalities, annotations, density, lighting, and HogFlow utility.
- [x] Map formats and required adapters to YOLO11/Ultralytics, ByteTrack, and the existing evaluator/counter without proposing production architecture changes.
- [x] Define audit, normalization, isolated experiment, independent holdout, and GO/NO-GO stages.
- [x] Define a small V3 experiment matrix, metrics, storage/compute ranges, leakage controls, and authorization gates.

### Task 4: Quality and hygiene verification

- [x] Run `git diff --check` and documentation scans for private paths, credentials, and media/model references.
- [x] Confirm V2 provenance and model SHA are unchanged, no external files were downloaded, and no Video C was inspected.
- [x] Report local changes and whether a commit/push is requested; do not claim CI changes for documentation-only work without running them.
