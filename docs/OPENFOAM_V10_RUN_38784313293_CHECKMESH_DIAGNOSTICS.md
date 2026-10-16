# OpenFOAM Foundation v10 run 86: checkMesh diagnostic replay

## Provenance

- Workflow: [Foundation v10 grid execution run 86](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38784313293), code commit e52507af869d2e88c675d3b9b78c4f57f8090fa4.
- Solver: OpenFOAM Foundation v10, build 10-c4cf895ad8fa.
- Artifact: [11997282424](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38784313293/artifacts/11997282424), 11,914,597 bytes, SHA-256 3186b0e870c9842fc74401ae65fa1cfc6fe33823d942b2df32d5beba61ba9667. The downloaded archive matched the digest returned by GitHub's artifact metadata, and the ZIP integrity check found no corrupt entry.

## Independent replay

The artifact contains nine cases, 72 manifest-bound generated input files, 36 command logs, and 45 VTK files. Independent verification reproduced all 72 input hashes and all 36 log hashes; each of the 36 recorded command stages returned zero.

For each case, the archived checkMesh.log was parsed again with the repository's Foundation v10 parser. Each replay matched its complete receipt object, including the source-log SHA-256. All nine reports were complete, reported Mesh OK, and contained no reported failed checks. The corresponding polyMesh volume audit receipts were bound to the same checkMesh log hashes.

## Reported synthetic mesh diagnostics

All three configurations use the same rectangular 3 m × 2 m × 2 m mesh at each resolution. Each report records a total cell volume of 12.0 m³.

| Grid | Cells | Faces | Points | Cell-volume range (m³) | Max skewness | Max aspect ratio | Max non-orthogonality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Coarse | 216 | 756 | 343 | 0.05555555544–0.05555555578 | 3.996802881e-15 | 1.500000002 | 0° |
| Medium | 1,728 | 5,616 | 2,197 | 0.006944444389–0.006944444472 | 7.997075208e-15 | 1.500000006 | 0° |
| Fine | 13,824 | 43,200 | 15,625 | 0.0008680555486–0.0008680555694 | 2.124309955e-14 | 1.500000006 | 0° |

The same cell counts, bounds, volumes, and quality diagnostics were reported for configurations 1–3. These are the tool's diagnostics for synthetic regular meshes. No project mesh-quality limits were defined or applied, so Mesh OK does not constitute project mesh acceptance.

## Status

This is reproducibility evidence for generated synthetic inputs. It does not demonstrate residual convergence, grid independence, suitability of physical cleanroom geometry, or correlation with measured cleanroom data. Keep mesh and integration capabilities partial, GCI eligibility unchanged, scientific validation BLOCKED, and issue #1296 open until the required physical evidence is available.
