# HogFlow Phase 10.3A — Provisional Pig Dataset & Demo Model Design

## Status and decision

This document specifies the explicitly authorized experimental subphase
**Phase 10.3A — Provisional Pig Dataset & Demo Model Training**. It extends
the existing Phase 4.2/4.3 and Phase 10.2 infrastructure to prepare a local,
human-reviewed pig dataset, fine-tune one local demo detector, and evaluate
the complete detector-to-counter flow on two owner-authorized videos.

It is not a replacement for the Phase 10.3 catalog or a new normative roadmap
phase. It does not establish production readiness, a representative pilot, or
counting accuracy unless manual directional crossing totals are later supplied.

## Scope

The only source media are the two explicitly selected local inputs represented
by sanitized IDs `demo_video_a` and `demo_video_b`. Their real basenames live
only in an ignored local authorization manifest. No source-controlled code,
test, report, or documentation records those names or a local path.

`demo_video_a` is the provisional development source. Its non-overlapping
temporal blocks provide training frames and internal calibration frames.
`demo_video_b` is an independent source. It is excluded from model training,
confidence tuning, epoch selection, augmentation selection, and detector
selection. It is used only after the Video A configuration and selected model
are frozen.

The existing strict Phase 10.3 catalog and its fixed three-video processing
order remain unmodified. The original videos are not inputs to the first
Phase 10.3A training or independent evaluation run.

## Existing components to reuse

The implementation reuses, rather than replaces:

- deterministic timestamp selection in `hogflow.data.frame_selection`;
- local OpenCV extraction in `hogflow.data.frame_extraction`;
- YOLO labels, manifests, and structural validation in `hogflow.annotation`;
- deterministic detection evaluation in `hogflow.evaluation`;
- the `DetectorTrainer` contract and `YOLOBaselineTrainer` adapter;
- Phase 10.2 `PigDetectorConfiguration` and the Ultralytics runtime boundary;
- the Phase 9.3/9.4 processor, tracker, crossing, shared lane, and HMI;
- the Phase 10.3 local-only model gate, without broadening its media catalog.

## Dataset authorization and privacy

An ignored local authorization file under `data/training/` will contain exactly
two records: the sanitized IDs, their real local basenames, roles, and the
permitted `pig` class. Loading it will reject duplicated IDs, duplicated
basenames, missing selected media, unexpected records, tracked artifacts, and
any attempt to discover arbitrary files.

The repository ignore rules will explicitly cover `data/training/` in addition
to the existing raw media, annotation, evaluation, run, metric, model, and
weight protections. Real media, extracted images, labels, authorization
records, count worksheets, checkpoints, reports, model artifacts, and review
sidecars remain local and untracked.

## Temporal split policy

The present annotation validator deliberately rejects assigning one source to
more than one split. That remains the default `source_isolated` policy.

Phase 10.3A adds one explicit `temporal_blocked` policy to the existing
manifest/validator—not a parallel dataset framework. Under that opt-in policy:

- every active record has its opaque source ID and extracted timestamp;
- each record belongs to exactly one declared temporal block;
- blocks are non-overlapping and assigned to exactly one split;
- Video A training and calibration blocks have a positive configured buffer;
- no image checksum or frame ID appears in multiple splits; and
- Video B cannot appear in the development manifest.

The policy will be represented in the sanitized annotation manifest and tested
alongside the existing source-isolation behavior. A normal Phase 4 dataset
continues to reject source leakage unchanged.

## Frame selection and human annotation

Selection begins with deterministic timeline sampling and then uses human
review to remove redundant or unresolvable candidates. The short source
durations make the requested frame counts targets rather than quotas: no near
duplicate frames will be retained merely to reach a numerical target.

Selected frames retain only opaque IDs in the annotation workspace. Each frame
will receive one existing status: `annotated`, `verified_empty`,
`needs_manual_review`, or `excluded`. Natural negative frames are included
only when a human confirms that no pig is present. The only detector class is
`0 = pig`.

A small local `scripts/annotate_pigs.py` helper will be added because the
repository has no practical box-drawing interface. It is a development tool,
not a HogFlow runtime component. It will open the selected ignored images,
preserve their native geometry, support draw/delete/save/previous/next,
reopen existing YOLO labels, and write labels through the existing policy and
serialization contracts. It will neither upload data nor import business,
camera, session, tracking, or counting code.

Human-reviewed boxes remain a hard gate. No training starts until the existing
annotation validator reports no fatal findings.

## Training and model selection

The existing `TrainingConfiguration` and `YOLOBaselineTrainer` remain the
single training abstraction. They will gain narrowly scoped reproducible
controls required for this experiment: early-stopping patience and a bounded
moderate augmentation profile. Effective values are recorded in sanitized
local provenance and contribute to a deterministic configuration fingerprint.

