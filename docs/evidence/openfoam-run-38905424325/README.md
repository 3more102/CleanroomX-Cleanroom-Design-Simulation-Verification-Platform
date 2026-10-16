# Replaying the run 125 grid audits

These three study JSON files and three unedited CleanroomX CLI result JSON
files were generated from the real OpenFOAM Foundation v10 artifact for run
38905424325. The artifact ID is `12047563804`, with SHA-256
`9224905fe3ec1efd76a46438596b0fd0966cb6dc0290323e26424a4f8491f464`.

Download that artifact from the [GitHub Actions run](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38905424325/artifacts/12047563804)
and verify its SHA-256 before extracting it. Run the commands below from the
repository root; they use the checked-out source through `PYTHONPATH=src`.
Copy each study JSON into the artifact's
`cleanroomx-cfd-grid-family/` directory; the CLI confines VTK and log inputs to
the directory containing the study file.

```sh
echo '9224905fe3ec1efd76a46438596b0fd0966cb6dc0290323e26424a4f8491f464  openfoam-run-38905424325.zip' | sha256sum -c -
unzip openfoam-run-38905424325.zip -d /tmp/openfoam-run-38905424325
family=/tmp/openfoam-run-38905424325/cleanroomx-cfd-grid-family
for configuration in 1 2 3; do
  cp "docs/evidence/openfoam-run-38905424325/configuration-${configuration}-study.json" \
    "$family/configuration-${configuration}-study.json"
  PYTHONPATH=src python -m cleanroomx.cfd_pipeline_cli grid-audit \
    "$family/configuration-${configuration}-study.json" \
    --output "$family/configuration-${configuration}-result.json" || test "$?" -eq 3
done
```

Exit code 3 is expected here: each audit is indeterminate because the solver
residual screens fail and the velocity QoI has no positive three-grid observed
order. Compare the generated result JSON with the preserved result file. The
example study criteria are recorded for reproducibility only; they are not
project-approved acceptance limits.

## SHA-256 of preserved audit files

| File | SHA-256 |
| --- | --- |
| `configuration-1-study.json` | `11a4ee1bf0b343ca840f72dfd25c9e740d1b52a7cbb5a26ea236e8bdeee36dfe` |
| `configuration-1-result.json` | `1af53d638351cf7988b74fb5155a76d0522e48b21c5f5eb24bdb0750290b5aae` |
| `configuration-2-study.json` | `452b614db2898970c2677d80311b33860fc296d0873e7301b5d06d0b08fb07f2` |
| `configuration-2-result.json` | `5b4ff074840c0f636489d0c59ba3b74c63096525ab49c067c04e294629511b04` |
| `configuration-3-study.json` | `2c437c436ce6837c67c62b44d9de80f1df49589245108d80f0745e5ac4710773` |
| `configuration-3-result.json` | `59268a2f78a6a01706d57a87976bccb7938dbece604bedfe5f082238f774d630` |
