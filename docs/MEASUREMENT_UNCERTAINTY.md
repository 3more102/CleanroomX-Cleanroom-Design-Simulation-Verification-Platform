# Measurement uncertainty and provenance

CleanroomX v0.5 adds a generic measurement record for auditable uncertainty budgets and traceability.

## Model

Each measurement contains:

- a measurand, measured value, and unit;
- one or more standard-uncertainty components;
- an optional sensitivity coefficient for each component;
- optional Type A / Type B labels and source references;
- a configurable coverage factor;
- optional upper, lower, or range requirements;
- instrument, calibration, procedure, operator, location, timestamp, and source-document provenance.

For independent components, CleanroomX calculates the combined standard uncertainty as the root-sum-square of each sensitivity-weighted standard uncertainty:

    u_c = sqrt(sum((c_i * u_i)^2))

Expanded uncertainty is:

    U = k * u_c

and the reported interval is:

    measured value ± U

CleanroomX does not infer a coverage probability solely from the selected coverage factor.

## Screening decision rule

The built-in interval rule is intentionally transparent:

- pass: the entire expanded-uncertainty interval is within the configured requirement;
- fail: the entire interval is outside the permitted side or range;
- indeterminate: the interval overlaps a requirement limit;
- not_checked: no requirement was configured.

This is a conservative screening rule, not a universal conformity-assessment rule. A client, regulator, laboratory quality system, or qualification protocol may require a different decision rule or guard band.

## Correlation boundary

The v0.5 RSS calculation assumes the listed uncertainty components are independent. Correlated inputs require covariance terms and are not yet modeled. Do not represent known correlated components as independent merely to use this workflow.

## CLI

    cleanroomx-measurement examples/measurement_uncertainty_demo.json

JSON output:

    cleanroomx-measurement examples/measurement_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-measurement examples/measurement_uncertainty_demo.json --output measurement-report.md

Exit codes:

- 0: pass or not_checked;
- 2: fail;
- 3: indeterminate.

## References

CleanroomX follows the general measurement-uncertainty vocabulary and formulas described by the Joint Committee for Guides in Metrology (JCGM) and NIST, while keeping project acceptance criteria explicit.

- JCGM 100:2008, Guide to the Expression of Uncertainty in Measurement:
  https://www.bipm.org/en/committees/jc/jcgm/publications
- JCGM 106:2012, The role of measurement uncertainty in conformity assessment:
  https://www.bipm.org/en/doi/10.59161/jcgm106-2012
- NIST Technical Note 1297:
  https://www.nist.gov/pml/nist-technical-note-1297
