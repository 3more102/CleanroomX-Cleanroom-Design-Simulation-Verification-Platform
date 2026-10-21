# CleanroomX — startup and runtime recovery, 21 October 2026

## Implemented

This increment repairs reproducible startup/diagnostic defects and runtime
selection in the existing desktop and connected-CFD workflow. It does not
complete the entire product roadmap or qualify the physical model.

The actual checkout is `/workspace/scratch/6ca3602dcd10/CleanroomX`, with an
isolated `.venv`, based on `edfe7dacdd42fdc985bda815d76b042347ac42b6` from
`feat/doors-5pa-ceiling-downflow-demo-20261020`. PR #1363 was open and mergeable
when inspected. Three older local copies were inspected. The two copies with
uncommitted engineering-workbench work were left untouched. This Linux host
cannot inspect `C:\Users\omar` or the user's D: drive or reproduce a missing
historical Windows traceback.

| Change | Important files |
|---|---|
| Full startup and initialization tracebacks, interpreter/CWD context, stderr fallback, partial-window cleanup | `gui.py`, `runtime_diagnostics.py` |
| Real Tk smoke fails on idle/callback exceptions; reject NaN/Infinity autosave values before creating Tk | `gui.py`, `test_gui_startup.py` |
| Missing optional demo produces an actionable error while keeping an empty interactive workspace available | `gui.py`, `test_gui_startup.py` |
| Failed no-argument CMD launch retains the console and original exit status | `start-cleanroomx.cmd` |
| Bounded, read-only installation discovery; explicit override; actual version/utilities checked before execution | `openfoam_runtime.py`, `with_openfoam10.sh`, `pyproject.toml` |
| Configurable WSL Linux bashrc path, including `/mnt/d/`; literal argument isolation | `cfd_wsl_bridge.py`, `run-cleanroomx-cfd-wsl.ps1` |
| Select an actual source checkout when installed from a wheel; display real WSL diagnostics through the GUI queue | `cfd_multizone_gui.py` |
| Explain missing original `0/U` and other required inputs; retain strict provenance rejection | `cfd_multizone.py` |
| Windows real-Tk startup from another directory; display-backed regression jobs | `.github/workflows/ci.yml`, `cfd-vtk.yml` |

No new production dependency was added. Core geometry, analysis registries,
OpenFOAM templates, VTK mesh/field interfaces and the existing particle force
model were preserved. The new inventory never sources discovered scripts or
claims their version is verified. The existing execution wrapper then selects
and interrogates the actual Foundation v10 executable. Other detected releases
are not treated as compatible with the current dictionaries.

## Verification

Measured environment: Python **3.12.14**, Tcl/Tk **9.0**, VTK **9.3.1**,
Matplotlib **3.10.8**, an actual Xvfb display, and **OpenFOAM Foundation v10,
build 10-c4cf895ad8fa**. A previously retained official runtime package was
reused, with its installation path restored locally; no runtime installation
on the Windows workstation is implied. Serial runtime initialization reports
missing `mpicc`; MPI execution was not tested.

| Executed check | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Initial focused existing GUI/diagnostics/WSL contracts | 74 | 0 | 0 |
| Failure reproduction before fixes | 1 | 7 | 0 |
| Focused recovery tests after fixes | 115 | 0 | 0 |
| Fresh independent actual OpenFOAM/Tk/VTK regression | 19 | 0 | 0 |
| Complete final suite, real display and sourced runtime | **2812** | **0** | **1** |

The focused checks overlap; their counts must not be added. The complete run
took **303.76 s** (pytest summary; JUnit records 303.724 s). The sole skip is
optional native IfcOpenShell, not an OpenFOAM test. There were 48 existing
Matplotlib font-property deprecation warnings.

The seven reproduced failures include an actual idle Tk exception that the
previous smoke command swallowed while printing PASS. The corrected command
records that traceback and returns failure. Reproduced initialization and
display failures retain the original exception when the log folder is unusable.

Final complete-suite invocation, using the local display wrapper:

```bash
CLEANROOMX_REQUIRE_OPENFOAM=1 \
LD_LIBRARY_PATH=/workspace/scratch/d2477ad7a66e/runtime-packages/root/usr/lib/x86_64-linux-gnu \
bash /workspace/scratch/6ca3602dcd10/with-display.sh \
  bash scripts/with_openfoam10.sh .venv/bin/python -m pytest -q -ra \
  --basetemp=/tmp/cleanroomx-recovery-final-check \
  --junitxml=/workspace/scratch/6ca3602dcd10/validation/full-final.xml
```

