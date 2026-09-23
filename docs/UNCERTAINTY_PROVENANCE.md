# Uncertainty and provenance

CleanroomX v0.5 adds optional engineering uncertainty and traceability metadata to the room and pressure-cascade verification workflow.

## Purpose

A measured value close to an acceptance threshold should not automatically become PASS or FAIL when the configured measurement uncertainty overlaps that threshold. CleanroomX therefore keeps nominal values visible and, when an absolute plus/minus uncertainty is supplied, evaluates the full interval.

The software does not invent uncertainty values. Enter them only from an applicable calibration certificate, test method, instrument specification, uncertainty budget, qualified engineering method, or other controlled source.

## Status logic

For a minimum requirement such as ACH or positive differential pressure:

- PASS when the complete uncertainty interval is at or above the configured minimum.
- FAIL when the complete uncertainty interval is below the configured minimum.
- INDETERMINATE when the interval overlaps the minimum.

For a maximum requirement such as particle concentration:

- PASS when the complete uncertainty interval is at or below the configured maximum.
- FAIL when the complete uncertainty interval is above the configured maximum.
- INDETERMINATE when the interval overlaps the maximum.

An indeterminate result is treated as not passing in the overall verification result. This prevents an ambiguous result from being reported as compliant.

## ACH uncertainty

The current ACH uncertainty is propagated only from the optional supply-airflow uncertainty:

    ACH = supply airflow / room volume
    ACH uncertainty = supply-airflow uncertainty / room volume

Geometry uncertainty is not yet propagated. If geometry uncertainty is material, perform an external uncertainty calculation or conservatively include its effect in the airflow/ACH input until a future model supports it explicitly.

## Pressure-cascade uncertainty

For a room-to-room differential, CleanroomX uses a conservative worst-case interval. If the high-pressure room has uncertainty u_high and the low-pressure room has uncertainty u_low, the differential-pressure uncertainty is:

    u_delta = u_high + u_low

This is interval arithmetic, not root-sum-square statistical combination. It avoids assuming independence or a probability distribution that the project has not supplied.

## Provenance fields

Optional provenance records can contain:

- source
- reference
- instrument_id
- calibration_reference
- observed_at

Requirement fields can also carry a requirement_reference, such as a URS clause, protocol step, drawing note, controlled specification, or licensed-standard clause reference.

## Example

    {
      "name": "Example cleanroom",
      "length_m": 6.0,
      "width_m": 4.0,
      "height_m": 3.0,
      "supply_airflow_m3_h": 1800.0,
      "supply_airflow_uncertainty_m3_h": 60.0,
      "min_ach": 20.0,
      "ach_requirement_reference": "URS-HVAC-007",
      "airflow_provenance": {
        "source": "TAB report",
        "reference": "TAB-2026-014",
        "instrument_id": "AFM-17",
        "calibration_reference": "CAL-2026-88",
        "observed_at": "2026-09-20T10:30:00+03:00"
      }
    }

## Engineering boundary

This feature is a transparent screening and reporting mechanism. It is not a substitute for a formal measurement uncertainty budget, accreditation requirements, statistical decision rules, guard bands, or a project-specific conformity assessment procedure.
