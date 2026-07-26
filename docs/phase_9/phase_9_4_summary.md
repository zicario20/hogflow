# Phase 9.4 — Summary

## Status

IMPLEMENTATION COMPLETE — representative live-camera and pig validation
pending.

## Delivered

- one framework-neutral latest-frame-only visual channel;
- immutable preview frame, track, crossing, health, and telemetry models;
- current tracked-box, temporary-ID, line, anchor, side, direction, dimension,
  camera, and pipeline diagnostics;
- UI-thread-only Tk rendering and a single bounded/cancellable refresh;
- application preview operations with no infrastructure access from
  presentation;
- render/publication failure isolation from counting;
- bounded USB source reopen with disconnected/opening/running health;
- reconnect reset for tracker/crossing state without fabricated frames;
- effective FPS, temporary failure, stale-result, recovery, worker, and preview
  metrics;
- deterministic synthetic and architecture tests;
- ADR-058 and dependency-rule updates.

## Preserved

- one shared physical source;
- one shared worker and detector/tracker/crossing pipeline;
- one shared counting lane and Phase 7 counter;
- four independent dock business contexts;
- Phase 7 counting policy;
- Phase 8 business rules and snapshots;
- exact source/lifecycle routing;
- no recording, persistence, network, or Phase 10.

## Limitations

- no physical camera or real GUI smoke test was performed;
- default detector/tracker adapters are empty and produce no pig evidence;
- no validated pig-specific weights exist in the repository;
- overlay throughput on deployment hardware is unmeasured;
- USB reopen behavior depends on the actual backend;
- tracker-ID reuse after reconnect remains an undercount/overcount risk;
- no camera calibration, line editor, RTSP recovery certification, storage, or
  production hardening exists;
- passing synthetic tests do not establish pig-count accuracy or production
  readiness.

## Next boundary

Audit Phase 9.4 and its remote CI before beginning Phase 10. Do not add storage
or broader product functionality as part of that audit.
