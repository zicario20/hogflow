# Proposed HogFlow Solution

## Proposed concept

HogFlow is an independent computer vision research prototype intended to produce a session-level AI count estimate.

PLANNED conceptual pipeline:

`VIDEO`
`→ DETECTOR`
`→ DETECTIONS`
`→ TRACKER`
`→ TRACKER IDS`
`→ DIRECTIONAL LINE CROSSING`
`→ SESSION COUNTER`
`→ EVENT STORAGE`
`→ OPERATOR UI`
`→ EVALUATION / ANALYTICS`

This pipeline is PLANNED and not yet implemented.

## Detection role

Detection identifies candidate pigs in video frames.

Detection does not directly determine the final session count.

## Tracking role

Tracking associates detections across multiple frames using tracker IDs.

A tracker ID is a technical tracking identity.

It is not a permanent biological identity.

ID switches, lost tracks, and fragmented tracks are technical risks.

## Counting unit

The conceptual counting unit is one unique positive tracker crossing per active session.

HogFlow does not count every detection in every frame.

## Directional counting rule

The planned counting concept uses:

* a configured virtual line
* a positive direction toward the weighing area
* a positive crossing candidate
* a reverse-direction event
* duplicate positive crossing prevention

Conceptual logic:

`tracker crosses positive direction`
`AND`
`tracker_id not in counted_tracker_ids`
`→ positive count +1`

Then:

`tracker_id added to counted_tracker_ids`

Reverse crossing:

`tracker crosses reverse direction`
`→ record reverse event`
`→ do not automatically increment positive count`

Repeated positive crossing from the same tracker during the same active session:

`→ do not increment positive count again`

This logic is PLANNED and not yet implemented.

## Session concept

HogFlow models three sequential section sessions.

`IDLE`
`→ SELECT SECTION`
`→ START SESSION`
`→ COUNTING`
`→ END SESSION`
`→ REVIEW RESULT`
`→ CONFIRM OR FLAG FOR REVIEW`
`→ COMPLETED`

Session assumptions for the MVP:

* only one session may be active in the MVP
* operator starts and ends sessions manually
* counted tracker IDs are session-scoped
* new session receives independent counting state

## Human role

The initial research prototype is semi-automatic.

The operator remains responsible for:

* selecting the section
* starting the session
* ending the session
* reviewing results
* confirming or flagging the session for review

HogFlow is not presented as replacing the operator.

## Ground truth

Human-verified ground truth is required to evaluate the AI count.

AI count and ground-truth count must remain separate data fields.

The design must not silently change AI output to match ground truth.

## Review events

Uncertain technical conditions may produce review events.

Candidate review reasons may include:

* tracker ID switch suspicion
* lost track
* fragmented track
* dense crossing
* multiple pigs crossing together
* poor visibility
* reverse movement ambiguity

Review events do not automatically change the AI count.

## Optional weight consistency

Group-weight consistency is only an OPTIONAL secondary future review signal.

It is not the primary counting algorithm.

It cannot silently rewrite AI count.

No universal valid pig-weight range should be assumed.
