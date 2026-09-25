# Cross-module input consistency

CleanroomX v0.17 adds a standalone consistency check for engineering inputs duplicated between the multi-room verification model and the HVAC model.

## What is compared

Rooms are paired only when their names match exactly. For each shared room, the checker compares:

- verification `supply_airflow_m3_h`;
- HVAC `cleanroom_airflow_m3_h`.

The reported difference is:

    HVAC cleanroom airflow - verification supply airflow

The checker also lists rooms that occur in only one project file.

## Explicit tolerance

The default absolute airflow consistency tolerance is `0.0 m³/h`, so duplicated inputs must agree exactly unless the user supplies another tolerance:

    cleanroomx-consistency examples/facility_project.json examples/consistency_hvac_demo.json --airflow-tolerance-m3-h 5

That tolerance is a data-consistency tolerance supplied by the project. CleanroomX does not infer it from an ISO class, HVAC rule, or other standard.

## Room-scope policy

By default, a room that appears in only one input is reported but does not fail the comparison. To require identical room-name sets:

    cleanroomx-consistency examples/facility_project.json examples/consistency_hvac_demo.json --require-same-room-set

Statuses are:

- `pass`: all shared-room airflow values agree and the room sets are identical;
- `pass_with_scope_difference`: shared-room airflow values agree, but one project contains additional rooms and identical sets were not required;
- `fail`: at least one shared-room airflow value exceeds the configured tolerance, or identical room sets were required and differ;
- `not_comparable`: there are no exact room-name matches and identical room sets were not required.

## Desktop/project input contract

When this workflow is configured as a CleanroomX project analysis, its JSON payload accepts only `verification_project`, `hvac_project`, `room_airflow_abs_tolerance_m3_h`, and `require_same_room_set`. Unsupported or misspelled fields are rejected before defaults are applied. For example, `require_same_room_sets` is an error rather than silently behaving as `require_same_room_set=false`.

## JSON and file output

    cleanroomx-consistency examples/facility_project.json examples/consistency_hvac_demo.json --format json
    cleanroomx-consistency examples/facility_project.json examples/consistency_hvac_demo.json --output consistency-report.md

The CLI returns exit code 2 only for `fail`; other states return 0 so callers can distinguish inconsistency from limited comparison using the structured status.

## Boundary

This workflow detects contradictory duplicated inputs. It does not establish airflow adequacy, cleanroom classification, certification, commissioning acceptance, or a standards-derived tolerance. Those decisions remain governed by the applicable project requirements, licensed standards, regulations, and qualified engineering review.
