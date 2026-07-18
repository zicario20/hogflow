# Phase 3 — Usage

## Environment

From the repository root, create or activate a Python 3.10+ environment and install the
project with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

OpenCV and NumPy are loaded only when a video is inspected. Empty-directory inventory and
framework-neutral model imports do not require video decoding.

## Prepare local data

1. Confirm that each clip is authorized or licensed for the intended project use.
2. Place unmodified originals in `data/raw/`.
3. Copy `data/review_sidecar.example.json` beside each clip and rename it to
   `<full-video-filename>.review.json`.
4. Complete the authorization and scene-review fields without credentials, personal data, or
   confidential operational details.
5. Optionally copy `data/clip_manifest.example.json` and record boundaries for manually cut
   static sections.

Do not download media as part of this workflow. Do not commit source clips, cut clips, frames,
thumbnails, reports, or weights.

## Generate an inventory

```bash
python -m hogflow.data.inventory \
  --input data/raw \
  --output data/processed/inventory
```

Optional manifest:

```bash
python -m hogflow.data.inventory \
  --input data/raw \
  --output data/processed/inventory \
  --clip-manifest data/clip_manifest.local.json
```

The command also supports bounded-sampling, stability-threshold, feature-count, sample-size,
and minimum-duration options. Inspect all options with:

```bash
python -m hogflow.data.inventory --help
```

Default output files:

- `data/processed/inventory/inventory.json`: complete machine-readable metadata;
- `data/processed/inventory/inventory.csv`: one row per discovered video; and
- `data/processed/inventory/inventory.md`: readable summary, problems, and review queue.

No image frame or thumbnail is generated.

## Interpret results

Treat automatic stability as a review hint. `likely_static` does not prove that the camera is
fixed, and `moving_camera` can be caused by foreground animals dominating feature matches.
`unknown` means evidence was insufficient.

Treat all suitability values as inventory labels. They do not demonstrate pig detection,
tracking, counting accuracy, or commercial viability. A `counting_candidate` appears only
after all required manual scene confirmations, but still requires later representative
technical evaluation.

## Validation commands

```bash
python --version
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src
python -c "import hogflow.data; import hogflow.data.inventory; import hogflow.video.metadata"
python -m hogflow.data.inventory --input <empty-directory> --output <empty-output>
python -m hogflow.data.inventory --input <synthetic-video-directory> --output <synthetic-output>
git diff --check
```

No static type checker is configured in `pyproject.toml` during Phase 3.

## Current limitations

- No real pig clip is bundled or validated.
- No downloader or video cutter is implemented.
- Metadata properties depend on the container and OpenCV backend.
- Bounded samples can miss corruption between sampled positions.
- Camera-motion labels can be wrong in animal-dominated scenes.
- Manual review does not replace later detector, tracker, or count evaluation.
- Phase 4 and later capabilities are not implemented here.
