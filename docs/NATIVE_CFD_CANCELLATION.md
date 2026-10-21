# Cancelling connected native CFD runs

The multiroom CFD window offers **Cancel native run** during its local
**Run OpenFOAM 10** operation. The request leaves the window responsive while
the worker stops and reaps the current process group. Once solver stages have
started, a cancelled run records
`status: cancelled`, retains its real stage log and elapsed time, and publishes
no successful field hashes. The existing importer rejects that receipt, even
if partial mesh/field files remain. Generate a fresh case before rerunning.
Cancellation during the preliminary runtime probe stops before solver stages;
it does not create a successful execution receipt.

This control supports native POSIX/Linux processes, including commands run
inside an already opened Linux/WSL session. It does not cancel the separate
Windows **Run case in WSL** bridge. That bridge needs an independently tested
Linux-side cancellation protocol; terminating `wsl.exe` alone cannot establish
that the Linux solver stopped. The native cancellation button stays disabled
for those bridge operations and for field imports.

## Process lifetime

- Every native command, including the runtime identity probe, starts in its
  own POSIX session, with arguments passed directly and output streamed to a
  file.
- Cancellation and per-stage timeouts terminate that group, escalate to kill
  remaining group members, and wait for the direct child. This handles ordinary
  children and TERM-resistant children that remain in the managed group.
- Closing the parent Tk application requests cancellation. The native worker
  is not a daemon and finishes cleanup without accessing Tk from its thread.
- An interrupt during a solver stage is handled by the same cleanup path. The
  command-line runner records a cancelled receipt and exits unsuccessfully.
- Cancellation is a request. A run whose receipt was already published may
  have completed before that request is observed. The completion event and
  receipt determine the final state shown by the window.

Group management covers the serial native pipeline and descendants that stay
in its group. It does not manage MPI jobs, remote jobs, or descendants that
deliberately start a new session. Those require separate lifecycle controls.

## GUI object lifetime

A complete-suite run exposed a native Tk crash while an unrelated numerical
worker collected a destroyed window's Tk variable cycle. The shared GUI
lifecycle helper now retains destroyed widgets until a full collection on
the main GUI thread. It re-retains objects still owned by callers, so a later
release cannot move their Tcl finalizers onto a worker. Main-thread collection
runs at worker entry and periodically while a GUI remains open. Automatic GC
is paused only during the short collection handoff and its prior policy is
restored. Numerical calculations and their provenance checks are unchanged.

See [CPython issue 39093](https://bugs.python.org/issue39093) for the underlying
Tk finalizer ownership issue. Real-widget regressions observe finalizer thread
identity and exercise both unreachable and still-referenced destroyed windows.

## Reproduction

After installing the project tests and optional CFD dependencies:

```bash
python -m pytest -q tests/test_cfd_process.py
xvfb-run -a python -m pytest -q tests/test_cfd_cancellation_gui.py
bash scripts/with_openfoam10.sh xvfb-run -a python -m pytest -q \
  tests/test_cfd_multizone_execution.py -ra
```

The first checks run real Python child processes, including TERM-resistant
descendants. They are process-management tests, not substitute CFD output.
The last suite requires actual Foundation v10 and exercises genuine solver
cancellation, final-stage cancellation, Ctrl+C, and rejection of partial fields.

Execution lifecycle tests do not establish CFD convergence, mesh independence,
closed-door 5 Pa performance or physical particle accuracy. Engineering release
remains **HOLD**.

[Two actual desktop captures and source-linked logs](native-cfd-cancellation-20261021/README.md)
show a separate real GUI-to-solver cancellation exercise.
