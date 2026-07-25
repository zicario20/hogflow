# Phase 8.2 - Summary

## Status

Phase 8.2 unloading-session to Phase 7 counting-lifecycle integration is
implemented; representative pig session-count validation and runtime
multi-dock orchestration remain pending.

## Delivered

- `UnloadingSessionCountingService` in the application-oriented
  `hogflow.sessions` package;
- immutable active and finalized lifecycle provenance;
- explicit integration configuration, lifecycle, reuse, and transfer errors;
- one session to one crossing/counting lifecycle binding;
- zeroed lifecycle state on every session start;
- delegation of all positive/reverse/duplicate policy to Phase 7;
- exactly-once transfer into completed session `actual_count`;
- cancellation with count discard and prior-session preservation;
- close-before-commit atomicity;
- lifecycle/source/timestamp validation;
- bounded finalization records;
- architecture tests preserving domain and counting independence;
- synthetic sequential, mixed-type, cancellation, reuse, and failure tests.

## Minimal Phase 7 compatibility correction

`LiveCountingTelemetry.record_started()` now resets current lifecycle count,
current identities, and last frame. Aggregate diagnostics remain bounded and
cumulative. This aligns telemetry with the already-existing Phase 7 behavior
that clears counted identities and sequence state on a fresh start.

No Phase 7 counting policy, public model, protocol, decision, capacity rule, or
reconnect rule changed.

## Preserved boundaries

Phase 8.1 remains immutable and has no counting import. Phase 7 remains unaware
of unloading sessions. The integration layer has no UI, persistence,
networking, API, concurrency, camera, tracker implementation, or storage
dependency.

## Limitations

Evidence is synthetic. A reconnect that changes the crossing lifecycle during
an active unloading session is rejected rather than merged. Multi-dock runtime
coordination, persistence, UI, automatic session generation, pig-specific
evidence, and Phase 8.3 are not implemented.

## Next boundary

Audit Phase 8.2 and its CI. Do not begin Phase 8.3 without an explicit
specification for broader multi-dock orchestration.
