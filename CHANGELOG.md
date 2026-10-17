Warning: truncated output (original token count: 63505)
Total output lines: 2295

# Changelog

## Unreleased Release 3 — canonical two-room case audit — 2026-10-17

- Rebuild the generated OpenFOAM inputs and derived metadata from the declared case specification during audit, rejecting altered boundary conditions or metadata even when an unsigned manifest is rewritten with matching hashes.
- Require the exact two-room manifest schema, Foundation v10 release label, and blocked scientific-validation status; solver and physical validation remain separate and blocked.

## Unreleased Release 3 — OpenFOAM ProofGraph export — 2026-10-17

- Adds standalone ProofGraph export from synchronized OpenFOAM result manifests through the GUI.
- Re-hashes manifests, immutable receipts, and referenced result assets; mismatches stop export and missing configurations remain explicitly not checked.
- Limits PASS to local hash-link consistency, without claiming signatures, authenticity, or re-hashed source-field bytes. Solver convergence and independent physical validation remain not checked and BLOCKED.

## Unreleased Release 3 — responsive OpenFOAM console — 2026-10-17

- Bounds the live OpenFOAM console view to the latest 4,000 lines or 500,000 characters while retaining the full session transcript in a temporary spool that spills to disk after 1 MB.
- Adds an atomic **Save full log…** action, reports when the displayed tail is truncated or full-log capture fails, and closes the temporary spool with the workspace.
- Processes queued solver output in bounded batches so sustained output does not monopolize the Tk event loop; the compact workspace is covered by the real-Tk Xvfb gate. Solver and scientific-validation semantics are unchanged.

## Unreleased Release 3 — refined industrial GUI theme — 2026-10-16

- Refines the light and dark workstation palettes around slate surfaces and a teal primary action, with distinct Design, Analyze, Verify, Evidence, and Release accents.
- Gives the guided workflow clearer stage colors, a more legible active tab, calmer panel chrome, roomier table controls, and a compact status strip.
- Changes presentation only; project data, solver execution, verification rules, and results are unchanged.

## Unreleased Release 3 — OpenFOAM case-input GUI preflight — 2026-10-16

- Adds a read-only desktop action that checks all 24 generated case-input hashes against the local unsigned manifest and recomputes the three boundary-geometry/inlet-flow consistency audits before a solver run.
- Runs the preflight off the Tk event loop, bounds manifest and input sizes, rejects symbolic-link inputs, and reports the local-manifest trust boundary explicitly.
- Keeps solver execution, convergence, grid independence, and physical cleanroom validation outside this preflight; scientific validation remains blocked.

## Unreleased Release 3 — strict OpenFOAM block vertex indices — 2026-10-16

- Parses all eight `blockMeshDict` hex vertex references as signed integer tokens and rejects negative or out-of-range references before deriving exterior-face topology.
- Adds a regression for a negative index that would otherwise lose its sign during digit extraction; OpenFOAM cases and scientific-validation status are unchanged.

## Unreleased Release 3 — bounded OpenFOAM residual-trend diagnostics — 2026-10-15

- Adds bounded first-window versus tail-window median initial-residual summaries to the read-only single-log and nine-case triage commands. Short logs use disjoint reduced windows; trend ratios remain descriptive and never satisfy convergence or validation criteria.
- Records reproducible 36-field diagnostics of the archived synthetic Foundation v10 runs 67 and 68, preserving the failed terminal residual screens and blocked scientific-validation status.
- Does not alter OpenFOAM cases, solver settings, tolerances, acceptance criteria, or engineering verdicts.

## Unreleased Release 3 — checkMesh/polyMesh volume cross-check — 2026-10-15

- Reconstructs every cell volume from Foundation v10 ASCII `polyMesh` data and compares cell counts, min/max/total volumes, bounding-box volume, and manifest-derived room volume against the hash-bound `checkMesh` receipt.
- Records all five mesh-file hashes and representation-based tolerances in the uploaded audit artifact; this is synthetic mesh-data integrity evidence only and does not change the blocked scientific-validation status.

## Unreleased Release 3 — Foundation v10 surface-flux VTK audit — 2026-10-15