`cleanroomx-gui --demo --smoke --autosave-interval-seconds 0` also passed from
`/tmp`, invoked through its absolute installed console-script path. The new
`cleanroomx-openfoam-runtime --json` worked from `/tmp`. Workflow YAML parsing
and `git diff --check` passed.

### Actual numerical evidence

The final suite generated a fresh **13,210-cell**, single-region mesh with
**Mesh OK**, ran `blockMesh`, `checkMesh`, `simpleFoam` and `postProcess`, and
verified their actual logs, return codes and source/output hashes. Saved
iterations were imported and exercised by the existing field, native original
mesh, numerical diagnostic and scheduled-particle integration tests.

The archived 100-iteration design-flow case is **NOT CONVERGED**. Its actual
outputs are execution/integration evidence; they do not establish accuracy,
mesh independence, a closed-door 5 Pa cascade, cleanroom classification or
physical particle validation.

- [Exact original executed case](executed-case.tar.gz)
- [Machine-readable environment, counts, stage/log hashes and source identity](validation.json)
- [Complete suite output](full-suite.log) and [JUnit results](full-suite.xml)
- [Before-fix failure reproduction, losslessly compressed](startup-before-fix.log.gz)
- [Fresh 19-test actual CFD/display regression](fresh-cfd-regression.log)
- [Three actual GUI captures and source-linked manifest](../../docs/startup-runtime-recovery-20261021/README.md)

The images are unedited running Tk window pixels. The new runtime controls
are disabled on this Linux host. The screenshots also retain the minimal
Linux/Tk font rendering limitations; they are not a native Windows/high-DPI
qualification. No CFD values are drawn into the captures outside the real GUI.

### Initial complete-suite attempt and integrity rejection

An earlier complete-suite attempt encountered seven failures after
`postProcess.log` no longer matched its recorded stage SHA-256, and was
interrupted. The cause of that alteration was not established. Its
[observed log and original receipt](rejected-log-evidence/) are retained;
this small evidence collection is not an importable simulation case.
An independent fresh 19-test solver/display run and the final complete suite
then passed. Hash checking was never relaxed, and the rejected case was not
used for the final captures or archived numerical evidence.

## Remaining issues and engineering limitations

- The actual Windows workstation, its D: drive and native WSL solver handoff
  remain untested here. Windows path/argument contracts are unit tests; the
  added native Windows CI smoke is a separate check whose per-commit outcome
  must be inspected. It does not install or run OpenFOAM inside WSL.
- The cause of the earlier modified postProcess log is unresolved, as recorded
  above. Strict import integrity remains required for every case.
- Current templates are Foundation v10 specific; other detected versions need
  explicit compatibility implementation and genuine execution tests.
- The existing design-flow case is unconverged; relaxation alone does not
  establish physical accuracy. Mesh sensitivity and appropriate model/boundary
  validation remain necessary.
- Closed-door network sensitivity is an analytical hypothesis, not closed-door
  CFD or commissioning evidence. The one-way frozen steady particle model still
  omits physical wall-deposition/outlet qualification and calibrated airborne
  concentration. ISO cleanroom compliance is not claimed.
- This increment does not add solver cancellation or reconcile divergent
  workbench branches and the separate AI assistant PR. Those remain explicit
  product-development tasks, rather than completed features of this change.

Engineering release remains **HOLD**.

## GitHub

- Branch: `feat/doors-5pa-ceiling-downflow-demo-20261020`.
- [Existing PR #1363](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1363).
- Implementation and evidence are included together in the hosting commit;
  its exact SHA and independently verified remote synchronization are reported
  with the delivered milestone. No published history is rewritten.
- All original screenshot galleries and prior source history remain present.

## Next engineering milestone

1. Run the actual Windows launchers and WSL probe/mesh/solver/import path on the
   workstation, including a source checkout and runtime path with spaces on D:.
   Acceptance: genuine four-stage receipt, logs and verified field import, plus
   a responsive design GUI when the selected runtime is unavailable.
2. Add managed solver cancellation/process cleanup, including Linux child-process
   termination and an independently tested WSL cancellation mechanism. Acceptance:
   no orphaned solver, no successful receipt after cancellation, and no importer
   acceptance of partial output.
3. Investigate design-flow convergence and model/boundary validity using independent
   cases and mesh studies. Acceptance: retained logs, residual/flux evidence,
   documented tolerances and model limits; no inferred 5 Pa closed-door proof.
4. Reconcile preserved workbench changes and the separate read-only AI assistant
   through tested stable interfaces. Acceptance: canonical project persistence,
   interactive real-data views and complete GUI regressions before integration.
