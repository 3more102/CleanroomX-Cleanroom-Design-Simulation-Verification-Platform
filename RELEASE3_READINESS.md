# CleanroomX Release 3 Readiness Gate

Date: 2026-10-05

This document records the final integration gate for the current Release 3 development line. It intentionally changes no solver equation, engineering tolerance, project schema, requirement criterion, verification verdict semantics, or persisted engineering evidence.

## Candidate baseline

- Base branch: `main`
- Candidate main SHA before this documentation-only gate: `fa4c8c7b3677721cda3ac42530147f8633f5cc01`
- Development package identity: `0.103.0.dev0`
- Published stable baseline remains `v0.102.1` until a separate, explicit release closure is completed.

## Required final CI

The current repository CI must pass on this branch with:

- Python 3.11 complete test job;
- Python 3.12 complete test job;
- Python 3.13 complete test job;
- Windows PowerShell/CMD checkout launcher smoke;
- native IfcOpenShell ingestion smoke;
- aggregate `Required CI Gate`.

This branch exists specifically to validate the integrated current-main tree using the current workflow after the native BIM gate and the latest Requirements/Constraint editor changes are both present.

## Repository governance

Repository rulesets are still an administration-level closure item. Issue #519 tracks protection of `main` with required pull requests and CI. That governance item is separate from engineering-model behavior and must not change solver, schema, tolerance, or acceptance semantics.

## Release boundary

CleanroomX provides engineering screening, simulation, verification, and software/provenance evidence. It does not by itself establish cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.