- Extends the opt-in nine-case Foundation v10 workflow to export native `phi` surface fluxes through pinned `foamToVTK -surfaceFields` support and independently recheck the resulting face-normal vectors against native face geometry and values.
- Adds bounded parsing for native surface-scalar fields and polyMesh face geometry, with explicit face-centre ordering, float32/ASCII serialization bounds, file hashes, synthetic regressions, and diagnostic-only evidence; no flow-balance threshold, convergence verdict, or scientific-acceptance status changes.

## Unreleased Release 3 — hash-bound OpenFOAM checkMesh diagnostics — 2026-10-15

- Adds a strict Foundation v10 parser for mesh counts, cell types, bounding box, face areas, cell volumes, and reported geometric checks; each receipt binds the parsed values to the raw log SHA-256.
- Records incomplete, ambiguous, non-finite, and tool-reported failure states explicitly, and stops before `simpleFoam` when `checkMesh` evidence is incomplete or reports failed checks.
- Labels the summary diagnostic-only and leaves project acceptance unevaluated because no project-specific mesh criteria or verified physical geometry are available.
- Adds a regression fixture copied from archived run 66 evidence; it does not create a real-case result or change the CFD scientific-validation status.

## Unreleased Release 3 — external dependency fingerprint runtime boundaries — 2026-10-04

- Narrows every application-layer stable dependency fingerprint boundary so only expected I/O/validation failures are converted into fail-closed dependency-state or private-snapshot errors.
- Covers initial capture, snapshot-copy retry rechecks, private-copy verification, backend snapshot verification, and later freshness revalidation; unexpected `RuntimeError` defects now propagate instead of being mislabeled as ordinary source instability, snapshot unavailability, or unverifiable evidence.
- Adds paired regressions proving expected I/O behavior is preserved while unexpected runtime defects remain visible at each boundary; solver equations, engineering tolerances, schemas, requirements, and verdict semantics are unchanged.

## Unreleased Release 3 — protect GUI revision restore destinations — 2026-10-04

- Applies the shared project/dependency output-identity guard before the desktop restores a saved project revision as a copy.
- Rejects destinations that alias the open project or any declared external engineering dependency both before restore work and again at the resolved atomic-replacement target, closing destination-alias races without weakening the revision writer's existing write-conflict guard.
- Adds a regression proving a declared dependency remains byte-for-byte unchanged when selected as the restore destination; solver equations, project schemas, tolerances, requirements, and verdict semantics are unchanged.

## Unreleased Release 3 — narrow project CLI runtime boundaries — 2026-10-04

- Adds a typed `CliStateError` for expected project/IFC CLI revision and state races instead of classifying every `RuntimeError` as a normal command failure.
- Narrows six project-level command boundaries so unexpected runtime defects propagate for debugging while expected source-change, migrated-project, publication-state, guarded-save lock/conflict/durability failures, and typed project-verification workflow/persistence failures retain deterministic stderr/exit-code handling.
- Adds regression coverage across project diagnostics, project dossier, project verification, requirements traceability, verification history, and IFC planning; solver equations, schemas, tolerances, requirements, and verdict semantics are unchanged.

## Unreleased Release 3 — root CLI strict input/output boundary — 2026-10-04

- Routes the top-level `cleanroomx` verification commands through the shared structural input normalizer and expected user-error boundary, so missing files and malformed user JSON fail with concise stderr instead of Python tracebacks.
- Serializes root verification and screening-calculator results through the canonical strict-JSON serializer, rejecting non-finite or otherwise non-JSON results instead of emitting permissive JSON tokens.
- Preserves explicit engineering verification exit code `2` and leaves unexpected runtime/programming defects visible; solver equations, schemas, tolerances, requirements, and verdict semantics are unchanged.

## Unreleased Release 3 — discovered CLI output publication guards — 2026-10-04

- Derives the completeness gate from every configured `[project.scripts]` entry point, then uses the Python AST to identify commands that expose a `--output` option.
- Requires every actual `publish_cli_output(...)` call to declare `protected_inputs` and every direct `atomic_write_text(...)` publication call in those commands to carry a `before_replace` guard.
- Prohibits direct `atomic_write_cli_output(...)` use in configured output-capable commands and automatically covers future console entry points regardless of module filename; solver equations, project schemas, engineering tolerances, requirement criteria, and verdict semantics are unchanged.

## Unreleased Release 3 — standalone CLI input error boundaries — 2026-10-04

