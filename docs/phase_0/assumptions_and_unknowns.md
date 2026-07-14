# HogFlow Assumptions and Unknowns

| ID | Assumption or unknown | Type | Why it matters | Validation method | Status |
| --- | --- | --- | --- | --- | --- |
| A-001 | A constrained passage exists at a useful counting point. | Workflow assumption | The entire directional line-crossing concept depends on a usable observation point. | facility workflow interview; authorized observation; camera-site assessment | Unvalidated |
| A-002 | Pig movement is sufficiently directional for virtual-line evaluation. | Technical assumption | Directional crossing logic is only meaningful if movement direction is interpretable. | representative video experiment; authorized observation | Unvalidated |
| A-003 | Camera placement can provide a usable field of view. | Camera assumption | Poor placement could make detection, tracking, or crossing logic unusable. | camera-site assessment; representative video experiment | Unvalidated |
| A-004 | Lighting is sufficient or can be handled technically. | Technical assumption | Poor lighting may degrade detection and tracking reliability. | representative video experiment; camera-site assessment | Unvalidated |
| A-005 | Occlusion does not make the count hypothesis fundamentally infeasible. | Technical assumption | Severe occlusion could break unique-crossing estimation. | representative video experiment; ground-truth comparison | Unvalidated |
| A-006 | Multi-object tracking can preserve identities long enough to evaluate crossings. | Technical assumption | The counting unit depends on stable tracker continuity. | representative video experiment; ground-truth comparison | Unvalidated |
| A-007 | Reverse movement occurs and requires explicit handling. | Workflow assumption | Reverse movement affects duplicate prevention and event logic. | authorized observation; representative video experiment | Unvalidated |
| A-008 | Session boundaries can initially be defined manually. | Workflow assumption | The MVP session model depends on operator-defined start and end boundaries. | facility workflow interview; authorized observation | Unvalidated |
| A-009 | Three sequential sections are an appropriate MVP workflow model. | Workflow assumption | The session structure and UI assumptions depend on this model. | facility workflow interview; authorized observation | Unvalidated |
| A-010 | Human-verified ground truth can be produced. | Evaluation assumption | Count accuracy cannot be evaluated without trustworthy ground truth. | ground-truth procedure design; authorized observation; pilot measurement | Unvalidated |
| A-011 | Representative legal or public pig video can be acquired for early experimentation. | Data unknown | Early experimentation requires lawful representative data. | data sourcing review; public dataset search; authorization review | Unvalidated |
| A-012 | Existing automation at candidate facilities is unknown. | Operational unknown | Existing systems may reduce need, alter workflow, or change integration scope. | facility workflow interview; market research | Unknown |
| A-013 | Existing camera infrastructure is unknown. | Camera assumption | Existing hardware could simplify or complicate later implementation. | facility workflow interview; camera-site assessment | Unknown |
| A-014 | Current manual counting frequency is not independently validated. | Operational unknown | Business and workflow relevance depend on how often counting occurs. | facility workflow interview; authorized observation | Unknown |
| A-015 | Current discrepancy frequency is not independently validated. | Operational unknown | Problem severity cannot be assumed without evidence. | facility workflow interview; authorized observation; pilot measurement | Unknown |
| A-016 | Acceptable count-error tolerance is unknown. | Evaluation assumption | Success criteria require a defined acceptable error threshold. | stakeholder interview; pilot measurement | Unknown |
| A-017 | Operational value has not been quantified. | Market unknown | Technical success alone does not prove useful deployment value. | market research; workflow interview; pilot measurement | Unknown |
| A-018 | The reference workflow may not generalize to other facilities. | Market unknown | A narrow plant-specific workflow would limit repeatability. | market research; facility workflow interview; cross-facility comparison | Unknown |
| A-019 | Tracker IDs may fragment or switch. | Technical assumption | ID instability can cause undercounting, overcounting, or review events. | representative video experiment; ground-truth comparison | Unvalidated |
| A-020 | Weight consistency may or may not provide a useful secondary review signal. | Evaluation assumption | Secondary review logic should not be assumed useful without evidence. | representative data analysis; pilot measurement | Unknown |

## Critical unknowns before a pilot

The most important unknowns that should be answered before Phase 16 can recommend an authorized pilot include:

* actual count workflow
* actual camera geometry
* representative video conditions
* human ground-truth procedure
* acceptable count error
* privacy requirements
* biosecurity requirements
* operational safety constraints
* IT or cybersecurity requirements
* manual fallback procedure
