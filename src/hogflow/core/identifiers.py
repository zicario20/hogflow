"""Deterministic opaque identifiers for privacy-preserving local workflows."""

from __future__ import annotations

import hashlib

from hogflow.core.errors import InputDataError


def phase4_clip_id(source_key: str) -> str:
    """Return the stable opaque clip ID used by Phase 4 preparation tools.

    ``source_key`` may be a local inventory-relative path, but it is used only
    as hash input and must never be included in the returned identifier.
    """

    if not isinstance(source_key, str) or not source_key:
        raise InputDataError("A non-empty source key is required to derive a clip ID.")
    return hashlib.sha256(f"hogflow-phase4:{source_key}".encode()).hexdigest()[:24]


__all__ = ["phase4_clip_id"]
