# Phase 10.3A Provisional Pig Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend HogFlow with a local, human-reviewed two-video pig-detection experiment that can train one provisional detector, evaluate an untouched holdout video, and exercise the existing detector-to-counter HMI flow.

**Architecture:** Add a small provisional-data package over the existing Phase 4.2/4.3 contracts. The current source-isolated annotation policy remains the default; an explicit temporal-block policy is the only new path for the development video, while the independent video is represented by an evaluation-only prepared dataset. A safety check in the existing shared camera controller prevents replay while a counting lane is occupied.

**Tech Stack:** Python 3.12, pytest, Ruff, OpenCV, Ultralytics/YOLO through the existing adapter, Tkinter development annotator, existing HogFlow detector/tracker/crossing/counter/HMI contracts.

**Spec:** `docs/superpowers/specs/2026-08-30-phase-10-3a-provisional-pig-demo-design.md`

## Global Constraints

- Run every command from the repository root and use `main` as the authorized branch.
- Use the repaired local Python 3.12 environment for every project command; never use global Python 3.14.
- Authorize exactly `demo_video_a` and `demo_video_b`; never recurse over arbitrary media and never modify `hogflow.validation.catalog`.
- Keep `demo_video_a` temporal training/calibration blocks disjoint with a positive buffer; keep `demo_video_b` out of the training manifest and decision process until the freeze receipt exists.
- Use exactly one detection class: `class_id=0`, `class_name='pig'`.
- Keep videos, frames, labels, sidecars, manifests, reports, checkpoints, model weights, and local databases ignored and untracked.
- Use existing `hogflow.data`, `hogflow.annotation`, `hogflow.training`, `hogflow.evaluation`, Phase 10.2, and Phase 9.3/9.4 contracts; do not create a second inference, tracking, counting, or validation stack.
- Do not redesign the HMI, add persistence, start Phase 10.4/11+, upload media, download external pig data, or make production-readiness claims.
- Stop at `HUMAN ANNOTATION REQUIRED` when box review is incomplete; never fabricate labels or manual crossing totals.

## File Map

Create:

- `src/hogflow/provisional/__init__.py` — public exports for the bounded 10.3A helpers.
- `src/hogflow/provisional/authorization.py` — exact-two-video local authorization and sanitized role model.
- `src/hogflow/provisional/frame_plan.py` — deterministic A temporal-block and B holdout frame planning over `FrameSelectionPlan`.
- `src/hogflow/provisional/evaluation.py` — evaluation-only prepared dataset and frozen-run/holdout orchestration over existing training/evaluation contracts.
- `src/hogflow/provisional/artifact.py` — final model staging and Phase 10.2-compatible sanitized provenance.
- `scripts/annotate_pigs.py` — local-only Tkinter box annotator; no production imports.
- `tests/test_phase_10_3a_authorization.py` — authorization and ignore-boundary behavior.
- `tests/test_phase_10_3a_temporal_split.py` — temporal policy and leakage checks.
- `tests/test_phase_10_3a_frame_plan.py` — deterministic selection and split isolation.
- `tests/test_phase_10_3a_annotation_tool.py` — annotation geometry and YOLO persistence helpers.
- `tests/test_phase_10_3a_training.py` — demo profile, evaluation-only loading, and provenance fingerprints.
- `tests/test_phase_10_3a_artifact.py` — single-model candidate and sanitized provenance checks.

Modify:

- `.gitignore` — explicitly ignore `data/training/` and preserve only its placeholder.
- `src/hogflow/annotation/models.py`, `manifest.py`, `validation.py` — opt-in temporal-block manifest policy with backward-compatible source isolation.
- `src/hogflow/data/frame_selection.py` and `src/hogflow/data/frame_extraction.py` — carry opaque temporal-block IDs and source timestamps through existing plans/reports.
- `src/hogflow/data/frame_extraction.py` — preserve selected source timestamps/block IDs in the sanitized extraction bridge.
- `src/hogflow/training/configuration.py`, `dataset.py`, `models.py`, `reporting.py`, `adapters/yolo_baseline_trainer.py` — demo training controls, deterministic configuration fingerprint, and holdout evaluation boundary.
- `src/hogflow/camera/controller.py` and `src/hogflow/presentation/presenter.py` — active-lane replay guard and snapshot-derived control availability.
- `HOGFLOW_PROJECT_MEMORY.md` and a new sanitized `docs/phase_10/phase_10_3a_validation.md` — record implemented behavior and measured evidence only after execution.

---

### Task 0: Repair and record the Python 3.12 execution environment

**Files:**
- No source files. The new environment remains under ignored `.venv/`.