- Adds one shared `cli_error_boundary` so expected standalone command `OSError` / `ValueError` failures return concise stderr and exit code 1 instead of a Python traceback.
- Adds a narrow `load_cli_input` boundary for the 22 direct file-loader CLIs, translating malformed user JSON structure failures such as missing fields or wrong container shapes without swallowing unexpected runtime defects from analysis/solver code.
- Applies the command boundary to all 24 standalone file-output engineering CLIs while preserving existing successful output, protected-output publication, strict-result JSON handling, and explicit engineering-domain exit codes.
- Adds regressions for missing required fields, wrong root shapes, explicit exit-code preservation, unexpected-runtime propagation, and source-level completeness guards; solver equations, schemas, tolerances, requirements, and verdict semantics are unchanged.

## Unreleased Release 3 — recovery comparison source-state classification — 2026-10-04

- Removes the separate source-path existence precheck from semantic recovery comparison and lets the canonical stable project loader determine source state.
- Classifies only a real `FileNotFoundError` at load time as a missing original source; permission and other read/validation failures remain unreadable evidence instead of being flattened by a racy precheck.
- Adds regressions for disappearance at the load boundary and non-missing access failure; recovery artifacts, project schema, solver behavior, requirements, and verdict semantics are unchanged.

## Unreleased Release 3 — deterministic portable-bundle private-snapshot diagnostics — 2026-10-04

- Preserves private stable-snapshot verification evidence at the portable-bundle inspection boundary without exposing random temporary-snapshot paths.
- Reports the original bundle path plus expected/actual byte size and SHA-256 evidence while preserving the existing `ProjectBundleError` API and typed `StableFileSnapshotVerificationError` cause.
- Adds a focused regression proving deterministic diagnostics; bundle schema, archive limits, extraction semantics, solver equations, engineering tolerances, requirement criteria, and verdict behavior are unchanged.

## Unreleased Release 3 — integrity boundary hardening — 2026-10-03

- Reuses the canonical stable-file revision identity and Windows path/handle binding policy for runtime Python-source provenance, rejecting same-size path/handle substitutions without changing the source-tree digest algorithm.
- Keeps the shared Windows stable-file binding portable across path/descriptor ID divergence using size, modification time, and a common creation-time clock, while runtime Python-source provenance additionally requires matching nonzero Windows file IDs to reject same-size/same-mtime path substitution.
- Preserves typed private-snapshot verification evidence at IFC import and direct dossier source-record boundaries while reporting the original source path instead of random private temporary-snapshot paths.
- Adds focused regressions for runtime provenance, IFC diagnostics, and dossier diagnostics; solver equations, engineering tolerances, IFC semantics, dossier schema, requirement criteria, and verdict behavior are unchanged.

## Unreleased Release 3 — deterministic assurance private-snapshot diagnostics — 2026-10-03

- Preserves typed `StableFileSnapshotVerificationError` evidence at the assurance-ingestion boundary without leaking random private temporary-snapshot paths.
- Reports the stable source path plus expected/actual size and SHA-256 evidence deterministically while preserving existing size-limit and generic I/O error contracts.
- Adds a regression for private snapshot verification failure; snapshot schema, solver equations, engineering tolerances, requirement criteria, and verdict semantics are unchanged.

## Unreleased Release 3 — verified stable snapshot authority — 2026-10-03

- Verifies private stable-file snapshots against the captured source digest before any consumer can use them, including empty-file snapshots.
- Consolidates project-bundle verification on the shared bounded stable-snapshot authority instead of maintaining a second archive capture implementation.
- Binds Windows path/descriptor identity to size plus modification/change timestamps while ignoring only non-portable device/inode identifiers, closing the same-size ABA gap identified in #891.
- Preserves snapshot-verification failures as typed private-snapshot errors through analysis execution instead of reclassifying them as live-source changes.

## Unreleased Release 3 — typed analysis dependency size failures — 2026-10-03

- Preserves canonical `StableFileSizeError` evidence for file-backed analysis dependencies instead of collapsing deterministic byte-ceiling violations into transient unavailable/unstable classifications.
- Keeps live-source size failures in the external-dependency change contract with explicit observed-size/limit evidence, while private execution-snapshot failures retain the snapshot-error contract.
- Covers initial fingerprinting, snapshot capture retry, private-copy verification, and backend snapshot verification without changing solver equations, engineering tolerances, project schemas, or verdict semantics.

## Unreleased Release 3 — assurance snapshot strict-JSON error boundary — 2026-10-03

