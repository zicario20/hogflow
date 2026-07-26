# Phase 9.3 — Summary

## Status

IMPLEMENTATION COMPLETE — representative camera/pig validation pending.

## Delivered

- one shared source controller with one controlled worker;
- USB-index and local-file configuration;
- immutable camera/pipeline snapshots;
- detector/tracker/crossing processor over existing public contracts;
- exact shared-lane lifecycle routing and stale-result rejection;
- serialized operator/camera access to the caller-serialized Phase 8 lane;
- application methods, CLI options, manual-refresh UI controls/status;
- deterministic source, pipeline, shutdown, counting, presentation, and
  architecture tests;
- ADR-057 and dependency-rule updates.

## Not delivered

- real pig detector weights or validation;
- physical camera smoke test;
- video preview or overlays;
- automatic polling;
- reconnection loop;
- multiple cameras;
- one camera/counter per dock;
- persistence, API, networking, Phase 9.4, or Phase 10.

## Validation

Local focused suite: `98 passed`.

Local full suite: `830 passed, 1 warning`. The unchanged warning is the
Supervision `ByteTrack` deprecation warning. Remote CI is reported separately
after commit/push; local success is not treated as remote success.

Ruff lint/format, compileall, pip check, diff check, import smoke, and both CLI
help entry points passed locally. No physical source was opened.

## Next step

Audit Phase 9.3 before authorizing Phase 9.4 or Phase 10.
