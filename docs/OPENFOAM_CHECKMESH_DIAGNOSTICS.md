# OpenFOAM checkMesh diagnostic receipt

The Foundation v10 runner records a structured summary of each `checkMesh`
log alongside the raw log path and SHA-256 digest. The receipt schema is
`cleanroomx.openfoam-checkmesh-diagnostics.v1`.

## Interpretation

- `parse_status=complete` means the expected Foundation v10 records appeared
  exactly once and their numeric values were finite. `incomplete` and
  `ambiguous` identify missing, malformed, non-finite, or repeated records.
- `mesh_result` preserves the final tool-level result as `mesh_ok`,
  `checks_failed`, or `unknown`. If `Mesh OK` conflicts with any reported
  failed check, the result becomes `unknown` and the report is ambiguous. It
  is not a CleanroomX engineering verdict.
- `reported_checks` contains the `OK` or `Failed` labels printed by OpenFOAM;
  `patch_topology` retains each patch's face count, point count, and topology
  label. Failed labels are listed in `reported_check_failures` and stop the
  runner. These observations are not converted into project acceptance.
- `counts` and `geometry` preserve cell/face counts, cell types, dimensions,
  areas, volumes, and the geometric metrics printed by `checkMesh`.
- `patch_topology` preserves the tool-reported face/point counts and topology
  label for each named boundary patch. Failed labels remain in
  `reported_check_failures`.
- `source_log_sha256` binds the summary to the raw log. The runner records an
  incomplete report and stops before `simpleFoam` if it cannot parse the
  expected Foundation v10 records or if the tool reports failed checks.
- `interpretation=diagnostic_only` and
  `project_acceptance=not_assessed_no_project_criteria` are fixed report
  fields. The parser does not set project mesh thresholds, infer suitability,
  or change CFD convergence, GCI, or scientific-validation status.

The checked-in parser regression fixture is the archived Foundation v10
`configuration_1/coarse/checkMesh.log` from run 66. Its SHA-256 is
`4233a532e90d079c4ee3df31ecaa12fdddf41da67d630ad87aa6f04bfc97a478`, matching
the run 66 artifact report. This is a parser fixture from a regular synthetic
mesh, not a real cleanroom mesh or physical validation dataset.

The parser verifies that the supplied SHA-256 matches the exact UTF-8 log text
and preserves CRLF line endings when read from raw bytes. The runner hashes and
decodes the same byte snapshot so text newline normalization cannot change the
evidence digest.

See [the OpenFOAM pipeline guide](CFD_OPENFOAM_PIPELINE.md) for execution
instructions and [the run 66 checkMesh report](OPENFOAM_V10_RUN_38776224839_CHECKMESH_QUALITY.md)
for the archived mesh diagnostics and their limits.