- Converts non-strict design-assurance analysis results into the assurance-snapshot domain error contract during both snapshot creation and deterministic replay verification.
- Prevents `cleanroomx-assurance-snapshot` from leaking a raw `StrictJSONError` traceback if an analysis implementation returns non-finite or otherwise invalid JSON content.
- Adds direct creation/replay regressions plus a CLI no-traceback regression while preserving snapshot schema, canonicalization, solver equations, engineering tolerances, requirements, and verdict semantics.

## Unreleased Release 3 — dossier CLI manifest error boundary — 2026-10-03

- Converts strict-JSON, UTF-8, size, missing-file, and other manifest read failures at the `cleanroomx-dossier` CLI boundary into deterministic stderr diagnostics and exit code 1 instead of exposing a Python traceback.
- Rejects invalid manifests before analysis execution or output publication.
- Adds regressions for malformed syntax, non-finite JSON, invalid UTF-8 bytes, oversized manifests, and missing paths while preserving valid dossier analysis and output contracts.

## Unreleased Release 3 — recovery source-inspection race classification — 2026-10-03

- Removes the suppressing `Path.exists()` precheck from recovery source-state classification so non-missing filesystem errors cannot be mislabeled as a missing original project.
- Treats only `FileNotFoundError` from the canonical stable source fingerprint as a missing source, while preserving typed oversize and other I/O failures as `source_oversized` and `source_unavailable`.
- Handles a source that disappears during fingerprinting through the returned `exists=false` evidence instead of falling through to `source_changed`.
- Adds regressions for disappearance after selection and disappearance during fingerprinting; recovery validity, restore non-overwrite behavior, schemas, solvers, requirements, and verdicts are unchanged.

## Unreleased Release 3 — typed recovery strict-JSON size failures — 2026-10-03

- Preserves the canonical `StrictJSONSizeError` classification when recovery-artifact ingestion exceeds its hard ceiling.
- Translates the typed failure into the existing recovery-specific size error while retaining observed-size/limit evidence through the exception cause.
- Keeps unrelated strict-JSON failures on the generic invalid-recovery path, eliminating accidental classification by message text.
- Adds regressions for both the typed oversize path and a size-like generic strict-JSON message; recovery schema, quarantine semantics, project persistence, solver behavior, requirements, and verification verdicts are unchanged.

## Unreleased Release 3 — typed runtime source revision changes — 2026-10-03

- Replaces runtime-provenance retry classification based on exception-message text with a dedicated typed source-tree revision-change failure.
- Retries only genuine source identity races while propagating unrelated runtime failures immediately, even if their message contains the old race wording.
- Preserves runtime fingerprint schema, source-byte limits, deterministic hashing, solver equations, engineering tolerances, requirement criteria, and verification verdict semantics.
- Adds regressions for typed retry behavior and false-positive message matching.


## Unreleased Release 3 — exact stable-file read ceilings — 2026-10-03

- Makes the canonical stable-file authority request at most the remaining configured byte allowance plus one sentinel byte instead of issuing fixed 1 MiB reads before enforcing smaller limits.
- Applies the exact read ceiling to both stable SHA-256 fingerprinting and digest-bound private snapshots while preserving the existing size-error contract, retry policy, and accepted-file digests.
- Adds regressions proving a file exactly at the configured limit is read with bounded requests in both modes.
- Changes no project schema, solver equation, engineering tolerance, requirement criterion, ProofGraph verdict, or persistence format.

## Unreleased Release 3 — typed stable-file size failures — 2026-10-03

- Adds a canonical `StableFileSizeError` from the shared stable-file hashing/snapshot authority, carrying the source path, observed byte count, and configured limit.
- Fails immediately on deterministic size-limit violations instead of retrying them as transient I/O failures.
- Removes message-text matching from project revision capture, IFC ingestion, and design-assurance snapshot ingestion; only the typed size failure is translated into each domain's existing public error contract.
- Adds regressions proving oversized inputs remain rejected while unrelated `OSError` messages cannot be misclassified as size violations; no solver equation, engineering tolerance, requirement criterion, ProofGraph verdict, project schema, or persistence format changes.

