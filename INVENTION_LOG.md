# HogFlow Invention Log

This document is a chronological invention-development record for HogFlow.

Future material invention-concept changes should be appended as dated entries below. Preserve historical entries as written. Do not rewrite earlier entries to match later architecture changes. This document does not make patentability, ownership, inventorship, or legal-protection claims.

## Historical entries

### July 12, 2026

Historical concept entry reconstructed from preserved project source material.

This entry preserves supported concepts from the July 12, 2026 project record but is not presented as a verbatim transcription of the original wording.

Conceived HogFlow as a computer vision research concept for counting unique livestock moving directionally through a constrained passage toward a weighing area. The concept is centered on pig detection, multi-object tracking, and a virtual directional line used to evaluate whether an individual tracked pig should contribute a positive count.

The intended counting logic is tracker-based rather than frame-based. A tracked pig should contribute at most one positive count within an active session, with session-scoped counted tracker IDs used to prevent duplicate positive crossings from the same tracker during that session.

Positive counting is intended only for crossings in the configured direction toward the weighing area. Reverse-direction movement should be handled as an event and should not automatically increase the positive count.

The broader workflow concept includes a three-section session model with operator-managed session boundaries, event and session storage, and later comparison between AI output and human-verified ground truth.

Uncertain cases should remain reviewable rather than silently resolved. The concept therefore includes review events for uncertain counting or tracking outcomes, a later failure-review or review-clips workflow, and optional group-weight consistency analysis as a secondary review signal rather than a primary counting rule.

Status of this July 12, 2026 entry: concept and research hypothesis only. This entry does not assert validated implementation, validated counting accuracy, operational deployment, or production readiness.

## Future updates

Append future material invention-concept changes here as dated entries when explicitly requested.