**Interfaces:**
- Consumes: the installed Python 3.12 runtime discovered under the local Codex runtime dependencies.
- Produces: `.venv\phase10_3a\Scripts\python.exe`, a reproducible interpreter for all later tasks.

- [ ] **Step 1: Prove the stale environments fail without changing them**

```powershell
& .\.venv\native\Scripts\python.exe --version
& .\.venv\windows\Scripts\python.exe --version
```

Expected: both report their obsolete `the_m` runtime path and exit non-zero.

- [ ] **Step 2: Create the ignored Python 3.12 environment**

```powershell
$python312 = Get-ChildItem -Path "$env:LOCALAPPDATA\.." -Recurse -File -Filter python.exe -ErrorAction Stop |
    Where-Object { $_.FullName -match 'codex-runtimes.*dependencies.*python.exe' } |
    Select-Object -First 1 -ExpandProperty FullName
$env312 = Join-Path $PWD '.venv\phase10_3a'
& $python312 -m venv --copies $env312
& "$env312\Scripts\python.exe" --version
```

Expected: `Python 3.12.x` and no modification to tracked files.

- [ ] **Step 3: Install the project and verify dependency versions**

```powershell
& "$env312\Scripts\python.exe" -m pip install -e '.[dev]'
& "$env312\Scripts\python.exe" -c "import cv2, supervision, torch, ultralytics; print(cv2.__version__); print(supervision.__version__); print(torch.__version__); print(ultralytics.__version__)"
```

Expected: installation succeeds, imports succeed, and the versions are captured in the local run record.

- [ ] **Step 4: Run the untouched baseline gates with Python 3.12**

```powershell
& "$env312\Scripts\python.exe" -m pytest
& "$env312\Scripts\python.exe" -m ruff check --no-cache .
& "$env312\Scripts\python.exe" -m ruff format --check --no-cache .
& "$env312\Scripts\python.exe" -m compileall -q src
& "$env312\Scripts\python.exe" -m pip check
& "$env312\Scripts\python.exe" -m hogflow --help
& "$env312\Scripts\python.exe" -m hogflow run --help
```

Expected: the baseline result is recorded exactly; a failure stops implementation until its cause is understood.

---

### Task 1: Add exact-two-video provisional authorization

**Files:**
- Create: `src/hogflow/provisional/__init__.py`
- Create: `src/hogflow/provisional/authorization.py`
- Create: `tests/test_phase_10_3a_authorization.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: an ignored JSON object with two local basenames and the repository `data/raw` root.
- Produces: `ProvisionalVideoRole`, `AuthorizedProvisionalVideo`, `ProvisionalVideoManifest`, `load_provisional_video_manifest(path, raw_root)`, and `write_provisional_video_manifest(manifest, path)`.

- [ ] **Step 1: Write the failing authorization tests**

```python
def _write_manifest(root: Path, records: list[dict[str, str]]) -> Path:
    path = root / "authorization.json"
    path.write_text(json.dumps({"format_version": 1, "videos": records}), encoding="utf-8")
    return path


def test_manifest_accepts_exactly_two_explicit_roles(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, [
        {"video_id": "demo_video_a", "basename": "a.mp4", "role": "training_development"},
        {"video_id": "demo_video_b", "basename": "b.mp4", "role": "independent_validation"},
    ])
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "b.mp4").write_bytes(b"b")

    manifest = load_provisional_video_manifest(manifest_path, tmp_path)

    assert tuple(video.video_id for video in manifest.videos) == ("demo_video_a", "demo_video_b")


def test_manifest_rejects_extra_records_and_missing_media(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, [
        {"video_id": "demo_video_a", "basename": "a.mp4", "role": "training_development"},
        {"video_id": "demo_video_b", "basename": "b.mp4", "role": "independent_validation"},
        {"video_id": "extra", "basename": "c.mp4", "role": "independent_validation"},
    ])
    with pytest.raises(InputDataError, match="exactly two"):
        load_provisional_video_manifest(manifest_path, tmp_path)
```

- [ ] **Step 2: Run the focused tests and verify the expected missing-module failure**

Run: `& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_authorization.py -q`

Expected: FAIL because the provisional authorization module does not exist.

- [ ] **Step 3: Implement the minimal exact-record gate**

```python
EXPECTED_IDS = ("demo_video_a", "demo_video_b")

def load_provisional_video_manifest(path: str | Path, raw_root: str | Path) -> ProvisionalVideoManifest:
    payload = _load_object(path)
    records = payload.get("videos")
    if not isinstance(records, list) or len(records) != 2:
        raise InputDataError("Provisional authorization must contain exactly two videos.")
    videos = tuple(_parse_record(item, Path(raw_root)) for item in records)
    if tuple(video.video_id for video in videos) != EXPECTED_IDS:
        raise InputDataError("Provisional videos must be demo_video_a followed by demo_video_b.")
    if len({video.basename.casefold() for video in videos}) != 2:
        raise InputDataError("Provisional video basenames must be unique.")
    return ProvisionalVideoManifest(videos=videos)
