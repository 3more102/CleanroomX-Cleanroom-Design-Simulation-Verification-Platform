# CleanroomX v0.100.0 Release Checklist

This is the merge gate for the final v0.100.0 consolidation.

## Functional integrity

- [x] v0.99.1 installed desktop packaging and self-contained `--demo` retained.
- [x] Application registry is validated before normal Tk startup.
- [x] Abandoned work remains exclusive until its backend worker exits.
- [x] Save As and JSON import preserve external consistency/dossier file referents.
- [x] Project persistence and GUI exports use same-directory atomic UTF-8 replacement.
- [x] Fan/system plots reuse backend-evaluated system-pressure evidence.
- [x] Every application run records canonical input SHA-256 provenance.
- [x] Consistency/dossier dependencies record before/after SHA-256 and byte-size evidence.
- [x] Run-bundle JSON export preserves execution provenance.

## Required CI gates

The exact pull-request head SHA must pass:

- Python 3.11, 3.12, and 3.13 complete test suites.
- v0.91 selected-projection compatibility regressions.
- v0.92 full-bisection projection compatibility regressions.
- v0.93 supplied-point replay regressions.
- v0.94 canonical solver-provenance regressions.
- v0.95 solver-result-integrity regressions.
- v0.100.0 final consolidation regressions.
- Clean wheel build/install and installed `cleanroomx-gui --check`.
- Python 3.13 Tk/Xvfb smoke of the installed `cleanroomx-gui --demo` path.
- Representative CLI JSON and Markdown smoke checks.

## Engineering boundary

No intentional changes are made to validated solver equations, numerical tolerances, uncertainty enumeration semantics, no-extrapolation behavior, or engineering acceptance criteria.

## Merge rule

Do not merge until every required GitHub Actions job for the exact final head SHA is green.
