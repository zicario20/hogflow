# Phase 3 — Summary

## Status

Phase 3 infrastructure implemented; real authorized dataset acquisition and review in
progress.

## Delivered

- local `raw`, `interim`, and `processed` data workspace with Git safeguards;
- immutable framework-neutral video metadata, review, manifest, and summary models;
- deterministic recursive discovery for explicit video extensions;
- bounded OpenCV metadata and decode validation;
- feature-based global camera-motion estimate with conservative labels;
- strict JSON authorization and manual scene-review sidecars;
- optional JSON clip-boundary manifest for already-cut clips;
- conservative detection, tracking, counting, stress-test, and manual-review labels;
- atomic JSON, CSV, and Markdown inventory output;
- `python -m hogflow.data.inventory` local CLI; and
- synthetic and framework-boundary tests requiring no downloaded or real pig media.

## Architecture result

OpenCV and NumPy remain inside `hogflow.video.metadata`. Public data models, discovery,
sidecar parsing, manifest parsing, suitability rules, and summaries remain framework-neutral.
The inventory CLI composes these layers and never modifies input videos. Relative report paths
avoid leaking local absolute paths into generated inventory records.

## Evidence boundary

Synthetic videos exercise video opening, bounded sampling, metadata, camera translation,
report generation, and empty-dataset behavior. They do not validate real pig-video quality,
pig detection, pig tracking, count accuracy, or camera stability in an operational setting.

No real pig media is committed. A real clip can enter a candidate category only after the
user confirms authorization in a local sidecar. Counting candidacy additionally requires
manual confirmation of static camera, clear passage, predominant movement direction, and a
usable virtual-line location.

## Known limitations

- Real authorized pig-video collection and review may still be ongoing.
- Bounded sampling cannot detect every corrupt frame in a long source.
- Container metadata can be inaccurate.
- Feature-based motion estimates can be biased by dense animal motion.
- No automatic authorization or license determination is attempted.
- No video cutting, model training, fine-tuning, tracking evaluation, counting evaluation,
  sessions, storage, UI, or analytics is implemented.

## Roadmap boundary

Phase 3 adds data-acquisition and inventory infrastructure only. Phase 4, the pig detection
baseline, has not started.