```

The parser resolves only `raw_root / basename`, rejects traversal, rejects tracked or missing files, and never calls recursive discovery. The writer emits only the explicit two-record local file.

- [ ] **Step 4: Add the ignore rule and run the focused tests**

Add:

```gitignore
data/training/**
!data/training/.gitkeep
```

Run: `& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_authorization.py -q`

Expected: PASS, including an assertion that a local authorization manifest and media are ignored and absent from `git ls-files`.

- [ ] **Step 5: Create the local two-record authorization file without committing it**

Use `write_provisional_video_manifest` with the two user-selected basenames, save it under `data/training/`, and verify:

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -c "from hogflow.provisional.authorization import load_provisional_video_manifest; print(load_provisional_video_manifest('data/training/phase10_3a_authorization.local.json','data/raw'))"
& git -c safe.directory=D:/hogflow ls-files data/raw data/training
```

Expected: two explicit records load; `git ls-files` prints no real media or local manifest.

---

### Task 2: Implement the opt-in temporal-block manifest policy

**Files:**
- Modify: `src/hogflow/annotation/models.py`
- Modify: `src/hogflow/annotation/manifest.py`
- Modify: `src/hogflow/annotation/validation.py`
- Modify: `src/hogflow/data/frame_extraction.py`
- Create: `tests/test_phase_10_3a_temporal_split.py`

**Interfaces:**
- Consumes: existing `AnnotationDatasetManifest`, `AnnotationFrameRecord`, extraction report records, and YOLO validation.
- Produces: `AnnotationSplitPolicy`, `TemporalBlock`, `AnnotationFrameRecord.source_timestamp_seconds`, `AnnotationFrameRecord.temporal_block_id`, `PlannedFrame.temporal_block_id`, `ExtractedFrameRecord.temporal_block_id`, and `build_annotation_manifest(..., split_policy=..., temporal_blocks=...)`.

- [ ] **Step 1: Write the failing tests for both policies**

```python
def test_source_isolated_remains_the_default() -> None:
    manifest = _manifest_with_same_clip_in_train_and_validation()
    report = validate_annotation_dataset(_dataset_root(manifest), manifest)
    assert "source_video_split_leakage" in {finding.code for finding in report.findings}


def test_temporal_blocks_allow_one_source_only_with_gap_and_timestamps() -> None:
    manifest = _temporal_manifest(train_end=4.0, validation_start=5.0)
    report = validate_annotation_dataset(_dataset_root(manifest), manifest)
    assert report.valid


def test_temporal_policy_rejects_overlap_missing_block_or_nonpositive_gap() -> None:
    for manifest in (_overlapping_manifest(), _missing_timestamp_manifest(), _zero_gap_manifest()):
        report = validate_annotation_dataset(_dataset_root(manifest), manifest)
        assert not report.valid
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_temporal_split.py -q`

Expected: FAIL because the policy, block metadata, and timestamp fields are not defined.

- [ ] **Step 3: Add immutable policy and block metadata with backward-compatible defaults**

```python
class AnnotationSplitPolicy(str, Enum):
    SOURCE_ISOLATED = "source_isolated"
    TEMPORAL_BLOCKED = "temporal_blocked"

@dataclass(frozen=True, slots=True)
class TemporalBlock:
    block_id: str
    clip_id: str
    split: DatasetSplit
    start_seconds: float
    end_seconds: float

# Add this optional field to the existing immutable plan/extraction records:
temporal_block_id: str | None = None

# Add these optional fields to the existing immutable AnnotationFrameRecord:
source_timestamp_seconds: float | None = None
temporal_block_id: str | None = None
```

Keep schema version 1 manifests loadable with `source_isolated`; serialize the new fields only when present and use a versioned manifest payload for temporal manifests. Reject private paths, non-finite times, unknown blocks, and class maps other than `((0, 'pig'),)`.

- [ ] **Step 4: Route validation according to the explicit policy**

```python
if manifest.split_policy is AnnotationSplitPolicy.SOURCE_ISOLATED:
    _validate_source_split_isolation(manifest.frames, findings)
else:
    _validate_temporal_blocks(manifest.frames, manifest.temporal_blocks, findings)
```

The temporal validator must require a positive interval gap between train and calibration blocks, one block per frame, timestamps within the block, no frame/checksum duplication, and no test/independent frames in the A development manifest. The existing source-isolation validator remains unchanged for the default policy.

- [ ] **Step 5: Preserve timestamps/block IDs through frame plans and manifest construction**

Pass `actual_timestamp_seconds` (falling back to planned timestamp) from extraction records into `AnnotationFrameRecord.source_timestamp_seconds`; pass the planned block ID from the provisional planner. Run:

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_temporal_split.py tests/test_annotation_manifest.py tests/test_annotation_validation.py -q
```

Expected: new temporal tests pass and all existing source-isolation tests remain green.

---

### Task 3: Build deterministic A/B frame plans and extract locally

**Files:**
- Create: `src/hogflow/provisional/frame_plan.py`
- Create: `tests/test_phase_10_3a_frame_plan.py`

**Interfaces:**
- Consumes: `ProvisionalVideoManifest`, `ClipSamplingMetadata`, `FrameSelectionSettings`, and the inspected A/B durations.
- Produces: `create_phase10_3a_frame_selection_plan(...) -> FrameSelectionPlan` and a sanitized plan summary with temporal block boundaries.

- [ ] **Step 1: Write the failing plan tests**

```python
def test_plan_is_deterministic_and_contains_no_duplicate_timestamps() -> None:
    first = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())
    second = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())
    assert first == second
    assert len({frame.frame_id for frame in first.frames}) == len(first.frames)
    assert len({(frame.clip_id, frame.planned_timestamp_seconds) for frame in first.frames}) == len(first.frames)


def test_video_b_frames_are_holdout_only() -> None:
    plan = create_phase10_3a_frame_selection_plan(_metadata(), settings=_settings())
    assert all(frame.clip_id == DEMO_A_CLIP_ID for frame in plan.frames if frame.split in {DatasetSplit.TRAIN, DatasetSplit.VALIDATION})
    assert all(frame.split is DatasetSplit.TEST for frame in plan.frames if frame.clip_id == DEMO_B_CLIP_ID)
```

- [ ] **Step 2: Run the focused tests and verify the missing helper failure**

Run: `& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_frame_plan.py -q`

Expected: FAIL because the provisional planner does not exist.

- [ ] **Step 3: Implement bounded timeline sampling over the existing plan model**

Use `create_frame_selection_plan` for each explicitly declared temporal block, then combine and sort its existing `PlannedFrame` values:

```python
def create_phase10_3a_frame_selection_plan(metadata, *, settings):
    blocks = _declared_blocks(metadata)
    planned = tuple(
        frame
        for block in blocks
        for frame in _plan_block(block, settings=settings)
    )
    return FrameSelectionPlan(settings=settings, frames=tuple(sorted(planned, key=_frame_sort_key)))
```

Use deterministic timeline offsets, start/end exclusions, and an explicit positive A train/calibration buffer. Do not use adjacent frames from the buffer, do not randomize across videos, and never exceed the available timeline.

- [ ] **Step 4: Run tests and write local plan outputs**

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_frame_plan.py tests/test_frame_selection.py -q
```

Expected: PASS. Write the ignored plan and inspect the sanitized summary to confirm A training/calibration counts and B holdout count without private paths.

- [ ] **Step 5: Extract selected images with the existing extractor**

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m hogflow.data.frame_extraction `
  --plan data/training/phase10_3a_frame_selection.local.json `
  --source-map data/training/phase10_3a_source_map.local.json `
  --output data/annotations/phase10_3a
```

Expected: only local ignored images are created, each with an opaque frame ID and preserved native dimensions; no label file is generated automatically.

---

### Task 4: Add the minimal local pig annotator

**Files:**
- Create: `scripts/annotate_pigs.py`
- Create: `tests/test_phase_10_3a_annotation_tool.py`

**Interfaces:**
- Consumes: selected ignored images and optional existing YOLO label files.
- Produces: `normalized_box(...)`, `load_boxes(...)`, `save_boxes(...)`, and an interactive `main()` that edits only class `pig` labels.

- [ ] **Step 1: Write failing geometry and persistence tests**

```python
def test_drag_coordinates_are_normalized_against_native_dimensions(tmp_path: Path) -> None:
    box = normalized_box(native_width=1320, native_height=2868, x0=132, y0=286, x1=660, y1=1434)
    assert box == (0.3, 0.3, 0.4, 0.4)


def test_save_and_delete_round_trip_uses_class_zero_only(tmp_path: Path) -> None:
    label = tmp_path / "frame.txt"
    save_boxes(label, [(0.5, 0.5, 0.2, 0.3)])
    assert load_boxes(label) == [(0.5, 0.5, 0.2, 0.3)]
    save_boxes(label, [])
    assert load_boxes(label) == []


def test_invalid_class_lines_are_rejected(tmp_path: Path) -> None:
    label = tmp_path / "frame.txt"
    label.write_text("1 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="class 0"):
        load_boxes(label)
```

- [ ] **Step 2: Run the focused tests and verify missing helper failure**

Run: `& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_annotation_tool.py -q`

Expected: FAIL because the development helper does not exist.

- [ ] **Step 3: Implement the non-UI helper functions first**

```python
def normalized_box(native_width: int, native_height: int, x0: int, y0: int, x1: int, y1: int) -> tuple[float, float, float, float]:
    left, right = sorted((max(0, x0), min(native_width, x1)))
    top, bottom = sorted((max(0, y0), min(native_height, y1)))
    if left >= right or top >= bottom:
        raise ValueError("A pig box must have positive area.")
    return ((left + right) / (2 * native_width), (top + bottom) / (2 * native_height), (right - left) / native_width, (bottom - top) / native_height)
```

Route serialization through `hogflow.annotation.yolo` where possible, reject every class other than 0, preserve native dimensions, and never infer boxes.

- [ ] **Step 4: Implement the bounded Tkinter workflow**

The window loads one selected ignored image at a time, scales only the display canvas, maps drag coordinates back to native pixels, shows `index / total`, supports Previous/Next/Save/Delete, reloads existing labels, writes the status map, and exits without network calls. It must not import `hogflow.application`, `hogflow.sessions`, `hogflow.camera`, `hogflow.tracking`, or `hogflow.counting`.

- [ ] **Step 5: Run helper/UI boundary tests and lint**

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_annotation_tool.py -q
& .\.venv\phase10_3a\Scripts\python.exe -m ruff check --no-cache scripts/annotate_pigs.py
```

Expected: PASS. The GUI launch itself is deferred until the local extracted frame count is known.

---

## HUMAN ANNOTATION CHECKPOINT

After Tasks 1–4, stop before Task 5 if any selected frame lacks a human-reviewed status and boxes. Report the exact generated frame count and give the user:

```powershell
& .\.venv\phase10_3a\Scripts\python.exe scripts/annotate_pigs.py `
  --dataset data/annotations/phase10_3a `
  --manifest data/annotations/phase10_3a/metadata/extraction_report.json `
  --status-map data/training/phase10_3a_annotation_status.local.json
```

The user must draw one tight box per clearly identifiable pig, omit people/equipment/shadows, mark natural no-pig images as `verified_empty`, and save progress. Resuming the same command must continue from the saved status map. Validate completion with:

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m hogflow.annotation.manifest `
  --extraction-report data/annotations/phase10_3a/metadata/extraction_report.json `
  --status-map data/training/phase10_3a_annotation_status.local.json `
  --output data/annotations/phase10_3a/metadata/dataset_manifest.json
& .\.venv\phase10_3a\Scripts\python.exe -m hogflow.annotation.validation `
  --dataset data/annotations/phase10_3a `
  --manifest data/annotations/phase10_3a/metadata/dataset_manifest.json `
  --output data/evaluation/phase10_3a_annotation_validation.json
```

Continue only when the validation report is valid and its invalid-annotation count is zero.

---

### Task 5: Extend the existing trainer for the frozen demo profile and B holdout

**Files:**
- Modify: `src/hogflow/training/configuration.py`
- Modify: `src/hogflow/training/dataset.py`
- Modify: `src/hogflow/training/models.py`
- Modify: `src/hogflow/training/reporting.py`
- Modify: `src/hogflow/adapters/yolo_baseline_trainer.py`
- Create: `src/hogflow/provisional/evaluation.py`
- Create: `tests/test_phase_10_3a_training.py`

**Interfaces:**
- Consumes: a valid A temporal manifest and the existing `DetectorTrainer` contract.
- Produces: `TrainingProfile.PHASE_10_3A_DEMO`, `TrainingConfiguration.configuration_fingerprint`, `PreparedEvaluationDataset(frame_ids, root, manifest_path, manifest, validation_report, dataset_version)`, `load_prepared_evaluation_dataset(dataset_root, manifest_path)`, and `YOLOBaselineTrainer.validate_holdout(dataset, checkpoint_path, configuration)`.

- [ ] **Step 1: Write failing configuration and holdout tests**

```python
def test_demo_profile_records_patience_augmentation_and_all_settings() -> None:
    configuration = TrainingConfiguration.demo_phase_10_3a(
        epochs=75, batch_size=4, device="cpu", seed=17, patience=20
    )
    same = TrainingConfiguration.demo_phase_10_3a(
        epochs=75, batch_size=4, device="cpu", seed=17, patience=20
    )
    different = TrainingConfiguration.demo_phase_10_3a(
        epochs=75, batch_size=4, device="cpu", seed=18, patience=20
    )
    assert configuration.profile is TrainingProfile.PHASE_10_3A_DEMO
    assert configuration.configuration_fingerprint == same.configuration_fingerprint
    assert configuration.configuration_fingerprint != different.configuration_fingerprint
    assert configuration.early_stopping_patience == 20


def test_holdout_loader_does_not_require_a_training_split(tmp_path: Path) -> None:
    manifest = _validation_only_manifest(tmp_path)
    dataset = load_prepared_evaluation_dataset(tmp_path, manifest)
    assert dataset.frame_ids == tuple(sorted(dataset.frame_ids))


def test_video_b_is_not_in_the_training_dataset_fingerprint(tmp_path: Path) -> None:
    training = _load_a_only_dataset(tmp_path)
    HOLDOUT_CLIP_ID = "b" * 24
    assert all(record.clip_id != HOLDOUT_CLIP_ID for record in training.manifest.frames)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_training.py -q`

Expected: FAIL because the demo profile, fingerprint, and evaluation-only dataset are missing.

- [ ] **Step 3: Add the opt-in demo profile without changing baseline defaults**

Keep the existing baseline profile capped at 30 epochs. Add a demo profile with an explicit upper bound of 100 epochs, patience 20, a fixed seed, zero/bounded Windows workers, 640 image size, and moderate augmentation fields. Include every effective field in a canonical JSON configuration fingerprint; keep confidence and IoU thresholds separate from framework mAP.

- [ ] **Step 4: Add the evaluation-only prepared dataset**

Reuse `validate_annotation_dataset`, label parsing, checksums, and `DetectionFrame` construction. Allow a validation-only manifest for B without requiring a train split, reject any training/validation source overlap with A, and expose only immutable frame IDs and sanitized fingerprints.

- [ ] **Step 5: Extend the YOLO adapter with frozen configuration and holdout prediction**

Pass `patience`, image size, moderate augmentation values, seed, workers, device, confidence, and IoU/NMS settings to the existing Ultralytics adapter. Add `validate_holdout` that predicts only B frames after the freeze receipt and converts outputs through the existing `DetectionFrame` evaluator. Call framework `.val` only when the installed API accepts the holdout YAML; otherwise record framework mAP as unavailable and retain HogFlow TP/FP/FN metrics.

- [ ] **Step 6: Run training-unit tests and existing training tests**

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_training.py tests/test_baseline_training.py tests/test_training_dataset.py tests/test_yolo_baseline_trainer.py -q
```

Expected: PASS with synthetic fakes; no model download or real media is used by CI tests.

---

### Task 6: Add model artifact selection and sanitized provenance

**Files:**
- Create: `tests/test_phase_10_3a_artifact.py`
- Create: `src/hogflow/provisional/artifact.py`

**Interfaces:**
- Consumes: one selected checkpoint, A dataset/configuration fingerprints, and the existing `LocalValidationWorkspace` model gate.
- Produces: `write_demo_model_provenance(artifact, dataset_fingerprint, configuration_fingerprint, training_run_id, evaluation_reference, output_path) -> Path` and a single ignored final artifact with identity `hogflow_pig_demo.pt`.

- [ ] **Step 1: Write failing artifact/provenance tests**

```python
def test_provenance_is_path_free_and_has_the_existing_phase_10_2_fields(tmp_path: Path) -> None:
    artifact = tmp_path / "hogflow_pig_demo.pt"
    artifact.write_bytes(b"demo")
    provenance = write_demo_model_provenance(
        artifact=artifact,
        dataset_fingerprint="a" * 64,
        configuration_fingerprint="b" * 64,
        training_run_id="phase10_3a_demo",
        evaluation_reference="demo_video_b_holdout",
        output_path=tmp_path / "provenance.json",
    )
    payload = json.loads(provenance.read_text(encoding="utf-8"))
    assert payload["purpose"] == "pig_detection"
    assert payload["class_mapping"] == {"0": "pig"}
    assert str(tmp_path) not in json.dumps(payload)


def test_model_gate_is_available_only_for_one_ignored_candidate(tmp_path: Path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "hogflow_pig_demo.pt").write_bytes(b"demo")
    workspace = _workspace(tmp_path)
    assert workspace.locate_model().state is ModelGateState.AVAILABLE
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_artifact.py -q`

Expected: FAIL because the provisional provenance helper is missing.

- [ ] **Step 3: Implement the provenance writer and gate checks**

Write the artifact SHA-256, `class_mapping`, `dataset_fingerprint`, `configuration_fingerprint`, framework/version, image size, model identity, target class, training run, evaluation reference, rationale, date, and `complete` flag. Reuse the existing Phase 10.2 loader-compatible fields (`purpose`, `artifact_sha256`, `class_mapping`, `training_run_id`, `evaluation_reference`). Never write paths, usernames, credentials, or media names into the JSON.

- [ ] **Step 4: Stage exactly one final candidate and run tests**

Keep all experiment checkpoints under `data/runs/` or `data/training/`; copy only the selected checkpoint to ignored `models/hogflow_pig_demo.pt`, remove extra model candidates from approved discovery roots only after verifying their exact paths, and run:

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_artifact.py tests/test_real_world_validation_workspace.py -q
```

Expected: the model gate reports `AVAILABLE`, exactly one compatible candidate, and a deterministic artifact fingerprint.

---

### Task 7: Block unsafe local-file replay during active counting

**Files:**
- Modify: `src/hogflow/camera/controller.py`
- Modify: `src/hogflow/presentation/presenter.py`
- Create: `tests/test_phase_10_3a_replay_guard.py`
- Modify: `tests/test_local_video_playback.py` only where its active-session replay expectation conflicts with the new safety rule.

**Interfaces:**
- Consumes: existing `SharedCountingRuntimeAccess.active_binding()` and immutable `MultiDockRuntimeSnapshot`.
- Produces: an authoritative `CameraPipelineLifecycleError` for unsafe explicit or implicit replay and disabled snapshot actions while the lane is occupied.

- [ ] **Step 1: Write the failing active-lane replay tests**

```python
def test_restart_video_is_blocked_when_shared_lane_is_occupied(tmp_path: Path) -> None:
    runtime = _runtime_with_exhausted_file_and_active_session(tmp_path)
    with pytest.raises(CameraPipelineLifecycleError, match="active counting session"):
        runtime.application.restart_video()
    assert runtime.counter.statistics().total_count == 1


def test_start_pipeline_cannot_implicitly_replay_an_active_session(tmp_path: Path) -> None:
    runtime = _runtime_with_exhausted_file_and_active_session(tmp_path)
    with pytest.raises(CameraPipelineLifecycleError, match="active counting session"):
        runtime.application.start_counting_pipeline()


def test_presenter_disables_replay_actions_for_occupied_lane(tmp_path: Path) -> None:
    screen = _exhausted_active_screen(tmp_path)
    assert not screen.actions.restart_video
    assert not screen.actions.start_pipeline
```

- [ ] **Step 2: Run focused tests and verify they fail against current replay semantics**

Run: `& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_replay_guard.py tests/test_local_video_playback.py -q`

Expected: the new tests fail because replay currently preserves active lane state.

- [ ] **Step 3: Add the low-level guard before source reopen or processor reset**

In `CountingPipelineController.restart_video`, after confirming the source is an exhausted local file and before creating a new decoder:

```python
if self._runtime.active_binding() is not None:
    raise CameraPipelineLifecycleError(
        "Cannot replay a local video while an active counting session owns the lane."
    )
```

The same guard covers the `start_counting_pipeline` exhausted-file path because it delegates to `restart_video`. USB/live-camera behavior remains unchanged.

- [ ] **Step 4: Derive safe button states and update regression expectations**

In `_action_state`, compute `replay_safe = not snapshot.counting_lane.occupied` and require it for `restart_video` and exhausted-file `start_pipeline`. Keep the existing error presentation path so a stale direct command shows a clear operator message.

- [ ] **Step 5: Run replay and Phase 9/10 regression tests**

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m pytest tests/test_phase_10_3a_replay_guard.py tests/test_local_video_playback.py tests/test_phase_10_2_detector_integration.py tests/test_operator_application.py -q
```

Expected: PASS; replay after session completion/cancellation remains available, while replay during occupancy is blocked and the count is not reset or incremented.

---

### Task 8: Execute frozen A training, independent B evaluation, and HMI smoke

**Files:**
- Create: `docs/phase_10/phase_10_3a_validation.md`
- Modify: `HOGFLOW_PROJECT_MEMORY.md`
- No media/model artifacts are added to Git.

**Interfaces:**
- Consumes: valid human-reviewed A dataset, local official pretrained checkpoint, frozen configuration, one final artifact, B holdout dataset, and existing CLI/runtime contracts.
- Produces: sanitized local reports, freeze receipt, independent detection metrics, optional counting metrics, and final integration evidence.

- [ ] **Step 1: Complete A validation and refuse training if invalid**

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -c "from hogflow.training.dataset import load_prepared_training_dataset; load_prepared_training_dataset('data/annotations/phase10_3a','data/annotations/phase10_3a/metadata/dataset_manifest.json'); print('A dataset gate passed')"
```

Expected: the command succeeds only with zero fatal annotation findings, non-empty A train/calibration splits, class map 0/pig, and no duplicate frames/checksums.

- [ ] **Step 2: Inspect Ultralytics/Torch/CUDA and obtain one official small pretrained checkpoint**

Use the installed versions to select the canonical smallest official checkpoint. If absent, download only that official checkpoint into ignored `data/training/pretrained/`; verify its SHA-256 and keep it out of `models/`, `weights/`, and `data/models/` until it is the selected final artifact.

- [ ] **Step 3: Run experiment 1 on A and write separate framework/HogFlow metrics**

Use the demo profile, fixed seed, 640 image size, observed safe batch, bounded workers, patience 20, moderate augmentation, and the configured CPU/CUDA device. Write the training run metadata, dataset/configuration fingerprints, calibration TP/FP/FN/precision/recall/F1, mean IoU, framework mAP values when available, and failure summary. Do not inspect B metrics during selection.

- [ ] **Step 4: Freeze the model/configuration before opening B evaluation**

Write a local freeze receipt containing the selected architecture, image size, augmentation, epochs/early-stop policy, confidence, IoU/NMS, device, dataset fingerprint, and selected checkpoint fingerprint. Once written, do not modify these settings based on B.

- [ ] **Step 5: Evaluate B once through the holdout boundary**

Load B only through `load_prepared_evaluation_dataset` and `validate_holdout`. Report labeled-frame TP/FP/FN/precision/recall/F1, optional framework metrics, latency/FPS, obvious tracking issues, and crossing events. If manual totals are missing, write `BLOCKED — MANUAL CROSSING GROUND TRUTH MISSING` and do not calculate count error.

- [ ] **Step 6: Run the real A in-sample HMI smoke**

Inspect the current CLI first:

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m hogflow --help
& .\.venv\phase10_3a\Scripts\python.exe -m hogflow run --help
```

Then run the existing `--video`, `--detector ultralytics`, `--model-path`, `--model-provenance`, `--target-class-name pig`, `--target-class-id 0`, `--confidence-threshold`, `--iou-threshold`, `--inference-size`, and `--device` arguments with the local file. Visually confirm detector boxes, temporary track IDs, directional crossing events, `LIVE COUNT`, and HMI state. Record only what actually executed.

- [ ] **Step 7: Supply manual crossing totals only when the user provides them**

Use the existing sanitized ID worksheet:

```text
demo_video_a -> manual crossing count: ___
demo_video_b -> manual crossing count: ___
```

Store supplied integers in the ignored local evidence record, then calculate system count, signed difference, absolute error, and percentage error. Never infer these values from detection boxes or frame presence.

- [ ] **Step 8: Verify model gate, privacy, and full quality gates**

```powershell
& .\.venv\phase10_3a\Scripts\python.exe -m pytest
& .\.venv\phase10_3a\Scripts\python.exe -m ruff check --no-cache .
& .\.venv\phase10_3a\Scripts\python.exe -m ruff format --check --no-cache .
& .\.venv\phase10_3a\Scripts\python.exe -m compileall -q src
& .\.venv\phase10_3a\Scripts\python.exe -m pip check
& git -c safe.directory=D:/hogflow diff --check
& git -c safe.directory=D:/hogflow ls-files
& git -c safe.directory=D:/hogflow status --ignored --short
```

Expected: all source-only gates pass; no real media, frames, labels, sidecars, model artifacts, or local databases are tracked; the final model gate sees exactly one ignored candidate.

- [ ] **Step 9: Review diff, update memory, commit, push, and verify CI**

Update `HOGFLOW_PROJECT_MEMORY.md` with implemented status, evidence boundaries, environment/runtime facts, and limitations. Do not modify `INVENTION_LOG.md` unless explicitly requested. Commit only source, tests, and sanitized docs with a descriptive message, push `origin/main`, verify local `HEAD` equals `origin/main`, and retrieve the actual GitHub Actions result before reporting it.

---

## Plan self-review

- Dataset authorization, exact roles, ignore policy, and no arbitrary discovery are covered by Task 1.
- Temporal block isolation, timestamp provenance, default policy preservation, and validation are covered by Task 2.
- Deterministic selection, short-video de-duplication, extraction, and A/B leakage checks are covered by Task 3.
- Human-reviewed YOLO boxes, class-zero enforcement, local UI, progress, and resume are covered by Task 4 and the annotation checkpoint.
- Demo training controls, early stopping, moderate augmentation, configuration fingerprinting, framework/HogFlow metric separation, and B holdout evaluation are covered by Task 5.
- Single final model gate and Phase 10.2-compatible provenance are covered by Task 6.
- Unsafe active-session replay for both explicit and implicit paths is covered by Task 7.
- A smoke, B independent evaluation, manual-count blocking, privacy gates, full tests, memory update, publication, and CI verification are covered by Task 8.
- The only intentional exception to source-level splitting is the explicit `temporal_blocked` policy; the default `source_isolated` path remains intact.
- No placeholders, production claims, external uploads, original crowded-video training, persistence, or later roadmap phases are included.
