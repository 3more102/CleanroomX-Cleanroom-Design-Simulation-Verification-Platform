# WORKSTREAM WS-14-PRESSURE-NETWORK-HARDENING

- **Worker ID:** WS-14-PRESSURE-NETWORK-HARDENING
- **Branch:** `dev/WS-14-PRESSURE-NETWORK-HARDENING`
- **Starting SHA:** `2cccdbacff36e609cf9d39996cd36886bd574f35`
- **Implementation/test SHA before this report:** `3ae683b9ed7d42ee0f5c747c3a7a577352d45ee0`
- **Assigned scope:** Harden the room pressure/leakage network against non-finite derived numerical states without changing normal-range equations, project schema, or solver semantics.

## Files intentionally modified

- `src/cleanroomx/pressure_network.py`
- `tests/test_pressure_network.py`
- `docs/PRESSURE_NETWORK.md`
- `docs/parallel/WORKSTREAM_WS-14-PRESSURE-NETWORK-HARDENING.md`

## Features completed

- Reject node airflow combinations whose derived mechanical injection overflows despite finite component inputs.
- Reject non-finite effective pressure differences, pressure-flow values, local sensitivities, residuals, Jacobian/elimination states, target margins, totals, and report-unit conversions.
- Use finite-safe summation for fixed-pressure averaging and mechanical airflow totals.
- Allow damped Newton line search to discard a non-finite trial state and retry with a smaller step instead of accepting or propagating it.
- Preserve existing power-law/orifice equations, pressure targets, output keys, project schema, and normal-range behavior.
- Do not clip, saturate, or fabricate a result after numerical overflow.

## Tests added

Seven regression cases cover:

1. overflow in combined mechanical injection;
2. overflow in effective pressure difference;
3. overflow in power-law flow;
4. overflow in derived orifice coefficient;
5. overflow during report-unit conversion to m3/h;
6. overflow in minimum target margin;
7. overflow in maximum target margin.

## Tests run / baseline

The starting `main` tree is file-identical to PR-head commit
`fc3e3155e6c78bc3e44fe9ca8bd532a9164a8fa1` (the merge commit adds no file
changes). GitHub Actions run `36194881564` completed successfully on that tree:

- Python 3.11: 1043 passed;
- Python 3.12: 1043 passed;
- Python 3.13: 1043 passed;
- Windows launcher smoke: success.

Post-change validation is performed by PR #511 CI after this report commit; the PR
run is the authoritative final test evidence.

## Known limitations

- This worker environment cannot access the user's local `C:\CleanroomX`
  filesystem, so local uncommitted/untracked state cannot be inspected or modified.
- The work therefore operates only on the isolated GitHub branch above.
- This hardening detects floating-point non-finiteness; it does not impose new
  engineering realism limits on otherwise finite user inputs.

## Shared interfaces changed

None. Public model classes, solver call signature, result keys, project schema,
serialization format, and CLI arguments are unchanged.

## Migration / schema changes

None.

## Recommended integration order

Merge after any branch that intentionally changes `src/cleanroomx/pressure_network.py`.
At report creation there were no other open workstreams identified as owning that
module. Re-run pressure-network and full CI if a later integration modifies the same
solver internals.