## Unre…53505 tokens truncated… fan-speed operating points.
- Uses an explicit user-supplied absolute airflow tolerance; exact agreement remains the zero-tolerance default.
- Preserves unsolved fan studies and fan-speed cases as `not_comparable` rather than converting missing operating points into failures.
- Adds pass, fail, not-comparable, and pass-with-unresolved-studies states with per-operating-point evidence in Markdown/JSON dossiers.
- Propagates solved mismatches into dossier attention items and unresolved comparisons into unchecked tracking.
- Added focused unit tests, an end-to-end dossier example, documentation, and package/runtime version 0.22.0.
- Keeps the feature bounded as cross-study consistency, not airflow adequacy, fan selection, commissioning acceptance, cleanroom certification, or a standards-derived tolerance.

## v0.21 automatic Darcy friction screening — 2026-09-23

- Added optional roughness/kinematic-viscosity-driven Darcy friction-factor resolution for path-based duct models and fixed-demand supply trees.
- Computes Reynolds number from section velocity, hydraulic diameter, and explicit kinematic viscosity.
- Uses the Darcy laminar relation `f = 64/Re` for circular ducts below `Re = 2300` and solves the Colebrook equation for `Re >= 2300`.
- Rejects automatic laminar friction for noncircular ducts instead of applying the circular-duct relation; users can still supply an explicit friction factor.
- Preserves the existing explicit `friction_factor` workflow and rejects ambiguous manual-plus-automatic inputs.
- Resolves supply-tree friction after terminal-demand airflows are propagated, so each branch uses its solved airflow.
- Resolves reference-flow fan/duct friction at the declared section reference flow, then holds that factor constant while deriving the bounded fixed-ratio quadratic system curve.
- Leaves passive parallel-flow and fan-driven parallel-network solvers on explicit fixed resistance; v0.21 does not add nonlinear variable-friction network balancing.
- Added focused regression coverage, documentation, an automatic-friction HVAC example, and 0.21.0 metadata.


## v0.20 dossier-integrated fan-speed studies — 2026-09-23

- Integrated v0.19 fan-speed affinity-law studies into engineering dossier manifests as an optional analysis list.
- Added SHA-256 source fingerprinting for every referenced fan-speed study input.
- Aggregated individual speed-case statuses so any bounded no-intersection case becomes a dossier attention item.
- Added fan-speed study/case counts to the executive summary and detailed speed-ratio, rpm, airflow, and pressure evidence to Markdown dossiers.
- Added a solved dossier fan-speed fixture plus end-to-end and adverse-state regression coverage.
- Moved the dossier non-empty-source validation after all optional fan-study lists so fan-only dossiers remain valid.
- Kept existing manifests backward compatible because the new fan-speed list is optional.
- Bumped package/runtime metadata to v0.20.0.

## v0.19 bounded fan-speed affinity-law study — 2026-09-23

