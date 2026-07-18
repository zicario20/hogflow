# Phase 4.2 — Source-Video Dataset Splitting

## Principle

HogFlow assigns opaque source clip IDs—not frames—to `train`, `validation`, or
`test`. Every frame derived from a source inherits that assignment. One clip ID
can occur in exactly one split.

Assignments are deterministic and order-independent. The rank is derived from
the explicit seed and opaque clip ID; filenames, source paths, review notes, and
authorization details are not inputs to randomization or output.

## Default ratios

- train: 70%
- validation: 20%
- test: 10%

Ratios must be finite, positive, and sum to one. Largest-remainder allocation
is used, with non-empty splits only when the approved minimum source count is
met.

## Small datasets

The default minimum for an evaluation split is ten independent source clips.
Below that threshold, all selected sources receive the `preparation` assignment
and the plan records:

- `insufficient_source_diversity_for_train_validation_test`; and
- `preparation_only_not_statistically_meaningful`.

This avoids presenting three clips as a meaningful 70/20/10 experiment. A clip
is never copied into multiple splits, and frames are never split independently
to compensate for insufficient sources. The threshold may be explicitly
changed for a synthetic or narrowly bounded preparation exercise, but doing so
does not make the split statistically representative.

## Command

```bash
python -m hogflow.data.dataset_splitting \
  --selection data/processed/phase_4/detection_selection.json \
  --output data/processed/phase_4/source_split_plan.json \
  --seed 42
```

The output contains only opaque clip IDs, assignments, ratios, warnings, and
counts. It contains no source filename or path.
