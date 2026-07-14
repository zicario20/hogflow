# Current Conceptual Process

## Process boundary

The conceptual process boundary is animal movement from a grouped holding state through a constrained passage toward a weighing or downstream processing area.

## Three-section conceptual workflow

The HogFlow MVP concept assumes a three-section sequence in which animals may be moved sequentially by section.

### SECTION 1

Animals conceptually begin in a grouped state and may be moved as the first section toward the constrained passage and downstream area.

### SECTION 2

After the first section ends, a second section may be selected and moved through the same general flow.

### SECTION 3

After the second section ends, a third section may be selected and moved through the same general flow.

This three-section model is a project assumption for the MVP. It is not yet independently validated as a universal facility workflow.

## Conceptual manual workflow

1. Animals are grouped before movement.
2. A section is selected for movement.
3. Animals begin moving toward a constrained passage.
4. Animals pass through or near an alley leading toward the weighing area.
5. A human operator may perform a manual count.
6. Movement may include overlap, bunching, stopping, or reverse movement.
7. The section movement ends.
8. The observed count may be recorded or reconciled within the broader operational workflow.
9. The next section may begin.

The exact workflow sequence, pacing, and local operational details remain project assumptions unless independently validated.

## Why direct dense-group counting is not the initial approach

Counting pigs while stationary or densely grouped in a holding area is not the initial HogFlow approach because:

* individual bodies may overlap
* animals may partially occlude one another
* visible shapes may merge
* stationary group boundaries may be ambiguous
* unique individual identity is difficult to infer from a dense single view

This is a computer-vision design rationale.

It is not a claim that dense-group counting is impossible.

## Proposed observation point

The initial proposed observation point is a constrained passage because it may provide:

* narrower field of movement
* more directional motion
* temporal separation may improve
* easier definition of a virtual crossing line
* tracking trajectories may be easier to evaluate than dense group membership

Camera placement and actual alley geometry remain unvalidated assumptions.

## Current process limitations and unknowns

Current limitations and unknowns include:

* exact workflow may differ by facility
* number of manual counts is not independently validated
* count ownership is not independently validated
* current digital systems are unknown
* existing automation is unknown
* camera infrastructure is unknown
* acceptable error tolerance is unknown
