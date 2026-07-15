# Phase 2.3 — Generic Pipeline Usage

## Environment setup

HogFlow requires Python 3.10 or newer. Install runtime and development
dependencies from the repository root:

```bash
python -m pip install -e ".[dev]"
```

Ultralytics ByteTrack requires its LAP assignment dependency at runtime.
HogFlow declares `lap>=0.5.12` explicitly so environments do not depend on
Ultralytics attempting an installation during tracker import.

## Validation commands

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src
```

Tests use synthetic frames, fake model/tracker backends, and a generated local
video. Ordinary tests do not download a model, require a GPU, or use employer
media.

## Generic CLI

The Phase 1 command and arguments remain compatible:

```bash
python -m hogflow.video.generic_counter \
  --input data/raw/authorized_sample.mp4 \
  --output data/processed/phase_2_3_output.mp4 \
  --events data/processed/phase_2_3_events.jsonl \
  --class person \
  --line-start 100,300 \
  --line-end 900,300 \
  --positive-direction negative-to-positive \
  --confidence 0.35 \
  --line-epsilon 1.0 \
  --model yolo26n.pt \
  --max-frames 300
```

Coordinates must be selected for the actual input frame. The line endpoints
define a finite segment; crossing an invisible extension is not counted.
Reversing start/end reverses the side convention and therefore changes the
interpretation of positive direction.

Available arguments remain:

* `--input`
* `--output`
* `--events`
* `--class`
* `--line-start`
* `--line-end`
* `--positive-direction`
* `--confidence`
* `--line-epsilon`
* `--model`
* `--device`
* `--show`
* `--max-frames`

## Outputs

The annotated video contains bounding boxes, tracker IDs where available, the
configured finite segment, the selected class, and current unique positive
count.

Each non-empty JSONL line is one actual finite-segment crossing event with the
unchanged fields:

* `frame_index`
* `timestamp_seconds`
* `tracker_id`
* `direction`
* `counted`
* `previous_point`
* `current_point`
* `current_positive_count`

Reverse events are logged with `counted: false`. A repeated valid positive
crossing for an already-counted tracker is also logged with `counted: false`.

## Limitations

This remains a generic people/vehicle research pipeline. It has no pig-specific
detector, pig-specific tracking validation, sessions, persistence, user
interface, or ground-truth evaluation. Tracker ID switches and fragmentation
can affect counts. RGB-byte conversion adds overhead. A real-model smoke test
requires a suitable local public or explicitly authorized video and available
model weights; synthetic infrastructure tests do not establish detection or
counting accuracy.