- Added explicit user-supplied fan speed-ratio sweeps from a supplied reference fan curve.
- Applied classical fan affinity-law scaling to supplied points: airflow proportional to speed, pressure proportional to speed squared, and theoretical power scaling proportional to speed cubed.
- Reused the existing bounded fan/system operating-point solver for every transformed speed case, preserving no-extrapolation and no-intersection behavior.
- Added optional reference-rpm reporting while keeping allowed fan/VFD speed ranges external to CleanroomX.
- Kept fluid air power (Q×pressure) separate from the cubic affinity-law power-scaling indicator; no motor/VFD efficiency or electrical-input model is inferred.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-speed` CLI, example data, documentation, and regression coverage.
- Bumped package/runtime metadata to v0.19.0.

## v0.18 complete engineering dossier — 2026-09-23

- Integrated the v0.17 verification/HVAC duplicated-airflow consistency checker into engineering dossier manifests.
- Reuses the standalone checker's exact-name matching, absolute airflow tolerance, identical-room-set option, statuses, and scope boundary.
- Propagates consistency failures into dossier attention tracking and preserves `not_comparable` as an unresolved state.
- Adds consistency evidence to Markdown dossiers plus an end-to-end example and regression tests.
- Requires both verification and HVAC project inputs when a dossier consistency check is configured.
- Added reference-flow fan/duct-network studies to dossier manifests, executive summaries, Markdown reports, SHA-256 source traceability, and end-to-end regression coverage.
- Added fan-driven passive parallel-network studies to the same dossier workflow while preserving bounded no-extrapolation/no-intersection states.
- Promotes unresolved integrated fan-network intersections to dossier attention items rather than collapsing them into a generic success state.
- Bumped package/runtime metadata to v0.18.0 while keeping all new dossier fields optional for backward-compatible manifests.

## v0.17 cross-module input consistency — 2026-09-23

- Added a standalone verification/HVAC consistency checker for duplicated room-airflow inputs.
- Matched rooms by exact room name and compared verification supply airflow against HVAC cleanroom airflow.
- Added an explicit user-supplied absolute consistency tolerance with exact agreement as the default; no engineering tolerance is invented.
- Added optional identical-room-set enforcement while preserving unmatched-room evidence when different module scopes are intentional.
- Added pass, pass-with-scope-difference, fail, and not-comparable states plus Markdown/JSON reporting, CLI, example data, documentation, and regression coverage.
- Kept the workflow explicitly bounded as input consistency rather than airflow adequacy, cleanroom acceptance, certification, or standards conformity.

## v0.16 fan-driven passive parallel-network integration — 2026-09-23

- Coupled the bounded fan/system operating-point solver to the passive common-pressure-node parallel-path model.
- Added analytical equivalent network resistance for pressure-balanced paths following fixed R·Q² behavior.
- Added fan/system operating-point solving followed by redistribution of the solved total airflow across the original branches.
- Added fixed-pressure plus network-pressure decomposition, fan/system residual, mass-balance residual, equal-pressure residual, and per-section flow/loss reporting.
- Preserved no-extrapolation behavior when the operating point lies outside supplied fan data.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-network` CLI, example data, tests, and engineering-scope documentation.
- Kept this distinct from v0.14 reference-flow fan/duct integration: v0.16 solves the passive branch split from common pressure instead of holding reference flow fractions fixed.
- Kept the workflow explicitly bounded: no arbitrary looped-network solution, variable friction-factor iteration, dampers/controls, leakage, system effect, acoustics, fan-law scaling, stall/surge acceptance, or manufacturer selection.


## v0.15 psychrometric state uncertainty — 2026-09-23

- Added uncertain dry-bulb temperature, relative humidity, and total-pressure inputs with strict interval-domain validation.
- Added deterministic evaluation of every unique rectangular uncertainty-box corner using the existing CleanroomX psychrometric equations.
- Added bounded vapor-pressure, humidity-ratio, enthalpy, specific-volume, dew-point, and moist-air specific-heat results.
- Added provenance completeness reporting without inventing uncertainty magnitudes, probability distributions, covariance, or acceptance limits.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-psychrometric-uncertainty` CLI, example data, documentation, and regression coverage.
- Kept the v0.10 thermal uncertainty workflow psychrometrically fixed; explicit cross-module coupling remains a later milestone.

## v0.14 fan/duct-network operating-point integration — 2026-09-23

- Added a reference-flow fan/duct-network study that derives path quadratic resistance from explicit duct geometry, Darcy friction factors, air density, local-loss coefficients, and section reference airflow fractions.
- Added critical-path selection from the derived path resistances and direct reuse of the bounded fan/system operating-point solver.
- Added per-path and per-section reference/operating airflow and pressure-drop reporting.
- Added validation that section reference airflow does not exceed the declared reference system airflow, plus rejection of zero-resistance paths.
- Added JSON loading, Markdown/JSON reporting, the cleanroomx-fan-duct CLI, example data, documentation, and regression tests.
- Kept the workflow explicitly bounded: section flow fractions, density, friction factor, geometry, and local-loss coefficients remain fixed while total airflow varies; no general network balancing, variable-friction iteration, leakage, system effect, stall/surge, or controls are inferred.

## v0.13 integrated engineering dossier — 2026-09-23

- Added a manifest-driven engineering dossier that aggregates room/cascade verification, HVAC/duct screening, v0.12 HVAC fan-curve design-duty verification, measured recovery, uncertainty/provenance, qualification uncertainty, thermal/HVAC uncertainty, and standalone fan/system operating-point studies.
- Added SHA-256 fingerprints for every referenced source file so dossier inputs are auditable and reproducible.
- Preserved component-specific fail, incomplete, indeterminate, not-checked, solved, outside-supplied-range, and no-intersection states instead of collapsing the package into a certification verdict.
- Added attention tracking for HVAC fan-duty failures/out-of-range cases, unresolved standalone fan/system intersections, and thermal uncertainty failures/indeterminate capacity checks.
- Added Markdown/JSON dossier output, the `cleanroomx-dossier` CLI, example manifest, documentation, and regression coverage.
- Kept older dossier manifests compatible by making thermal-uncertainty and standalone fan-study fields optional.
- Kept the dossier explicitly bounded as a traceability/reporting layer rather than cleanroom certification, regulatory approval, commissioning acceptance, or fan/equipment selection.

## v0.11 fan/system operating-point solver — 2026-09-23

- Added explicit fan performance curves from ordered airflow/pressure points with strict finite and monotonic validation.
- Added fixed-plus-quadratic system curves using project-supplied fixed pressure and resistance.
- Added bounded fan/system intersection solving with piecewise-linear fan interpolation and no fan-curve extrapolation.
- Added operating airflow, fan/system pressure, pressure residual, interpolation segment, and fluid air-power reporting.
- Added explicit no-intersection status when the operating point lies outside the supplied fan data.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-curve` CLI, example data, tests, and documentation.
- Kept the workflow explicitly bounded: no inferred fan laws, manufacturer acceptance, stall/surge limits, variable resistance, system effect, controls, or electrical-power inference.

