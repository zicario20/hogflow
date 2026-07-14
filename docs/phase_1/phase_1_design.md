# Phase 1 Design — Generic Directional Line-Crossing Counter

## Objective

Phase 1 implements a generic proof of concept for this technical question:

`Can the generic detection → tracking → directional line-crossing pipeline count unique tracked objects without counting the same tracker repeatedly?`

The implementation accepts a local people or vehicle video, obtains generic detections and tracker IDs, passes bottom-center observations to HogFlow's detector-independent counter, logs crossing events, and writes an annotated video.

## Why people or vehicles

Common pretrained object-detection models already support generic classes such as `person`, `car`, and other road vehicles. Those classes allow the detection, tracking, and crossing integration to be exercised without pig-specific training or data.

Success in this phase does not validate pig counting. People and vehicle movement do not establish performance for pigs, livestock facilities, dense animal groups, or any operational HogFlow workflow.

## Phase 1 pipeline

`VIDEO`
`→ GENERIC DETECTOR`
`→ CLASS FILTER`
`→ TRACKER`
`→ TRACKER ID`
`→ BOTTOM-CENTER POINT`
`→ DIRECTIONAL LINE COUNTER`
`→ UNIQUE POSITIVE COUNT`
`→ EVENT LOG`
`→ ANNOTATED VIDEO`

Ultralytics applies the requested class and confidence settings before its ByteTrack update. Supervision converts the result for annotation. The project's `DirectionalLineCounter` is the only source of the displayed and logged positive count.

## Core counting logic

The core module defines typed `Point`, `Line`, `CrossingDirection`, `CrossingEvent`, and `DirectionalLineCounter` structures. It has no dependency on OpenCV, Supervision, Ultralytics, a video file, a model, or a GPU.

For a directed line from A to B and an observation P, the side calculation is the signed 2D cross product:

`cross(B - A, P - A)`

A positive value identifies the positive mathematical side of the directed line; a negative value identifies the negative side. Reversing the line endpoints reverses the sign convention. The counter normalizes the cross-product magnitude by line length, producing a signed perpendicular distance for epsilon comparison.

Observations are classified as:

* negative side
* near line
* positive side

The configurable epsilon is a perpendicular-distance tolerance in point-coordinate units. For video coordinates, those units are pixels. Near-line observations do not replace the tracker's last meaningful side. Therefore:

* `negative → near line → positive` creates one crossing
* `negative → near line → negative` creates no crossing
* repeated observations on the same side create no additional events

The configured positive direction is either `negative_to_positive` or `positive_to_negative`. A crossing in that direction is eligible to increment the count. The opposite transition is retained as a reverse event and does not increment the count.

The counter maintains a set of tracker IDs that already contributed a positive count. A repeated positive crossing for one of those IDs remains observable as an event with `counted = false`.

`reset()` clears counted IDs, transient tracker-side state, and internally stored crossing events. The video integration may discard transient side state after prolonged tracker inactivity, but it does not remove the ID from the counted-ID set during the same run.

## Finite counting segment

The displayed counting boundary is the finite segment between the configured line start and end points. The directed infinite line through those endpoints is used only to classify meaningful sides; a side transition alone is insufficient to create an event.

For each opposite-side transition, the counter also verifies that the movement segment from the last meaningful tracker point to the current meaningful point intersects the configured finite counting segment. Crossings of the invisible line extensions beyond either endpoint are ignored for positive, reverse, and repeated-positive events.

An intersection exactly at a counting-segment endpoint may count when the tracker changes meaningful sides. There is no hidden endpoint exclusion rule. Parallel movement, collinear movement, sliding along the line, and endpoint touches without a meaningful side change do not count.

The configured start-to-end order still controls the side sign and the interpretation of `negative_to_positive` and `positive_to_negative`. Reversing the endpoints therefore reverses the side convention and positive-direction interpretation while preserving the same finite geometric boundary.

## Counting unit

`One unique eligible positive tracker crossing per Phase 1 counter run.`

This is a technical proof-of-concept rule. A tracker ID is not a permanent physical or biological identity, and the rule does not solve tracker fragmentation, tracker ID switches, or re-identification.

## Detector choice

Phase 1 uses the Ultralytics package in the `8.4` release series with the small pretrained `yolo26n.pt` detection model by default. The model supports common generic classes and is substantially smaller than the larger model variants, making it appropriate for a local proof of concept. The requested class name is checked against the loaded model's names; an invalid class produces an error rather than silently selecting another class.

The model may download its public pretrained weights on first use. No custom model is trained, and no pig-specific weights are used.

## Tracker choice

Phase 1 uses the currently supported ByteTrack backend bundled with Ultralytics, selected through `tracker="bytetrack.yaml"`. Consecutive frames are passed through `model.track(..., persist=True)`, and tracker IDs are returned in the tracking result and preserved by Supervision's `Detections.from_ultralytics` conversion.

The deprecated Supervision ByteTrack wrapper is not used. A separate future tracking abstraction is intentionally deferred to Phase 2.

## Anchor point

Each tracked bounding box contributes its bottom-center point:

`x = (x_min + x_max) / 2`

`y = y_max`

Bottom-center is a simple proxy for the object's contact or location position relative to the virtual line. The video loop sends this point to `DirectionalLineCounter` and does not implement separate crossing rules.

## Known failure risks

* detector false positives
* detector missed objects
* occlusion
* tracker ID switches
* tracker fragmentation
* temporary lost tracks
* line placement sensitivity
* camera perspective
* low frame rate
* fast movement
* overlapping objects
* stale-state cleanup causing a returning uncounted tracker to establish new side state

## Phase boundary

Phase 1 does not include:

* pig-specific detection or validation
* custom model training
* a future detector interface or tracker abstraction
* three-section session management
* SQLite or other event storage
* an operator UI
* ground-truth count evaluation
* analytics or pilot readiness
* production deployment architecture
