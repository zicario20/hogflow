# Phase 10.3C — Frozen Demo Validation Environment

This is a sanitized, source-controlled record for the frozen HogFlow Pig
Detector Demo V2 validation environment. It is not a production deployment
specification and contains no local paths, credentials, media, or weights.

## Environment used to train and validate V2

| Component | Frozen value |
| --- | --- |
| Python | `3.12.14` |
| Torch | `2.11.0+cu128` |
| Torchvision | `0.26.0+cu128` |
| CUDA runtime reported by Torch | `12.8` |
| GPU | `NVIDIA GeForce RTX 5070 Ti Laptop GPU` |
| Ultralytics | `8.4.135` |
| OpenCV | `4.14.0.94` |
| Supervision | `0.29.1` |
| LAP | `0.5.13` |
| NumPy | `2.5.2` |
| Environment fingerprint | `c9b694c500915733c2cf2c142bbe6392b559e7fb0d985f1de559848fa6befa92` |

The GPU environment is project-local and ignored. Its imports and CUDA
availability were verified before Phase 10.3B V2 execution. It intentionally
does not upgrade Supervision/ByteTrack before the frozen C evaluation; the
known ByteTrack deprecation warning is preserved as technical debt.

## Quality-gate environment

Source-only quality gates continue to run in the project-local Python 3.12
CPU environment. That environment reports Python `3.12.14`, Torch
`2.13.0+cpu`, Ultralytics `8.4.135`, OpenCV `4.14.0`, and Supervision
`0.29.1`. It is not the environment used for V2 GPU inference.

## Reproduction policy

Reproduction must use Python 3.12, the exact versions above, the repository's
declared dependencies, and the official PyTorch CUDA wheel family compatible
with CUDA 12.8. The exact local installer command may vary by supported
Windows wheel availability; after installation, the version table and CUDA
availability must match before evaluating C. No global Python 3.14, cloud
training, external datasets, or SaaS annotation services are permitted.

## Frozen detector boundary

- Model identity: `hogflow_pig_demo_v2`
- Artifact SHA-256: `892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c`
- Detector configuration fingerprint: `611a4b66efe97b38ef1aa07f5cace4d57aa366ccf1d9b4e4f50a703fc11191c0`
- Runtime environment policy: existing Phase 10.2 policy; resolved V2 device was `cuda:0`
- Tracker implementation: Supervision ByteTrack `0.29.1`, unchanged through C

The environment and detector are frozen before any C authorization. Any
runtime mismatch is a stop condition, not a reason to silently substitute a
different stack.
