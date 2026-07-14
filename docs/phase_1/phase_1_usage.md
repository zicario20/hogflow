# Phase 1 Usage — Generic Counter

## Requirements

* Python 3.10 or newer
* a local video that the user is authorized to use
* sufficient disk space for the annotated output video
* network access on first use if the default public pretrained model weights are not already cached

No sample video ships with the repository. Do not add arbitrary downloaded or copyrighted video files to Git.

## Environment setup

From the repository root in Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

The editable install makes the `src/` package importable and installs the Phase 1 runtime and development dependencies declared in `pyproject.toml`.

## Run tests

```powershell
python -m pytest
```

The core unit tests use synthetic points only. They do not load a video, AI model, OpenCV window, network resource, or GPU.

## Run Ruff

```powershell
python -m ruff check .
```

## Run the generic counter

People example:

```powershell
python -m hogflow.video.generic_counter `
    --input data/raw/people_sample.mp4 `
    --output data/processed/people_counted.mp4 `
    --events data/processed/people_events.jsonl `
    --class person `
    --line-start 100,300 `
    --line-end 1100,300 `
    --positive-direction negative-to-positive `
    --confidence 0.35
```

Vehicle example:

```powershell
python -m hogflow.video.generic_counter `
    --input data/raw/vehicle_sample.mp4 `
    --output data/processed/vehicle_counted.mp4 `
    --events data/processed/vehicle_events.jsonl `
    --class car `
    --line-start 640,100 `
    --line-end 640,650 `
    --positive-direction positive-to-negative `
    --confidence 0.35 `
    --max-frames 300
```

These paths are examples. The files do not ship with the repository. Use a public video with suitable redistribution/use rights, a synthetic video, or another local video you are explicitly authorized to process.

Arguments:

* `--input`: existing local video file
* `--output`: annotated output video path; parent directories are created
* `--events`: JSON Lines event-log path; parent directories are created
* `--class`: exact class name exposed by the selected detector, such as `person` or `car`
* `--line-start`: first directed-line endpoint in `x,y` pixels
* `--line-end`: second directed-line endpoint in `x,y` pixels
* `--positive-direction`: side transition eligible to increment the count
* `--confidence`: detector confidence threshold greater than 0 and at most 1
* `--line-epsilon`: optional near-line tolerance in pixels; default is 1.0
* `--model`: optional Ultralytics model name or path; default is `yolo26n.pt`
* `--device`: optional Ultralytics device such as `cpu` or `0`
* `--show`: optional OpenCV preview window; omitted by default for non-interactive use
* `--max-frames`: optional positive frame limit for a bounded run

The first run may download the small public default model weights. Model weight files are excluded by `.gitignore`.

## Choose line coordinates

Line coordinates use input-video pixel coordinates:

* top-left is `(0, 0)`
* x increases to the right
* y increases downward

Place the line where complete tracked objects are expected to pass through a constrained part of the scene. A line that misses object anchor points, lies inside a heavy occlusion region, or is too close to frame boundaries can create misleading results.

The counter supports horizontal, vertical, and diagonal finite line segments. The line start and end must be different. Objects whose movement crosses only the invisible extension beyond either endpoint are not counted and do not produce crossing events.

## Positive direction

The two options are:

* `negative-to-positive`: count the first transition from the line's negative side to its positive side for each tracker ID
* `positive-to-negative`: count the first transition from the line's positive side to its negative side for each tracker ID

Negative and positive sides are not universally equivalent to physical left/right or up/down. Their meaning depends on the directed line. Reversing the line start and end points preserves the same finite segment but reverses the signed side convention and positive-direction interpretation.

If initial output counts movement in the wrong physical direction, either change `--positive-direction` or reverse the line endpoints, then verify the result visually.

## Output files

The annotated video contains:

* selected-class bounding boxes
* tracker IDs when available
* the virtual line
* `COUNT: N`, the current unique positive count
* the selected class name

The JSONL file contains one object per actual finite-segment crossing event. It does not contain one record per frame. Each event includes frame index, timestamp, tracker ID, actual side-transition direction, whether the event incremented the count, previous and current points, and the current positive count. Reverse events and repeated positive crossings remain present with `counted: false` only when the tracked movement intersects the configured segment.

## Limitations

This generic counter does not validate pig counting, HogFlow accuracy, operational performance, labor savings, or commercial value. Results remain sensitive to detector errors, tracker identity instability, occlusion, line placement, frame rate, camera perspective, and video quality.