## v0.10 thermal uncertainty screening — 2026-09-23

- Added deterministic interval propagation for internal sensible/latent loads, cleanroom airflow, makeup airflow, and optional supply-air temperature.
- Added conservative cooling/heating capacity requirement intervals with project-configured available-capacity pass/fail/indeterminate checks.
- Added governing supply-airflow intervals across cleanroom, makeup-air, and sensible-load airflow candidates.
- Added provenance completeness reporting for every uncertain thermal input.
- Added JSON loading, Markdown/JSON reporting, a dedicated `cleanroomx-thermal-uncertainty` CLI, example data, tests, and documentation.
- Kept room/outdoor psychrometric states fixed and explicitly bounded the workflow as screening rather than statistical uncertainty, hourly load simulation, or equipment selection.

## v0.9 passive parallel-path flow solver — 2026-09-23

- Added analytical airflow distribution across two or more passive duct paths sharing common pressure nodes.
- Added fixed-resistance R·Q² path modeling from explicit Darcy friction, geometry, air density, and local-loss coefficients.
- Added solved per-path airflow, common pressure drop, per-section losses, mass-balance residual, and equal-pressure residual reporting.
- Added circular/rectangular geometry support, finite-input validation, JSON loading, Markdown reporting, and the `cleanroomx-duct-flow` CLI.
- Added regression coverage for equal and unequal resistances, rectangular sections, zero-resistance rejection, non-finite inputs, mass continuity, and equal-pressure verification.
- Kept the solver standalone and explicitly bounded: it does not yet combine the v0.8 supply tree with arbitrary loops, fan curves, dampers, leakage, or variable-friction-factor iteration.

## v0.8 branch-flow supply-tree solver — 2026-09-23

- Added directed supply-tree topology with explicit source, branches, and fixed leaf-terminal airflow demands.
- Added automatic upstream branch-flow propagation by steady-state mass continuity.
- Reused the hardened v0.6.1 Darcy-Weisbach/local-K section model at each solved branch airflow.
- Added source-to-terminal accumulated pressure losses, critical-terminal selection, and node continuity residual reporting.
- Added topology validation for multiple feeds, unreachable nodes, missing leaf demands, and invalid terminal placement.
- Integrated branch-flow critical-path pressure loss into preliminary fan duty with an HVAC airflow-consistency guard.
- Kept the solver explicitly limited to fixed-demand trees rather than looped or pressure-balanced networks.
- Added JSON loading, Markdown reporting, tests, example data, and documentation.


## v0.7 qualification uncertainty — 2026-09-23

- Added uncertainty-aware minimum and maximum qualification checks for project-configured measured quantities.
- Added conservative room-to-room pressure-cascade interval propagation using uncertain pressure measurements.
- Added pass/fail/indeterminate overall qualification status with failure taking precedence over ambiguity.
- Preserved requirement references and input provenance while keeping traceability completeness separate from numerical acceptance.
- Added JSON loading, Markdown/JSON reports, a dedicated `cleanroomx-qualification` CLI, example data, tests, and documentation.
- Kept the workflow explicitly bounded as deterministic interval screening; no ISO class, pressure, particle, or conformity threshold is embedded.

## v0.6.1 duct-input hardening — 2026-09-23