The first experiment uses the smallest compatible official Ultralytics
pretrained detector available locally. If a compatible base checkpoint is not
present, exactly that official checkpoint may be downloaded to an ignored
training-only location after confirming the installed Ultralytics API and
version. No base checkpoint is placed in a Phase 10.3 model-discovery root.

The default experiment is a fixed-seed, 640-pixel run with Windows-safe
workers, an observed safe integer batch size, no aggressive geometric changes,
and a bounded early-stopping policy. The actual device follows preflight
evidence: CUDA only when Torch reports a usable compatible device; otherwise
CPU is explicitly reported. A larger model is considered only after a
structurally valid small-model experiment underperforms and is recorded as a
separate experiment.

Video A internal calibration produces HogFlow TP/FP/FN, precision, recall,
F1, mean matched IoU, and separately named framework metrics such as mAP when
the framework provides them. It is development evidence, not independent
generalization evidence.

Once architecture, image size, augmentation, epoch/early-stop policy,
confidence, and IoU/NMS settings are frozen, a local freeze receipt is written
before Video B evaluation. Video B is evaluated through a narrowly extended
evaluation-only use of the existing detector and annotation contracts, so its
labels are not required by the training dataset or fingerprint. The evaluation
may report framework metrics where the installed API supports them; unavailable
framework metrics remain explicitly unavailable rather than fabricated.

## Model artifact and Phase 10.2 integration

Training checkpoints remain under ignored training-run roots. Only one selected
demo model will be copied to an approved ignored model root, with a sanitized
identity such as `hogflow_pig_demo.pt`. Extra compatible candidate artifacts
will remain outside Phase 10.3 model-discovery roots.

The selected artifact must produce an `AVAILABLE` Phase 10.3 model gate and
load via `PigDetectorConfiguration` with `target_class_name = pig` and
`target_class_ids = (0,)`. Sanitized local provenance records backend,
format, model identity, SHA-256, target class, framework version, image size,
dataset fingerprint, configuration fingerprint, selection rationale, date,
and completeness. It contains no paths, usernames, media basenames, or
credentials.

The end-to-end smoke test uses the current composition only:

```text
detector -> tracker -> directional crossing -> lifecycle counter -> shared lane -> HMI
```

It does not create a second inference or counting stack and does not redesign
the HMI. Video A smoke output is explicitly in-sample development evidence.

## Manual crossing ground truth

Existing Phase 3 review sidecars establish scene authorization and suitability;
they do not contain a manual crossing total. Phase 10.3A will generate local
review templates where missing and a separate ignored worksheet using the
existing sanitized-video-ID/manual-total convention. Its initial value is
missing/unknown, never a fabricated number.

After the user watches each full source under the existing directional line
rule, the worksheet accepts one non-negative integer per eligible video.
Only then may the report calculate system-minus-human difference, absolute
error, and percentage count error. Until then, detector and tracking evidence
may proceed but count-accuracy evidence remains blocked.

## Replay safety

Current local-file replay resets tracker and crossing state while preserving an
active shared-lane session. This is unsafe for real detector evidence because
the same animals can receive new temporary tracker IDs. The implementation
will block both explicit `Restart Video` and the exhausted-file implicit replay
path behind `Start Pipeline` whenever the shared lane is occupied.

The low-level camera controller performs the authoritative check through its
existing runtime-access port. Presentation derives disabled replay controls
from the same immutable lane snapshot. After a session is completed or
cancelled, replay is again available and begins a separate safe lifecycle.
USB/live-camera semantics do not change.

## Verification and delivery

Every source behavior change follows test-first development. New tests cover
the exact two-record local authorization, arbitrary-media rejection, temporal
block separation, default source-isolation preservation, class-zero and
negative-frame rules, deterministic fingerprints, model-candidate gating,
sanitized provenance, and replay blocking with an active lane.

Before any local experiment, the moved project environment is rebuilt or
repaired with the available Python 3.12 runtime. Python 3.14 is not used for
project tests, extraction, annotation, training, or validation.

The final quality gates are the repository test suite, Ruff lint/format,
compileall, pip dependency check, diff check, and CLI help commands using that
Python 3.12 environment. If source-controlled changes pass, they are committed
and pushed to `origin/main`. The local artifacts never enter the commit. CI
status is retrieved after the push rather than assumed.

## Explicit non-goals

- No Phase 10 persistence, Phase 10.4, Phase 11, analytics, review clips, or
  pilot-readiness work.
- No model or media upload, cloud annotation, external dataset download, or
  production training claim.
- No changes to receiving, session, reverse-count, or crossing business rules.
- No use of the original Phase 10.3 videos for initial training.
- No production validation claim. The selected artifact is always labeled
  **DEMO MODEL — NOT PRODUCTION VALIDATED**.
