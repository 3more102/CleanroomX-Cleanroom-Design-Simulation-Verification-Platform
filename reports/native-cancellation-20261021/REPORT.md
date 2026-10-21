# Native CFD cancellation and Tk lifecycle recovery — 21 October 2026

The existing connected CFD desktop now cancels native Linux solver operations,
cleans up their managed process groups and refuses cancelled output as completed
CFD. A fatal Tk finalization defect found during the complete suite was also
reproduced at the ownership boundary and repaired. **Engineering release remains
HOLD.** These are execution/lifecycle improvements, not physical qualification.

## Implemented

- Added `src/cleanroomx/cfd_process.py`: direct argument execution in a dedicated
  POSIX session, file-backed output, finite positive timeouts, cooperative
  cancellation, TERM/KILL escalation and direct-child reaping. The runtime
  identity probe uses the same managed process path. No new dependencies.
- Extended `cfd_multizone.py` with an optional cancellation event. Cancelled or
  interrupted stages retain their actual log/hash/timing and a cancelled
  receipt, with no successful output hashes. A final cancellation check also
  covers requests received during output validation. Existing input, normal
  completion and provenance gates remain in force.
- Added the functional **Cancel native run** control to
  `cfd_multizone_gui.py`. The native worker publishes queue events, leaves Tk on
  the main thread and finishes process cleanup after parent destruction. WSL
  bridge/import operations do not expose unsupported native cancellation.