- Rejected non-finite duct inputs (NaN and positive/negative infinity) before pressure-loss analysis.
- Added regression coverage for airflow, air density, friction factor, local-loss coefficient, length, and circular/rectangular geometry dimensions.
- Synchronized package runtime metadata with the v0.6 release line.
- Corrected duct-model documentation that still referred to v0.5.

## v0.6 duct critical-path pressure loss — 2026-09-23

- Added circular and rectangular duct-section models with strict input validation.
- Added velocity, velocity-pressure, hydraulic-diameter, Darcy-Weisbach friction-loss, and local-loss calculations.
- Added user-defined duct paths and critical-path pressure-loss selection.
- Added explicit air-density, Darcy friction-factor, and local loss-coefficient inputs; no hidden fitting or roughness assumptions.
- Integrated computed critical-path duct loss into preliminary supply-fan sizing while preserving legacy manual duct-loss input when no network is configured.
- Added duct-network JSON loading, Markdown reporting, example data, tests, and engineering-scope documentation.
- Documented ASHRAE duct-design references and kept the model explicitly preliminary rather than a branch-flow/network solver.

## v0.5 uncertainty/provenance foundation — 2026-09-23

- Added explicit provenance records for engineering inputs, including source type/name, reference, revision, date, uncertainty basis, and notes.
- Added absolute uncertainty bounds for room dimensions and supply airflow.
- Added deterministic conservative interval propagation for room volume and supply ACH.
- Added robust pass/fail/indeterminate/not-checked evaluation against a project-configured minimum ACH requirement.
- Added provenance-completeness reporting without conflating missing traceability with numerical acceptance.
- Added JSON loading, Markdown/JSON reporting, a dedicated CLI, example data, tests, and documentation.
- Kept the method explicitly bounded as interval screening rather than a statistical measurement-uncertainty budget.

## v0.4 recovery qualification — 2026-09-23

- Added measured particle-recovery test records with strict sample validation.
- Added explicit project target concentration and optional maximum recovery-time criteria.
- Added pass/fail/incomplete/not-checked qualification states.
- Added observed recovery windows based on discrete samples without inventing an exact crossing time.
- Added optional traceability metadata for instrument, sample location, occupancy state, and method/protocol reference.
- Added log-linear decay diagnostics, R², fitted target crossing, and estimated effective ACH as screening outputs only.
- Added JSON loading, Markdown/JSON reporting, a dedicated CLI, example data, tests, and documentation.
- Kept ISO/project acceptance thresholds external; no proprietary ISO limits are embedded.

## v0.3 airflow/fan extension — 2026-09-23

- Added per-room supply/return/exhaust/transfer airflow balance.
- Added explicit minimum airflow-surplus verification and margin reporting.
- Added optional filter/FFU pressure-drop input.
- Added preliminary central supply-fan static-pressure, air-power, shaft-power, and electrical-input calculations.
- Added airflow/fan report sections, example inputs, tests, and documentation.
- Kept all limits and pressure-drop values requirement-driven; no ISO class is mapped to airflow surplus or fan sizing.

## v0.2 HVAC extension — 2026-09-23

- Added psychrometric air-state calculations.
- Added explicit sensible and latent room loads.
- Added outdoor/makeup-air load calculations.
- Added preliminary cooling/heating capacity.
- Added cleanroom-vs-makeup-vs-thermal governing airflow selection.
- Added optional FFU/filter-unit sizing.
- Added a separate HVAC CLI, JSON project loader, Markdown reporting, tests, and documentation.
- Preserved the existing particle, room, and pressure-cascade verification architecture.

## Unreleased — Release 2 architecture consolidation

- Consolidates durable verified atomic persistence behind one shared persistence layer, including durable creation of previously missing nested parent directories.
- Adds versioned crash-recovery integrity evidence while preserving legacy v1 recovery readability as unverified evidence.
- Adds guarded saved-project revision history with migration-aware stable source revision tracking.
- Consolidates project, analysis, and spatial edits into one bounded transactional Undo/Redo stream.
- Makes completed analysis runs immutable snapshots and preserves exact submitted-input, implementation, runtime, and external-dependency provenance.
- Adds a bounded integrity-checked persisted analysis run-history ledger.
- Adds analysis plugin API v1 with deterministic discovery and built-in-key collision protection.
- Adds integrity-checked portable project bundles and self-contained verified portable engineering HTML reports.
- Adds Release 2 regression/performance gates while preserving existing solver equations, tolerances, and acceptance semantics.
