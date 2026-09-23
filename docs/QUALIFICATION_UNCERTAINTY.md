# Qualification uncertainty

CleanroomX v0.6 extends the conservative uncertainty/provenance foundation to qualification-style threshold checks for measured quantities and room-to-room pressure cascades.

## Scope

The workflow supports:

- minimum requirements, such as a project-configured differential-pressure minimum;
- maximum requirements, such as a project-configured particle-concentration maximum;
- room-to-room pressure cascades with uncertainty on both measured room pressures;
- requirement references and engineering-input provenance;
- pass, fail, and indeterminate results.

The workflow remains requirement-driven. CleanroomX does not supply ISO class limits, universal pressure limits, or other acceptance thresholds.

## Decision rule

For a measured value x with user-supplied absolute uncertainty bound u:

    x_low = x - u
    x_high = x + u

For a minimum requirement L:

- pass when x_low >= L;
- fail when x_high < L;
- indeterminate when the interval overlaps L.

For a maximum requirement U:

- pass when x_high <= U;
- fail when x_low > U;
- indeterminate when the interval overlaps U.

This is deliberately conservative interval screening. It is not a statistical uncertainty budget and does not imply a coverage probability.

## Pressure-cascade propagation

For a higher-pressure room H and lower-pressure room L:

    delta_nominal = H_nominal - L_nominal
    delta_low = H_low - L_high
    delta_high = H_high - L_low

A configured minimum cascade is passed only when the complete conservative differential-pressure interval meets the minimum.

## Overall status

- fail if any configured check fails;
- otherwise indeterminate if any check is indeterminate;
- otherwise pass.

Missing provenance is reported separately and does not silently change numerical acceptance.

## CLI

    cleanroomx-qualification examples/qualification_uncertainty_demo.json

JSON output:

    cleanroomx-qualification examples/qualification_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-qualification examples/qualification_uncertainty_demo.json --output qualification-report.md

Exit codes:

- 0: pass;
- 2: fail;
- 3: indeterminate.

## Metrology boundary

JCGM 106:2012 addresses the role of measurement uncertainty in conformity assessment, while JCGM 100:2008 and NIST Technical Note 1297 provide broader uncertainty guidance. CleanroomX does not claim that this simple interval rule implements those documents in full. Project, regulatory, accreditation, and validation decision rules take precedence.

Official references:

- JCGM 100:2008: https://www.bipm.org/en/doi/10.59161/JCGM100-2008E
- JCGM 106:2012: https://www.bipm.org/en/doi/10.59161/JCGM106-2012
- NIST Technical Note 1297: https://www.nist.gov/pml/nist-technical-note-1297