- Added `gui_lifecycle.py` and connected it to application, CFD, particle-source
  and native-viewer window creation. Destroyed widgets are retained until a
  main-thread collection; surviving caller-owned objects stay protected until
  their later release. Automatic GC is paused only for that short handoff and
  its prior policy is restored. Numerical algorithms and result values are
  unchanged. See [the lifecycle explanation](../../docs/NATIVE_CFD_CANCELLATION.md)
  and [CPython issue 39093](https://bugs.python.org/issue39093).
- Added real subprocess/group, Tk ownership, cancel-button and actual solver
  regressions in `test_cfd_process.py`, `test_gui_lifecycle.py`,
  `test_cfd_cancellation_gui.py` and `test_cfd_multizone_execution.py`.
  Display-backed Linux and Windows CI now include the applicable regressions.
- Added a repeatable actual-window capture script, two original screenshots,
  source hashes and the original cancelled case. Existing history, GUI modules,
  physics and archived successful cases are preserved.

## Executed verification

| Local execution | Passed | Failed | Skipped | Time |
|---|---:|---:|---:|---:|
| Complete suite, required actual Foundation v10, real Tk/VTK display | 2833 | 0 | 1 | 415.82 s |
| Focused native process/GUI/actual CFD suite before the lifecycle repair | 35 | 0 | 0 | 101.05 s |

The focused run overlaps the complete suite and is not an additional 35
independent tests. The sole complete-suite skip is the optional native
IfcOpenShell smoke. There were 48 existing Matplotlib font-property deprecation
warnings. The final complete process exited **0**; a skipped solver test is not
being counted as solver evidence.

Environment: Linux, Python 3.12.14, Tk 9.0.4, VTK 9.3.1, Foundation v10 build
`10-c4cf895ad8fa`, actual Xvfb TCP display and software GL. The retained runtime
requires its shared-library directory in this execution environment. The
existing wrapper selects and verifies the actual v10 environment. Its `mpicc`
discovery warning does not prevent these serial runs; MPI was not qualified.

Executed complete-suite command (with the environment-specific display and
shared-library setup applied):

```bash
CLEANROOMX_REQUIRE_OPENFOAM=1 bash scripts/with_openfoam10.sh \
  python -m pytest -q -ra \
  --basetemp=/tmp/cleanroomx-native-cancel-verified \
  --junitxml=native-verified.xml
```

Evidence: [machine-readable validation](validation.json),
[complete JUnit](evidence/native-complete.xml),
[complete console bytes, gzip](evidence/native-complete.log.gz),
[focused JUnit](evidence/native-focused.xml) and
[focused console bytes, gzip](evidence/native-focused.log.gz).

The actual OpenFOAM tests cover cancellation after entering `simpleFoam`,
cancellation at the final stage, Ctrl+C with solver-PID reaping, and destruction
of the actual parent Tk application during the solver loop. They assert a
cancelled receipt, no successful output hashes, absent solver PID and canonical
import refusal. Process tests separately exercise ordinary and TERM-resistant
descendants, literal arguments, nonzero exits, timeouts and pre-cancellation;
those Python children are process tests, not CFD substitutes. Ownership tests
observe Tk variable finalizer thread identity without invoking unsafe Tcl calls
from a worker, including windows still referenced by callers at a collection.

### Actual GUI exercise

[Two original desktop captures](../../docs/native-cfd-cancellation-20261021/README.md)
come from the current GUI driving a fresh real mesh/solver case. The script
waited for `simpleFoam`'s actual iteration loop, invoked the real cancel button,
verified the PID disappeared and confirmed partial-result import was rejected.
The capture manifest records **zero Tk callback errors**. Image, compressed
artifact and decoded original-log hashes were independently checked.

The installed `cleanroomx-gui --demo --smoke --autosave-interval-seconds 0`
entry point also passed on a real display with `/tmp` as its working directory
and exited 0: [original console output](evidence/installed-gui-smoke.log).

The [original cancelled case archive](evidence/actual-cancelled-native-case.tar.gz)
contains all 18 original files (inputs, generated mesh, logs and receipt),
preserved without rewriting numerical content. Its
[per-file hashes](evidence/actual-cancelled-native-case-files.json) were checked
against the archive entries. A fresh extraction was independently refused by
the canonical importer. It is intentionally **not an importable completed
solution**. The recovery report retains the separate earlier executed
100-iteration case.

### Rejected attempts and confirmed defects

1. The first complete run terminated with exit **139** at a Tk variable
   finalizer on a numerical worker. The
   [original traceback](evidence/rejected-pre-fix-tk-crash.log.gz) is retained.
   The main-thread lifetime boundary and real-widget regression address this
   observed failure; the final complete suite passed after the fix.
2. One separate capture attempt returned blockMesh exit **0** with a truncated
   log, no normal completion marker and no generated mesh. Its cause remains
   **unresolved**. The pipeline correctly refused it as `incomplete`, retained
   empty output hashes and did not proceed to the solver. The
   [original receipt](evidence/rejected-incomplete-mesh-receipt.json),
   [source manifest](evidence/rejected-incomplete-mesh-source.json) and
   [original log](evidence/rejected-incomplete-blockMesh.log.gz) are retained.
   No causal connection to the Tk crash is established. A fresh actual capture
   and the final complete suite passed without weakening completion checks.

## Remaining issues and engineering limits

- Native cancellation manages serial POSIX groups and descendants that remain
  in them. MPI, remote jobs and descendants creating separate sessions require
  separate controls. Cancelling during the preliminary identity probe stops
  before stage execution and does not create a successful execution receipt.
- The separate Windows-to-WSL bridge still needs a Linux-side cancellation
  protocol and actual workstation execution. Killing `wsl.exe` alone would not
  establish solver termination. No native Windows workstation is available
  locally. Previous-commit Windows CI evidence is listed separately below.
- Genuine execution is not convergence or physical validation. The archived
  design-flow case remains unconverged. Closed-door 5 Pa leakage/control,
  mesh independence, turbulence/particle-model adequacy, calibrated airborne
  concentration and cleanroom qualification remain open. No ISO compliance
  claim is made.
- These Linux/Tk screenshots retain their actual font-rendering limitations.
  The unrelated truncated mesh-log incident remains an environmental/runtime
  investigation item rather than an asserted fixed defect.

## GitHub and preserved work

Target branch: `feat/doors-5pa-ceiling-downflow-demo-20261020`.
Existing PR: [#1363](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1363).
Parent: `45bcc04c37007a7a2f38144b895b5701b7e802c7`.
Changes were reviewed and tested in the separate
`work/native-cfd-cancellation-20261021` worktree; the original checkout's
uncommitted changes were preserved. Publication uses the tested tree and an
expected-head, non-force branch update. The enclosing commit/PR records the
published hash; `git ls-remote` is used to confirm synchronization.

All three inspected previous-parent workflows completed successfully:
[CI](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39590402416),
[actual OpenFOAM](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39590402494),
[VTK/display](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39590402230).
That CI included real Windows Tk startup through PowerShell and CMD from an
unrelated directory. These are evidence for **45bcc04**, not a claim that
this new commit's workflows have completed or that Windows-to-WSL CFD works.

## Next engineering milestone

Prioritize independently reproducible convergence and mesh-sensitivity studies
for the actual connected airflow case, with explicit mass/flux tolerances,
boundary-condition review and retained genuine solver evidence. A successful
acceptance result must pass those numerical checks and the provenance importer;
execution alone cannot lift HOLD. In parallel with access to a Windows/WSL
workstation, implement and test Linux-supervised cancellation acknowledgements
through the bridge. Existing design and analytical-network workspaces remain
available while these simulation capabilities are qualified.
