# OpenFOAM Foundation v10 upstream tutorial integration smoke

The `openfoam-v10-upstream-tutorial` GitHub Actions job checks a reproducible
solver-to-results path using the OpenFOAM Foundation source tree pinned to
commit `89f925dc708d068f84f51e8317e3bebcda64f5cb` and its
`tutorials/incompressible/simpleFoam/pitzDaily` case.

The job copies the pinned case into an isolated temporary directory, resolves
pinned `system/blockMeshDict` file and verifies its hash, then runs
`blockMesh`, `checkMesh`, and `simpleFoam`. During the actual
`simpleFoam` process, CleanroomX polls native result times and synchronizes
stable velocity (`U`) and kinematic pressure (`p`) snapshots through
`OpenFOAMResultSynchronizer`. The job retains command logs, input/configuration
hashes, the sync manifest, and imported VTK assets as an Actions artifact.

A passing receipt means only that the pinned upstream tutorial executed and
CleanroomX imported hash-bound nonzero-time results. The tutorial is an
integration fixture, not a cleanroom model. The receipt always keeps
`scientific_validation=BLOCKED`; it does not establish numerical convergence,
mesh independence, cleanroom performance, or agreement with measurements.

See the run's `openfoam-v10-pitzdaily-evidence` artifact for the exact
Foundation build, stage return codes, logs, synchronization manifest, and
result assets.
