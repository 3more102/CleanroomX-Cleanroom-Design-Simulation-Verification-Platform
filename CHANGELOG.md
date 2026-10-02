# Changelog

## Unreleased Release 3 — bounded desktop analysis-input import — 2026-10-02

- Routes **Import Analysis Input JSON** through the canonical bounded, revision-stable strict-JSON file reader instead of materializing the complete source with `Path.read_text()`.
- Preserves duplicate-key, non-finite-number, invalid-UTF-8, excessive-nesting, and analysis file-reference rebasing behavior while rejecting oversized or replaced sources before project mutation.
- Adds focused GUI regressions proving oversized input and source-path replacement fail closed without changing the selected analysis input.
- Changes no solver equation, numerical tolerance, project schema, requirement criterion, or verification verdict semantic.

## Unreleased Release 3 — development package identity — 2026-10-02

- Changes moving Release 3 `main` package/runtime identity to `0.103.0.dev0`, distinct from the immutable published `v0.102.1` baseline.
- Keeps `pyproject.toml` and `cleanroomx.__version__` synchronized and removes active CI/GUI tests that treated moving `main` as exactly `0.102.1`.
- Adds a focused packaging-contract regression that requires an explicit numeric `.devN` identity and rejects reuse of the published stable version.
- Leaves historical v0.102.1 release evidence, validation documents, demo fixtures, and release publisher checks unchanged.
- Changes no solver equation, engineering tolerance, project schema, acceptance criterion, or historical release tag.

## Unreleased Release 3 — standalone CLI publication safety — 2026-10-02

- Routes every standalone file-backed engineering CLI through one protected atomic output writer.
- Rejects output destinations that alias declared engineering inputs by resolved path or existing same-file identity, and rechecks immediately before atomic replacement.
- Extends strict JSON serialization across the standalone result-producing CLI surface so non-finite or Python-only values fail closed before publication.
- Protects dossier dependencies, consistency-project pairs, assurance snapshots, and project-bundle destinations against overwrite races.
- Restacks the reviewed unique delta from superseded PR #748 onto exact current main without importing its stale history.

## Unreleased Release 3 — psychrometric dew-point domain and phase-boundary hardening — 2026-10-02

- Adds direct regressions against the official IAPWS R14-08 230 K sublimation-pressure verification point and IAPWS-IF97 Region 4 300 K saturation-pressure verification point.
- Splits ice and liquid saturation-pressure helpers so dew-point inversion brackets exactly one continuous phase curve.
- Fails explicitly when water-vapor pressure lies in the narrow 0 °C pressure gap between the selected IAPWS ice and liquid equilibrium curves instead of silently returning a non-root near 0 °C.
- Replaces the arbitrary -100 °C dew-point inversion cutoff with the published IAPWS R14-08(2011) ice-Ih sublimation-pressure lower validity limit of 50 K (-223.15 °C), while failing closed below that domain.
- Adds regression coverage for an ultra-dry state whose dew point is below -100 °C but remains inside the IAPWS domain.
- Preserves the merged ASHRAE/IAPWS saturation equations, AirState dry-bulb operating range, humidity-ratio/enthalpy/specific-volume equations, and ordinary dew-point results.

## Unreleased — CI supply-chain hardening — 2026-10-01

- Pins every third-party GitHub Action used by the repository workflows to a reviewed immutable commit SHA while retaining human-readable upstream version comments.
- Covers Linux/Python CI, Windows launcher smoke, solution-manual publication, and all immutable v0.100.0 through v0.102.1 release publishers.
- The pinned SHAs were verified against the official `actions/checkout` and `actions/setup-python` repositories; no engineering model, solver, project schema, evidence semantic, or acceptance criterion is changed.


## Unreleased Release 3 — protected report publication identity recheck — 2026-10-01

- Rechecks project-source and declared file-backed dependency path identity immediately before publishing project diagnostics, engineering dossier, requirements traceability, and canonical verification artifacts.
- Applies the same protected-output boundary to desktop project-dossier export so a pathname identity change after the initial save-dialog validation fails closed before the atomic writer runs.
- Retains the existing revision-stability checks and atomic writer; this hardening closes the remaining time-of-check/time-of-use gap in project-facing report publication without changing engineering calculations or verdict semantics.
- Adds focused regressions proving a second publication-time guard runs and that an existing valid output is preserved when the recheck fails.

## Unreleased Release 3 — persisted project evidence authority — 2026-10-01

- Extends the canonical `project.metadata.requirement_evidence_mappings` registry with optional explicit evidence-authority decisions that select one already-mapped evidence identity for an otherwise ambiguous requirement/subject binding.
- Keeps ambiguity fail-closed: multiple active mappings for one binding are accepted only when they belong to the same analysis and a validated authority decision selects one active mapping; unnecessary, duplicate, cross-analysis, unknown, or out-of-scope decisions are rejected.
- Carries the same authority decision through project-native execution, canonical verification replay, ProofGraph projection, guarded verification-history persistence, and read-only requirements traceability.
- Retains every candidate evidence record while the canonical finding and ProofGraph check use only the explicitly selected mapping; authority provenance remains hash-bound by both the mapping-registry digest and canonical verification digest.
- Preserves the previous registry/result shape and digest when no authority decision is configured; authority-bearing mapping registries use an explicit metadata sub-schema v2 while legacy no-authority registries remain canonical v1. No solver equation, engineering unit conversion, requirement criterion, or top-level project schema version changes.

## Unreleased Release 3 — project batch protected-output hardening — 2026-10-01

- Protects `cleanroomx-project-run --output` from replacing the source project, same-file aliases such as hardlinks, or declared file-backed engineering dependencies.
- Reuses the canonical project/dependency path-identity guard already used by other project-facing operator surfaces.
- Revalidates source revision and protected output identities immediately before atomic publication, closing the post-analysis publication race.
- Adds focused regressions for direct source overwrite, same-file aliases, external dependency overwrite, single-revision guard/execution binding, path-resolution failures, and pre-publication source/dependency alias mutation.
- Changes no solver equation, numerical tolerance, analysis input, project schema, project-batch schema, or execution-order semantics.

## Unreleased Release 3 — ProofGraph evidence precedence and conflict policy — 2026-10-01

- Adds an explicit strongest-first evidence-kind/source precedence policy over existing ProofGraph evidence without mutating or deleting historical records.
- Resolves a claim only when policy precedence produces one unique preferred item; equally preferred disagreements fail closed as explicit conflicts.
- Keeps equal preferred claims coequal when value and unit match, and deliberately performs no hidden unit conversion, timestamp freshness inference, confidence weighting, or solver recomputation.
- Adds deterministic report schema `cleanroomx.proofgraph-evidence-precedence` v1 with candidate, preferred, shadowed, selected, and conflict evidence identity.
- Marks the report machine-readably as `decision_scope=assessment_only` and `changes_canonical_verification=false` so precedence inspection cannot be mistaken for canonical requirement-verdict authority.
- Adds regression coverage for precedence selection, source tie-breaking, equal-value peers, fail-closed value/unit conflicts, deterministic ordering, subject isolation, and graph immutability.

## Unreleased Release 3 — verification-history current-context hardening — 2026-10-01

- Reuses the canonical verification-currency record-context helper in the desktop Verification History surface instead of maintaining duplicate GUI logic.
- Validates retained-record and current-assessment input types and requires a non-empty stable analysis identity before projecting current context.
- Extends focused regressions for historical/latest/orphaned record context, defensive-copy behavior, malformed inputs, and identity mismatch.
- Changes no solver equation, numerical tolerance, requirement criterion, persisted verification record, ledger hash, dependency fingerprint, CLI schema, or project schema.

## Unreleased Release 3 — desktop requirement evidence drill-down — 2026-10-01

- Adds a structured read-only **Requirement Evidence** view inside **Analysis → Verification History...**.
- Projects each retained canonical finding as requirement → bound evidence → historical verdict without recomputing the verdict against current project state.
- Shows subject scope, explicit criterion, retained actual value/unit, evidence freshness, source, and exact result locator while preserving the complete canonical record in a separate tab.
- Uses the already integrity-validated persisted verification record and changes no solver equation, acceptance criterion, persisted verification schema, historical verdict, or project schema.

## Unreleased Release 3 — project requirements traceability CLI — 2026-10-01

- Adds `cleanroomx-project-traceability` as a read-only JSON/Markdown operator and automation surface over canonical persisted project requirements and requirement-to-analysis evidence mappings.
- Reuses the canonical registry parsers and active-mapping cross-validation; retained disabled/superseded references remain historical and are not silently rebound when analysis identity or kind no longer matches.
- Binds every report to one stable saved-project revision and protects both the project source and declared file-backed engineering dependencies from output overwrite.
- Changes no solver equation, numerical tolerance, requirement acceptance criterion, verification verdict, persisted registry, or project schema.

## Unreleased Release 3 — explicit evidence authority — 2026-10-01

- Adds an opt-in, fail-closed authority decision for requirement/entity bindings that contain multiple competing evidence records; the default remains invalid ambiguity with no silent selection.
- Requires the exact requirement ID, subject, selected already-bound evidence ID, authority source/issuer, decision reference, decision revision, and a non-empty rationale; stale, mismatched, duplicate, provenance-incomplete, or unnecessary authority decisions are rejected.
- Retains every competing evidence record in the canonical evidence collection and finding candidate list while evaluating only the explicitly selected authority.
- Hash-binds the normalized authority document, including decision identity/provenance, to the verification result without changing legacy result shape or digest when no authority policy is supplied.
- Adds deterministic ordering, PASS/FAIL selection, stale-policy rejection, duplicate-policy rejection, and compatibility regression coverage without changing solver equations, units, tolerances, or requirement acceptance semantics.

## Unreleased Release 3 — workflow ProofGraph cross-artifact integrity — 2026-10-01

- Cross-checks each project-requirements ProofGraph verification run against the canonical workflow requirements, evidence, and verification digests and status.
- Bumps the project-requirements workflow output to schema v2 and retains the complete canonical normalized requirements snapshot so its SHA-256 and full RequirementSet projection can be re-verified instead of trusting a lossy graph projection.
- Recomputes canonical verification from the retained requirements authority plus canonical bound evidence, and rejects resealed ProofGraphs whose RequirementSet metadata or requirement criteria differ from that authority.
- Verifies ProofGraph source-finding metadata against the canonical verification findings for the graph's requirement set.
- Verifies projected ProofGraph evidence and evidence sources against the exact bound workflow evidence, including value, unit, source revision, project revision, subject, locator provenance, calculation source, and evidence kind.
- Adds regressions that deliberately reseal both `graph_sha256` and `workflow_sha256` after tampering, proving cross-artifact inconsistencies still fail closed.
- Changes no solver equations, numerical tolerances, requirement comparison semantics, persisted project schema, or verification verdict rules.

## Unreleased Release 3 — external plugin trust gate — 2026-10-01

- Adds operator-controlled `trusted`, `disabled`, and `allowlist` modes for installed analysis plugins, with external plugins disabled by default until an operator explicitly opts in.
- Applies deny decisions before `entry_point.load()`, so blocked external plugins are not imported through the CleanroomX plugin entry point.
- Supports canonicalized distribution-name allowlisting with optional exact version pins and fails closed on invalid configuration, missing distribution identity, or pin mismatch.
- Exposes the effective trust policy in application-registry diagnostics while preserving plugin API v1, built-in analyses, solver equations, engineering tolerances, and project schema.

## Unreleased Release 3 — retained canonical ProofGraph verification evidence — 2026-10-01

- New persisted project-verification records retain the complete canonical ProofGraph documents alongside their existing SHA-256 identities.
- Ledger validation reparses each retained graph, requires canonical serialization, unique digest ordering, and exact agreement with `proofgraph_sha256`; legacy hash-only schema-v1 records remain readable.
- The configured verification-history byte budget now fails closed when the newest record alone exceeds it instead of silently retaining an oversized record.
- No solver equation, requirement comparison, ProofGraph verdict rule, or historical verification identity semantic is changed.

## Unreleased Release 3 — canonical requirement unit conversion — 2026-10-01

- Adds a centralized, dependency-free engineering-unit authority for requirement verification with explicit dimensional families and deterministic conversion provenance.
- Converts compatible numeric evidence into the persisted requirement unit before equality/minimum/maximum/range comparison, including affine temperature conversion.
- Retains raw evidence value/unit alongside converted findings and records the exact source/target canonical units, scale, offset, and engineering dimension used.
- Fails closed for unsupported unit spellings, incompatible dimensions, named-unit versus unitless mismatches, and non-numeric criteria with differing units.
- Preserves the legacy exact-unit finding shape and changes no solver equations, requirement criteria, persisted project schema, or historical verification records.

## Unreleased Release 3 — qualification uncertainty ProofGraph — 2026-10-01

- Adds a direct ProofGraph adapter for the canonical qualification-uncertainty workflow without duplicating interval calculations or decision semantics.
- Represents measured qualification inputs as commissioning evidence and canonical conservative intervals/differential-pressure intervals as calculation evidence with explicit upstream lineage.
- Preserves canonical PASS/FAIL/INDETERMINATE only when the measurements needed by the check carry source provenance; missing provenance fails closed to UNKNOWN while retaining the numerical result in verification-run metadata.
- Adds deterministic round-trip regression coverage and changes no configured limits, solver equations, project schema, or certification claims.

## Unreleased Release 3 — cooperative project batch cancellation — 2026-10-01

- Adds cooperative cancellation to `cleanroomx.project_batch.run_project_file()` through an optional caller callback checked only between analyses.
- Adds `cleanroomx-project-run --cancel-file PATH` so external automation can request a clean stop by creating a sentinel file without interrupting an active solver call.
- Records cancellation state, boundary, and associated analysis id in schema-v2 strict-JSON and Markdown batch reports; exit code 4 distinguishes clean cancellation when no execution error or source-integrity failure takes precedence.
- Preserves deterministic project order, exact source-revision checks, completed-run provenance, solver behavior, engineering tolerances, and project schema.

## Unreleased Release 3 — CI and installed operator-surface gate — 2026-10-01

- Adds a focused Release 3 regression gate for persisted project requirements, requirement-evidence mappings, canonical requirements verification/workflow, guarded verification persistence, verification currency, project-native dossier output, project verification CLI, and verification-history CLI.
- Extends clean-wheel installation checks to import and expose the Release 3 `cleanroomx-project-dossier`, `cleanroomx-project-verify`, and `cleanroomx-verification-history` entry points on every supported Python matrix job.
- Keeps the complete suite as the final correctness authority while making Release 3 traceability/operator regressions visible as an independent release gate.

## Unreleased Release 3 — desktop requirements traceability — 2026-10-01

- Adds **Analysis → Requirements Traceability...** as a dedicated read-only desktop inspection surface for persisted project requirements and requirement-to-analysis evidence mappings.
- Reuses the canonical Release 3 requirements and mapping parsers and cross-validates active mappings against the current project analysis collection before display.
- Shows registry SHA-256 identities, deterministic counts, requirement lifecycle/applicability/scope/criteria, mapping status/subject, resolved analysis identity, and exact result paths.
- Preserves historical disabled/superseded mapping references as traceability context instead of silently rebinding them.
- Changes no solver equation, acceptance comparison, requirement criterion, mapping registry, project schema, or persisted evidence.

## Unreleased Release 3 — persisted verification status gate — 2026-10-01

- Adds `cleanroomx-project-verify status <project> <analysis-id>` for read-only CI/release gating on retained canonical verification evidence.
- Returns exit code 0 only when the latest retained verification is both current against the present engineering configuration/dependency content and a canonical verified PASS.
- Separates verification currency from the historical verdict in strict JSON so a current FAIL and a stale historical PASS both fail closed for automation.
- Rechecks project-file stability across inspection and reuses the existing verification-currency/dependency-fingerprint authority without re-running solvers or mutating evidence.

## Unreleased Release 3 — diagnostics verification currency context — 2026-10-01

- Adds an explicit **Current verification currency** section to project-diagnostics Markdown output.
- Keeps immutable historical verification status separate from current/stale/dependency-freshness-unverifiable/not-verified/not-configured state.
- Shows per-analysis mismatch reasons and the latest retained verification sequence without rewriting historical evidence.
- Reuses the canonical verification-currency authority and changes no solver equations, requirement verdict semantics, persisted records, or project schema.


## Unreleased Release 3 — truthful current dependency currency explanation — 2026-10-01

- Corrects the canonical verification-currency explanation for file-backed analyses whose persisted dependency fingerprints still match current content.
- Keeps the existing fail-closed current/stale/unverifiable state semantics unchanged while ensuring operator-facing provenance text never claims that verified file-backed analyses have no external dependencies.


## Unreleased Release 3 — desktop verification history currency context — 2026-10-01

- Separates immutable historical verification status from present verification currency in **Analysis → Verification History...**.
- Applies canonical current/stale/dependency-freshness-unverifiable state only to each analysis's latest retained record; older rows are explicitly labeled `historical`.
- Labels retained records for analyses no longer present in the current project as `not_in_current_project` instead of implying current applicability.
- Reuses saved-project base-directory dependency checks and changes no solver equations, requirement verdicts, persisted verification records, or project schema.


## Unreleased Release 3 — dossier verification currency context — 2026-10-01

- Separates each project-dossier latest retained verification's historical PASS/FAIL status from its present verification-currency assessment.
- Attaches the canonical current/stale/dependency-freshness-unverifiable assessment to the corresponding retained record summary without rewriting historical evidence.
- Shows current currency and explicit mismatch reasons in the review-oriented Markdown table so a historical PASS cannot be mistaken for proof of the current edited configuration.
- Reuses the existing verification-currency authority and changes no solver equations, requirements comparison semantics, persisted ledger records, or project schema.


## Unreleased Release 3 — persisted verification dependency fingerprints — 2026-10-01

- Persists stable external engineering dependency fingerprints from execution provenance into new project-verification ledger records.
- Extends verification engineering identity to bind retained dependency fingerprints while remaining backward-compatible with legacy records that omit the optional field.
- Rechecks file-backed dependency SHA-256 and byte size during verification-currency assessment when the project base directory is known.
- Allows matching file-backed verification to be proven current; a proven content mismatch makes verification stale, while unavailable, unstable, unresolved, or legacy dependency evidence remains explicitly freshness-unverifiable.
- Reuses the existing immutable dependency-snapshot/provenance authority and does not change solver equations, requirement comparison semantics, or project file schema.


## Unreleased Release 3 — desktop project requirements verification — 2026-10-01

- Adds **Analysis → Verify Project Requirements** for read-only execution of the canonical saved-project requirements workflow.
- Adds **Analysis → Verify & Persist Project Requirements** for guarded persistence of PASS, FAIL, or incomplete canonical verification evidence.
- Adds **Analysis → Verification History...** with validated retained-ledger review and complete record inspection.
- Blocks desktop verification for unsaved projects, unsaved edits, unavailable saved-revision identity, or external on-disk changes.
- Reloads the committed project after verification persistence so desktop state, project revision identity, autosave, and history views remain synchronized with disk.

## Unreleased Release 3 — verification currency — 2026-10-01

- Adds a deterministic, fail-closed assessment of whether retained canonical project-requirements verification still matches the current analysis input, requirements, mappings, and active mapping identities.
- Exposes the canonical analysis-input SHA-256 and declared external-dependency introspection already used by execution provenance.
- Reports matching file-backed verification as `dependency_freshness_unverifiable` under schema-v1 rather than assuming external files are unchanged.
- Integrates verification currency into project diagnostics, verification-history inspection, and the project-native engineering dossier.
- Adds actionable stale/unverifiable diagnostics without changing solver equations, numerical tolerances, requirement verdict semantics, or persisted verification history.


## Unreleased Release 3 — project verification operator CLI — 2026-10-01

- Adds `cleanroomx-project-verify run` for read-only execution of the canonical saved-project requirements → evidence → verification → ProofGraph workflow.
- Adds `cleanroomx-project-verify persist` to run the same workflow and append the canonical result to the guarded tamper-evident project verification ledger.
- Uses exit code 0 only for verified PASS, 1 for successfully executed adverse/incomplete verification, and 2 for operational or integrity failures.
- Protects read-only workflow artifact publication against project/dependency overwrite and rejects publication if the exact verified project revision has changed.
- Preserves failed and incomplete verification as valid historical audit evidence when the operator chooses `persist`.


## Unreleased Release 3 — desktop project dossier export — 2026-10-01

- Adds **File → Export Project Engineering Dossier...** to the desktop application.
- Requires an explicitly saved, clean project so the exported artifact is bound to exact source bytes rather than unsaved editor state.
- Refuses externally changed source projects and protects both the project source and registered external engineering dependencies from report overwrite.
- Supports complete strict-JSON dossier export and review-oriented Markdown export while preserving the existing canonical dossier SHA-256.


## Unreleased Release 3 — project-native engineering dossier — 2026-10-01

- Adds a deterministic project-native dossier that projects canonical analysis definitions, first-class requirements, explicit requirement-evidence mappings, retained immutable analysis runs, persisted canonical verification runs, and project diagnostics into one evidence artifact.
- Binds every dossier to the exact saved source-project SHA-256 and adds an independent canonical dossier SHA-256.
- Adds `cleanroomx-project-dossier` with strict JSON and Markdown output plus guarded atomic report publication.
- Preserves historical verification semantics: a retained verification record remains bound to its own recorded source revision and is never silently reclassified as verification of later project edits.
- Reuses the existing project-loader, run-ledger, verification-ledger, diagnostics, and output-safety authorities; no solver equation or requirement acceptance rule changes.


## Unreleased Release 3 — verification history operator interface — 2026-10-01

- Adds `cleanroomx-verification-history list/show` for stable, read-only inspection of persisted canonical verification evidence.
- Binds inspection output to a stable source-file revision and emits strict JSON only after the project remains unchanged across the inspection.
- Adds compact ledger and latest-per-analysis verification summaries to project diagnostics and Markdown reports without reinterpreting historical evidence as current certification.
- Keeps solver equations, requirement acceptance semantics, persistence format, and historical verification records unchanged.


## Unreleased Release 3 — persisted canonical verification runs — 2026-10-01

- Adds a bounded integrity-chained project verification history separate from solver analysis run history.
- Persists exact source-project revision, immutable analysis bundle identity, analysis input identity, normalized requirements/mappings digests, exact evidence locators, canonical evidence, full canonical verification findings/completeness, ProofGraph identities, verifier implementation identity, CleanroomX version, runtime environment, and code revision provenance.
- Adds a deterministic verification engineering identity that excludes wall-clock completion time and ledger position while the storage record remains independently chain-hashed.
- Persists only when the saved project still matches the exact revision used by the workflow and saves through the existing optimistic guarded project-write boundary.
- Re-runs the canonical requirements verifier and ProofGraph projection before persistence; historical verification records are append-only and never silently rebound to a newer project revision.
- Validates the verification ledger during canonical project load/save and fails closed on evidence, digest, identity, or chain tampering.


## Unreleased Release 3 — project-native requirements execution — 2026-10-01

- Adds a direct saved-project orchestration path from one selected project analysis through immutable execution, persisted explicit evidence mappings, canonical requirements verification, and ProofGraph.
- Binds every workflow run to the exact loaded project SHA-256 and rechecks the source before and after analysis execution; source mutation prevents verification output.
- Consumes the canonical persisted requirements and requirement-evidence mapping registries instead of requiring transient caller assembly.
- Preserves the existing requirements verifier as the only comparison authority and the existing ProofGraph adapter as a projection of canonical findings.
- Keeps missing mapped results fail-closed as incomplete/not-checked evidence rather than PASS.
- Adds a deterministic workflow identity derived from project revision, normalized requirements/mappings, immutable run identity, canonical verification identity, and ProofGraph identity.


## Unreleased Release 3 — persisted requirement evidence mappings — 2026-10-01

- Adds a strict, versioned project-owned requirement-to-analysis evidence mapping registry under `project.metadata.requirement_evidence_mappings`.
- Persists explicit requirement ID, analysis ID, expected analysis kind, subject/entity scope, engineering property, exact result path, unit, evidence labels, lifecycle status, and notes without inferring solver semantics.
- Canonicalizes mappings deterministically and binds normalized content to `mappings_sha256`.
- Rejects duplicate IDs, ambiguous active requirement/subject bindings, malformed result paths, unknown fields, digest tampering, missing active requirement/analysis targets, analysis-kind mismatches, and invalid scope bindings.
- Integrates mapping normalization and cross-reference validation into the canonical project load/save boundary while preserving disabled/superseded historical references.
- Does not add a second requirements verifier, unit-conversion path, standards criteria, or compliance claim.


## Unreleased Release 3 — immutable analysis evidence binding — 2026-10-01

- Connects integrity-verified immutable CleanroomX analysis-run bundles to the canonical project requirements verifier through explicit result mappings.
- Derives requirement-evidence freshness from the exact current analysis input plus live content verification of the immutable run's recorded external dependencies instead of accepting a free-form current/stale assertion; the producing project SHA-256 remains provenance only.
- Adds exact escaped result locators to canonical requirement evidence and carries those locators into ProofGraph provenance.
- Rejects tampered run bundles, invalid project revision identities, duplicate mapping IDs, and non-scalar mapped results; missing result paths remain explicit incomplete evidence rather than PASS.
- Adds a direct immutable-analysis -> requirement verification -> ProofGraph workflow without duplicating comparison semantics.
- Adds regressions for current/stale/unknown freshness, changed inputs, unstable dependencies, integrity tampering, missing/non-scalar results, deterministic mapping order, locator escaping, and end-to-end ProofGraph provenance.

## Unreleased Release 3 — project requirements to ProofGraph — 2026-10-01

- Adds a deterministic adapter from the canonical project requirements verifier into the existing ProofGraph schema instead of creating a parallel evidence or comparison model.
- Emits one ProofGraph per non-empty persisted requirement set and preserves stable requirement identity, explicit criteria, source revision, lifecycle/applicability, evidence provenance, project/evidence/verification digests, and canonical source states.
- Maps PASS/FAIL directly, maps explicit inactive/not-applicable/not-checked states to NOT_CHECKED, and maps stale/incomplete/invalid evidence to UNKNOWN without promoting unresolved evidence to PASS.
- Preserves native single evidence lifecycle kinds where unambiguous and uses neutral declared evidence for aggregate or unsupported labels rather than fabricating design/calculation/commissioning provenance.
- Adds deterministic and strict-parser round-trip regressions for verified, stale, inactive, not-applicable, multi-set, multi-kind, missing-value, and empty-set cases.

## Unreleased Release 3 — canonical project requirements verification — 2026-10-01

- Adds the first canonical requirements -> evidence -> verdict engine over the persisted project requirements registry.
- Requires an approved active requirement, explicit applicability, one unambiguous evidence binding per requirement/entity, current freshness, required evidence kinds, exact unit agreement, and an explicit acceptance criterion before a PASS can be issued.
- Treats draft requirements as incomplete, superseded/withdrawn requirements as explicit inactive records, and duplicate evidence IDs as invalid audit identity rather than silently selecting or aliasing evidence.
- Reuses the established CleanroomX aggregate truth model while surfacing richer per-finding states for stale, incomplete, invalid, and not-applicable evidence.
- Adds deterministic requirements/evidence/result SHA-256 identities and order-independent evidence normalization.
- Adds fail-closed regressions for tolerance boundaries, missing/stale evidence, unit mismatch, ambiguous bindings, unresolved applicability, absent criteria, project-scope binding, and numeric canonicalization.

## Unreleased Release 3 — first-class project requirements registry — 2026-10-01

- Adds a strict, versioned project-owned requirements registry under `project.metadata.requirements` without changing the existing project schema version.
- Captures stable requirement identity, discipline/category, versioned source/reference, unit/criteria/tolerance, applicability, entity scope, verification method, required evidence, lifecycle status, assumptions, and notes.
- Enforces project-wide unique requirement IDs, finite numeric criteria, ordered bounds, non-negative tolerances, unambiguous target-vs-bound criteria, strict unknown-field rejection, and explicit applicability/lifecycle vocabularies.
- Canonicalizes requirement sets and requirements by stable ID and binds the normalized registry to a deterministic SHA-256 digest; supplied digest mismatches fail closed on project load/save.
- Keeps existing design-requirements, solver, compliance, and ProofGraph calculation semantics unchanged; the persisted registry is the Release 3 project authority for later requirements -> evidence -> verdict integration.

## Unreleased cross-study numerical integrity — full-precision standalone fan consistency — 2026-09-30

- Recomputes dossier-owned standalone fan/system operating points through the canonical full-precision solver state when evaluating HVAC/fan airflow consistency.
- Prevents the public three-decimal fan operating airflow from changing a fine user-supplied tolerance-boundary match/mismatch decision while preserving the public fan result schema.
- Adds a regression where the canonical fan root is 1000.00055 m³/h but the displayed value is 1000.001 m³/h, proving the consistency verdict follows engineering state rather than presentation rounding.

## Unreleased damper numerical integrity — full-precision redistribution metrics — 2026-09-30

- Computes damper-case edge airflow deltas and percent changes from canonical full-precision loop-network state instead of subtracting rounded public edge flows.
- Reuses each baseline and case calculation for both engineering metrics and terminal public formatting, avoiding duplicate solves and preserving the existing result schema.
- Adds a solver-tolerance-robust regression that deterministically finds a sub-display case where subtracting rounded edge flows disagrees with rounding the canonical airflow change.

## Unreleased fan/loop numerical integrity — canonical reference and uncertainty state — 2026-09-30

- Derives two-terminal equivalent loop resistance from full-precision reference node pressures instead of the rounded public loop-network result.
- Exposes one internal fan/loop calculation layer so public formatting remains a terminal boundary while downstream uncertainty analysis reuses canonical operating-point and edge-flow state.
- Builds fan/loop uncertainty envelopes from full-precision corner calculations and rounds only the final presented bounds; adds regressions for reference-pressure and operating-root precision boundaries.

## Unreleased ProofGraph thermal numerical integrity — full-precision evidence — 2026-09-30

- Separates canonical full-precision thermal uncertainty calculations from the rounded presentation payload.
- Stores those canonical load, airflow, cooling, and heating intervals in ProofGraph calculation evidence and finding actual/delta fields.
- Adds a sub-display-resolution capacity boundary regression proving that a FAIL verdict remains reproducible from evidence even when the standalone report rounds the displayed upper bound.

## Unreleased BIM import safety — bounded native IFC source size — 2026-09-30

- Rejects native IFC source files larger than 512 MiB before IfcOpenShell parsing and re-enforces the ceiling while streaming source SHA-256 provenance.
- Prevents a growing or unexpectedly giant IFC input from consuming unbounded hashing/parser resources while preserving the existing before/after source-stability digest guard.
- Adds focused rejection coverage and documentation without changing IFC semantic mapping, project schemas, solver equations, or engineering acceptance criteria.

## Unreleased fan/loop numerical integrity — full-precision operating root — 2026-09-30

- Carries the bounded fan/system operating-point root at full precision into the downstream loop-network solve instead of reusing the rounded public airflow value.
- Computes the fan-minus-system pressure check from the full-precision fan pressure and equivalent-system pressure, preventing presentation rounding from creating a false residual.
- Keeps the public result schema and display precision unchanged; adds a focused regression at a non-round operating point and documents the calculation/presentation boundary.

## Unreleased pressure-design numerical integrity — full-precision verdicts — 2026-09-30

- Uses full-precision pressure-network node state for mapped design-pressure requirement comparisons instead of reusing the nine-decimal public node display.
- Keeps the public pressure-network result schema and formatting unchanged while preventing presentation rounding from changing pass/fail at explicit fine tolerances.
- Adds a sub-display-resolution regression and documents the calculation/presentation boundary.

## Unreleased loop numerical integrity — full-precision variable-friction feedback — 2026-09-30

- Separates the loop-network full-precision calculation state from public result formatting without changing the public solver schema.
- Feeds exact solved edge airflows into variable-friction near-zero classification, Reynolds evaluation, Darcy friction updates, and resistance closure instead of reusing six-decimal presentation airflow.
- Adds a threshold-boundary regression where 100.0000004 m³/h must remain above a configured 100.0 m³/h freeze threshold even though its displayed airflow is 100.0 m³/h.

## Unreleased fan-network numerical integrity — full-precision composition — 2026-09-30

- Carries the full-precision bounded fan operating point into passive parallel-network redistribution and system-pressure checks.
- Prevents the public three-decimal fan airflow and rounded network pressure from becoming downstream engineering inputs.
- Adds a rounding-boundary regression without changing equations, units, schemas, fan-curve interpolation, or public result formatting.

## Unreleased ProofGraph integrity — globally unique provenance IDs — 2026-09-30

- Rejects reuse of one provenance-record ID across separate evidence records, removing ambiguity from graph-wide audit identity.
- Preserves valid distinct provenance records, provenance DAG semantics, and current adapter-generated IDs with linear validation over provenance records.
- Adds focused strict-parser success/failure regressions and documentation without changing schemas, solver equations, numerical tolerances, persistence formats, or requirement criteria.

## Unreleased cross-study numerical integrity — full-precision HVAC/fan consistency — 2026-09-30

- Uses the source HVAC project to recompute canonical aggregate governing airflow at full precision when the engineering dossier evaluates HVAC/fan operating-airflow consistency.
- Prevents the public three-decimal HVAC presentation total from changing a user-supplied tolerance-boundary match/mismatch decision.
- Preserves the existing public HVAC result shape, fan-study result shapes, equations, units, tolerance semantics, and dossier schema; adds a focused rounding-boundary regression.

## Unreleased ProofGraph integrity — verification-run completeness — 2026-09-30

- Rejects verification runs that declare checks with no verdict outcome, preventing silent unevaluated checks from appearing inside an otherwise auditable run.
- Preserves explicit `not_checked` results as valid outcomes; every declared run check must be represented by at least one referenced verdict.
- Adds strict-parser regression coverage and documentation without changing schemas, solver equations, requirement criteria, numerical tolerances, or persistence formats.

## Unreleased recovery integrity — strict editor-draft comparison — 2026-09-30

- Routes preserved crash-recovery editor drafts through the canonical strict JSON parser during semantic source comparison.
- Treats legacy duplicate-key drafts as invalid recovery evidence instead of silently applying JSON last-key-wins behavior, even when an old artifact carries `editor_json_valid=true`.
- Preserves the raw recovery artifact and existing invalid/incomplete operator semantics; no solver, schema, project-save, or automatic-restore behavior changes.

## Unreleased ProofGraph integrity — PASS required-evidence closure — 2026-09-30

- Rejects PASS findings that do not reference at least one evidence record for every kind declared by their compliance check's `required_evidence_kinds`.
- Keeps incomplete evidence representable for FAIL, WARNING, UNKNOWN, INDETERMINATE, and NOT_CHECKED findings instead of turning absence into success or a structural parse failure.
- Adds focused strict-parser regressions and documentation without changing schemas, solver equations, numerical tolerances, persistence formats, or acceptance criteria.

## Unreleased thermal uncertainty numerical integrity — full-precision governing airflow — 2026-09-30

- Keeps sensible-load airflow interval values at full precision while selecting the governing airflow candidate and conservative lower/upper bounds.
- Applies six-decimal rounding only when formatting the returned thermal-airflow interval, preventing presentation rounding from changing the reported governing basis.
- Adds a boundary regression where a rounded tie previously selected the wrong nominal airflow basis; no equations, units, capacity criteria, or uncertainty semantics change.

## Unreleased ProofGraph integrity — evidence-backed PASS — 2026-09-30

- Rejects PASS findings that declare evidence absent or reference no evidence, preventing absence of evidence from being serialized as successful compliance.
- Preserves FAIL, WARNING, UNKNOWN, INDETERMINATE, and NOT_CHECKED missing-evidence semantics for workflows that intentionally report incomplete or unavailable evidence.
- Adds focused model regressions and documentation without changing schemas, solver equations, requirement criteria, numerical tolerances, or persistence formats.

## Unreleased ProofGraph integrity — single-finding verdict status — 2026-09-30

- Rejects a verdict whose status disagrees with its sole referenced finding, preventing contradictory compliance state from being serialized as one auditable result.
- Leaves multi-finding aggregation semantics unchanged until an explicit aggregation policy is defined.
- Adds strict-parser regression coverage and documentation without changing schemas, solver equations, requirement criteria, numerical tolerances, or persistence formats.

## Unreleased ProofGraph integrity — explicit project identity — 2026-09-30

- Rejects a ProofGraph that combines evidence carrying different explicit `project_id` values, preventing cross-project evidence contamination from being serialized as one auditable graph.
- Keeps evidence without an explicit project identity compatible for source adapters that do not yet provide one.
- Adds strict-parser regression coverage and documentation without changing schemas, solver equations, requirement criteria, numerical tolerances, or persistence formats.

## Unreleased ProofGraph scalability — iterative provenance-cycle validation — 2026-09-30

- Replaces recursive provenance-cycle DFS with a deterministic explicit-stack traversal.
- Preserves readable cycle-path rejection while allowing deep valid provenance chains beyond Python's recursion depth.
- Adds a 1,200-link acyclic provenance regression without changing schemas, solver equations, requirement criteria, numerical tolerances, or persistence formats.

## Unreleased ProofGraph integrity — verification-run closure — 2026-09-30

- Rejects verification runs whose declared verdicts depend on findings from checks that are not listed in the same run.
- Keeps extra explicitly executed checks valid while preventing hidden out-of-run check dependencies from entering run-level audit evidence.
- Adds regression coverage and documentation without changing schemas, solver equations, requirement criteria, numerical tolerances, or persistence formats.

## Unreleased ProofGraph integrity — acyclic evidence provenance — 2026-09-30

- Rejects multi-evidence provenance dependency cycles such as `A -> B -> A` in addition to existing direct self-reference protection.
- Uses deterministic traversal and cycle diagnostics so malformed graphs fail closed reproducibly.
- Adds regression coverage and documentation without changing schemas, solver equations, requirement criteria, numerical tolerances, or persistence formats.

## Unreleased ProofGraph integrity — semantic cross-reference validation — 2026-09-30

- Rejects findings whose requirement identity disagrees with the referenced compliance check.
- Rejects finding evidence that was not declared by the referenced check, preventing hidden evidence links from bypassing the check record.
- Rejects verdicts that reference findings belonging to another requirement.
- Adds strict-parser regressions for each inconsistent graph shape without changing solver equations, requirement criteria, numerical tolerances, or project persistence schemas.

## Unreleased ProofGraph semantics — preserve canonical not-checked state — 2026-09-30

- Stops collapsing canonical `not_checked` results into ProofGraph `unknown` in the compliance-rule-pack and pressure-design-consistency adapters.
- Preserves missing rule-pack evidence and explicitly optional unmapped pressure targets as `not_checked`, including strict ProofGraph serialization round trips.
- Keeps `unknown` distinct for cases where CleanroomX cannot issue a verified verdict from the available evidence/provenance, and keeps `indeterminate` distinct for evaluated uncertainty intervals that overlap a decision boundary.
- Updates ProofGraph and pressure-consistency documentation without changing solver equations, numerical tolerances, persisted project schemas, or source-service acceptance semantics.

## Unreleased ProofGraph integration — thermal uncertainty capacity evidence — 2026-09-29

- Bridges canonical thermal uncertainty analysis into ProofGraph without duplicating psychrometric, load, airflow, or capacity equations.
- Creates cooling/heating capacity requirements only for explicitly configured available capacities; missing capacity is not invented as a requirement.
- Preserves conservative nominal/lower/upper capacity intervals, direct upstream evidence dependencies, deterministic source revisions, and originating-calculation identity.
- Extends ProofGraph's explicit verdict vocabulary with `indeterminate` and `not_checked`, preserving overlap and non-evaluation states instead of collapsing them into PASS/FAIL.
- Retains user-supplied input provenance, exposes missing provenance through verification metadata, and avoids manufactured confidence scores.
- Fails closed to `unknown` when canonical thermal inputs lack provenance while retaining the underlying thermal status in verification metadata.
- Adds pass/fail/indeterminate, heating-only, missing-requirement, provenance-gap, strict round-trip, and determinism regressions.

## Unreleased ProofGraph integration — airflow-balance evidence chain — 2026-09-29

- Bridges the canonical steady-state room airflow-balance calculation into ProofGraph without introducing a duplicate balance equation.
- Preserves explicit supply, return, exhaust, transfer-in, transfer-out, and minimum-surplus design inputs plus calculated net surplus and signed surplus margin.
- Adds explicit upstream evidence dependencies from flow inputs to net surplus and from net surplus/minimum surplus to the final margin.
- Preserves the canonical minimum-surplus PASS/FAIL result and explicitly records that the airflow-balance calculation does not calculate room pressure or invent unmodeled leakage.
- Adds focused pass/fail, dependency, no-pressure-claim, strict round-trip, and determinism regressions.

## Unreleased ProofGraph integration — ACH design evidence chain — 2026-09-29

- Bridges configured project minimum-ACH requirements into ProofGraph without adding a second airflow or ACH solver.
- Reuses the canonical preliminary air-system design for governing supply airflow and the canonical room verification path for room volume, nominal supply ACH, and exact minimum-ACH pass/fail semantics.
- Records requirement origin, room dimensions, room volume, governing supply airflow, calculated ACH, deterministic source revisions, and explicit upstream evidence dependencies.
- Fails closed to UNKNOWN when the matching air-system room is absent or canonical design-consistency does not establish matching room geometry; missing/ambiguous evidence is never promoted to PASS.
- Keeps design-consistency input tolerances separate from ACH compliance semantics and adds focused pass/fail/unknown, geometry-mismatch, strict round-trip, and determinism regressions.

## Unreleased ProofGraph integration — IFC/BIM design evidence — 2026-09-29

- Adds a dedicated IFC-to-ProofGraph bridge that revalidates normalized IFC semantics and optional semantic SHA-256 identity before emitting design evidence.
- Binds IFC evidence to the original source filename/SHA-256, normalized semantic SHA-256, IFC GlobalId, exact semantic field, and deterministic evidence identity.
- Preserves per-space dimension provenance so explicit IFC quantities and verified IfcOpenShell geometry fallback remain distinguishable in ProofGraph.
- Carries storey identity, spatial containment links, device orientation, coordinates, classification, and explicit CleanroomX space metadata as evidence without inventing compliance requirements.
- Adds immutable evidence attachment to an existing ProofGraph while preserving its requirement set, checks, findings, verdicts, actions, and verification runs.
- Adds strict digest-tamper, duplicate-attachment, round-trip, device/storey, and dimension-provenance regressions.

## Unreleased ProofGraph integration — pressure design evidence chain — 2026-09-29

- Bridges the canonical pressure-design-consistency workflow into ProofGraph without adding a second solver path.
- Records configured room pressure targets as DesignEvidence and solved signed node-to-reference differences as CalculationEvidence with separate deterministic source-revision digests.
- Preserves explicit room/node/reference mappings, absolute tolerance, expected/actual/delta values, design-requirement origin, and pressure-network calculation provenance.
- Preserves source semantics: required missing mappings remain FAIL, intentionally unchecked mappings become UNKNOWN, and rooms with no configured pressure target are never converted into invented requirements.
- Adds strict ProofGraph round-trip, failure, negative-pressure, missing-mapping, and determinism regressions plus documentation updates.

## Unreleased ProofGraph foundation — continuous compliance evidence model — 2026-09-29

- Adds GUI-independent typed ProofGraph domain records for requirements, evidence sources/layers, provenance, confidence/uncertainty, checks, findings, verdicts, corrective actions, and verification runs.
- Adds strict schema-v1 serialization/deserialization with deterministic whole-graph SHA-256 identity, finite-JSON validation, duplicate-ID rejection, and fail-closed cross-reference validation.
- Adds explicit design, calculation, simulation, commissioning, and operational evidence layers while retaining a neutral declared layer when the lifecycle source is not known.
- Bridges the existing deterministic compliance rule-pack engine into ProofGraph without changing its engineering semantics; missing rule-pack evidence maps to UNKNOWN and no evidence value is fabricated.
- Encodes the future corrective-action safety boundary by requiring user approval on every modeled action.
- Adds focused regression coverage and ProofGraph architecture documentation without changing GUI behavior, project persistence, standards limits, or existing solver equations.

## Unreleased BIM auditability — IFC space dimension provenance — 2026-09-29

- Records whether each natively extracted `IfcSpace` received Length/Width/Height from explicit IFC quantities (`ifc_quantities`) or the conservative IfcOpenShell rectangular-prism fallback (`ifcopenshell_geometry`).
- Preserves that optional provenance in normalized IFC semantics and semantic SHA-256 identity while keeping older integration records without the field valid.
- Makes a source-method change auditable as a semantic-only IFC re-import change when the resulting CleanroomX room geometry is otherwise unchanged.
- Rejects invented/unknown `dimension_source` values instead of silently accepting ambiguous provenance.
- Adds normalization, native extraction, and conflict-aware re-import regressions without changing spatial layout schema, solver equations, tolerances, or engineering acceptance semantics.
## Unreleased next-level BIM — standards-aligned IFC space geometry fallback — 2026-09-29

- Stops requiring non-standard \`Length\` and \`Width\` values to be present in \`Qto_SpaceBaseQuantities\` for every native \`IfcSpace\` import.
- Preserves the existing quantity path when positive Length / Width / Height values are explicitly supplied by the source.
- Falls back to IfcOpenShell world-space vertices when those quantities are incomplete and accepts only complete axis-aligned rectangular-prism geometry that the current room contract can represent exactly.
- Rejects rotated arbitrary-angle, tilted, incomplete, and non-rectangular geometry instead of converting it to a misleading generic bounding box.
- Adds helper- and extraction-level regression coverage without changing engineering solvers, project schema, numerical tolerances, or acceptance semantics.

## Unreleased next-level BIM — orthogonal IFC space footprint fidelity — 2026-09-29

- Preserves rectangular `IfcSpace` world-space footprints for 0°/90°/180°/270° plan rotations by transforming all four local rectangle corners.
- Correctly shifts the imported room origin to the world-space minimum corner and swaps length/width when a quarter-turn requires it.
- Rejects arbitrary-angle, tilted, reflected, or skewed `IfcSpace` placements instead of silently flattening them into misleading axis-aligned room geometry.
- Adds helper- and native-extraction regression coverage without changing engineering solvers, numerical tolerances, acceptance criteria, project schema, or analysis synchronization.


## Unreleased next-level BIM — generic IFC flow-terminal role safety — 2026-09-29

- Stops treating generic `IfcFlowTerminal` occurrences as supply-air devices.
- Maps generic flow terminals to equipment regardless of air-like free-text/predefined tokens; supply/return/exhaust classification remains limited to explicit `IfcAirTerminal` semantics.
- Native extraction requests direct `IfcFlowTerminal` occurrences without subtypes, preventing unrelated terminal families from being imported through the generic superclass query.
- Aligns the importer with buildingSMART's generic flow-terminal definition, which spans multiple distribution domains rather than HVAC supply only.
- Adds helper-level, layout-level, and native-extraction regressions without changing engineering solvers, numerical tolerances, acceptance criteria, or analysis synchronization.

## Unreleased next-level BIM — explicit IFC cleanroom semantics — 2026-09-29

- Reads the project-defined `CleanroomX_Space` IFC user property set on `IfcSpace` entities.
- Maps only `Classification` and `AnalysisRoomName` into existing CleanroomX room semantic fields.
- Keeps the mapping deliberately non-inferential: unrelated IFC property sets do not alter cleanroom classification or engineering inputs.
- Uses a user-defined property-set name without the buildingSMART-reserved `Pset_` prefix and supports type inheritance through IfcOpenShell.
- Adds focused malformed-payload and end-to-end extraction regressions without changing solver equations, tolerances, or acceptance semantics.


## Unreleased next-level BIM — IFC storey semantic fidelity — 2026-09-29

- Preserves explicit `IfcBuildingStorey` identity, name, and world-space elevation on normalized `IfcSpace` semantic records.
- Rejects conflicting name/elevation metadata for the same storey `GlobalId` instead of normalizing ambiguous provenance.
- Promotes the shared storey into CleanroomX floor metadata when every imported space belongs to the same IFC storey.
- Keeps multi-storey behavior conservative: room world elevations remain intact while the current single-floor UI does not fabricate multiple editable floor objects.
- Adds focused normalization, layout-mapping, and native-extraction regressions without changing engineering inputs, solver equations, tolerances, or acceptance semantics.


## Unreleased next-level BIM — IFC device orientation fidelity — 2026-09-29

- Preserves supported IFC device world-space plan orientation instead of defaulting every imported device to 0°.
- Derives yaw from IfcOpenShell's full nested local-placement transform, so parent rotations are reflected in CleanroomX `orientation_deg`.
- Rejects placements whose transformed local X axis has no usable XY projection rather than fabricating a plan orientation.
- Adds focused unit and extraction regressions without changing room geometry assumptions, engineering inputs, solver equations, tolerances, or acceptance semantics.


## Unreleased next-level BIM — IFC initial-import review integrity — 2026-09-29

- Adds a source-bound desktop preview before initial IFC mutation, showing the selected filename, extracted room/device counts, and source SHA-256.
- Requires explicit confirmation when establishing the first IFC identity baseline as well as when replacing an existing unlinked spatial layout.
- Re-extracts the selected IFC after confirmation and requires both source and semantic SHA-256 values to match the reviewed candidate before project mutation.
- Rejects provenance whose extracted source filename does not match the operator-selected file.
- Adds focused GUI regressions for preview-before-mutation, review-to-apply source drift, and selected-file provenance mismatch without changing engineering inputs or acceptance semantics.


## Unreleased next-level BIM — IFC placement and containment fidelity — 2026-09-29

- Uses IfcOpenShell's full nested local-placement transform for imported element origins instead of translation-only accumulation, preserving world-position coordinates across rotated parent placements.
- Resolves supported device-to-room links through explicit `IfcSpace` containment first and then IfcOpenShell's indirect spatial-container lookup, without geometric proximity inference.
- Validates the IFC length-unit scale and transformed coordinates as finite/positive inputs and fails closed when placement or containment resolution is invalid.
- Adds focused regressions for transformed coordinates, invalid placement values, indirect space containment, and direct-relation precedence.
- Keeps the CleanroomX room footprint axis-aligned and does not change IFC geometry semantics, engineering inputs, solver equations, tolerances, or acceptance criteria.


## Unreleased next-level BIM — IFC source stability — 2026-09-29

- Streams SHA-256 before and after native IFC semantic extraction and fails closed if the source changes or disappears while IfcOpenShell is reading it.
- Re-extracts a desktop re-import candidate after review/confirmation and requires both source and semantic digests to remain identical before project mutation.
- Adds focused regressions for stable extraction, extraction-time source drift, and review-to-apply source drift without changing IFC mapping or engineering semantics.

## Unreleased next-level BIM — desktop IFC review workflow — 2026-09-29

- Adds a dedicated BIM menu to the desktop application for initial IFC spatial import, read-only re-import review, and guarded application of conflict-free IFC revisions.
- Adds a per-entity review dialog showing IFC GlobalId, stable CleanroomX spatial identity, action classification, and local/source change state.
- Requires explicit confirmation before replacing an existing unlinked spatial layout and refuses to reset an established IFC identity baseline through the initial-import path.
- Keeps engineering inputs unsynchronized by default and leaves project persistence to the existing guarded Save workflow, preserving external-revision checks, save locking, revisions, autosave/recovery, and undo history.
- Adds focused regression coverage for initial import, explicit replacement consent, read-only conflict review, stable-identity re-import, and conflict-blocked application.

## Unreleased next-level BIM — conflict-aware IFC re-import — 2026-09-29

- Upgrades IFC link metadata to schema v2 with deterministic GlobalId-to-spatial-ID bindings, source-record digests, source-derived spatial-object digests, and a canonical binding-table SHA-256.
- Adds a read-only re-import planner that classifies unchanged, source-only, local-only, converged, added, removed, and conflicting IFC/spatial changes without mutating the project.
- Adds transactional re-import that preserves stable CleanroomX spatial IDs, keeps unbound local items, applies conflict-free source changes, and refuses two-sided conflicts or spatially invalid merged candidates.
- Keeps engineering solvers and analysis inputs untouched; IFC synchronization remains isolated to the existing spatial metadata boundary.
- Adds regression coverage for stable identity, local-edit preservation, source add/remove, transactional conflict handling, and binding tamper detection.

## Unreleased next-level Phase 1 — pressure evidence in design assurance — 2026-09-28

- Extends `design_assurance` with an optional canonical `pressure_design_consistency` component while keeping legacy assurance inputs/results unchanged when the field is absent.
- Aggregates explicit pressure pass/fail/not-checked findings into the assurance status and summary without inventing pressure mappings, reference rooms, tolerances, or standards criteria.
- Preserves the complete pressure-design result as an independent component and binds it into the traceability manifest with a deterministic normalized-result SHA-256.
- Makes design-assurance snapshots automatically freeze and replay the optional pressure component through their existing exact-source, result, traceability, and whole-snapshot digests; snapshot schema v1 remains unchanged.
- Adds focused regression coverage for successful aggregation, failure propagation, Markdown evidence, parser fail-closed behavior, and snapshot replay.

## Unreleased next-level Phase 1 — pressure design consistency — 2026-09-28

- Adds a deterministic read-only `pressure_design_consistency` workflow that composes the canonical design-requirements service with the canonical room pressure-network solver.
- Requires explicit room → pressure-node/reference-node mappings and compares the signed solved difference `pressure(node) - pressure(reference_node)` only against the configured room `pressure_target_pa`.
- Uses an explicit caller-supplied absolute pressure tolerance, preserves expected/actual/delta/unit/mapping/provenance evidence, and fails configured-but-unmapped pressure targets by default.
- Keeps the pressure network's own configured target checks as separate surfaced evidence instead of silently translating them into requirements semantics.
- Registers the workflow in the shared application/project execution boundary with a real example, full workflow-matrix coverage, focused regression tests, and dedicated documentation.
- Introduces no new pressure equation, leakage assumption, standards limit, project-schema change, certification semantics, or hidden reference-room inference.

## Unreleased next-level Phase 1 — design assurance snapshots — 2026-09-28

- Adds deterministic self-contained `cleanroomx.design-assurance-snapshot` artifacts that bind the exact UTF-8 source bytes, normalized design-assurance result, result SHA-256, traceability SHA-256, producing CleanroomX version, and a canonical whole-snapshot SHA-256.
- Adds independent snapshot verification that checks byte count/digest, embedded result digest, traceability linkage, whole-snapshot integrity, and deterministic replay through the canonical design-assurance parser/engine.
- Adds strict JSON, duplicate-key rejection, stable-file reads, 16 MiB source and 64 MiB snapshot limits, atomic output persistence, source/output alias protection, tamper regression coverage, and an installed `cleanroomx-assurance-snapshot` CLI.
- Keeps content digests explicitly separate from digital signatures or source-authenticity claims and introduces no engineering equation, standards limit, acceptance criterion, project-schema change, or certification semantics.

## Unreleased hardening — compliance JSON equality — 2026-09-28

- Makes `equals` and `one_of` use JSON-aware equality instead of Python container equality.
- Prevents boolean evidence from matching numeric criteria such as `true == 1` or nested boolean/number equivalents.
- Preserves normal JSON-number equivalence between integer and floating-point representations of the same value.
- Adds focused regression coverage and documents the comparison semantics.


## Unreleased next-level Phase 1 — design assurance matrix — 2026-09-28

- Adds a read-only `design_assurance` workflow that composes the canonical `design_consistency` result with one or more versioned `compliance_check` evaluations.
- Preserves complete component results plus compliance rule-pack identity, declared source, version, criteria SHA-256, exact supplied-evidence SHA-256, normalized component-result digests, and a deterministic traceability-manifest SHA-256 instead of flattening or reinterpreting evidence.
- Aggregates only explicit pass/fail/not-checked evidence into `pass`, `fail`, `not_checked`, or `pass_with_unchecked`; unresolved evidence is never promoted to a complete pass.
- Integrates through the shared application parser/runner/reporter boundary with a real example, focused regression coverage, full workflow-matrix coverage, and dedicated documentation.
- Introduces no new HVAC equations, standards limits, certification claims, implicit semantic mappings, project-schema changes, or engineering acceptance criteria.

## Unreleased next-level Phase 1 — design consistency — 2026-09-26

- Adds a deterministic read-only `design_consistency` workflow that composes the canonical design-requirements and preliminary air-system engines rather than introducing a competing room or calculation model.
- Cross-checks room-set identity, dimensions, minimum ACH, ACH-derived supply airflow, explicitly entered sensible load, and room-air temperature against the configured requirement range.
- Requires explicit absolute comparison tolerances, retains expected/actual/delta/unit/provenance evidence, and preserves missing requirement evidence as `not_checked` instead of promoting it to pass.
- Lists pressure, relative-humidity, recovery, filtration, contamination, operating-mode, and free-text strategy semantics as deliberately outside this cross-check instead of inventing mappings.
- Integrates through the existing application parser/runner/reporter boundary with a real example and focused regression coverage.
- Preserves project schema version 1, v0.102.1 release identity, existing solver equations/tolerances, and configured engineering acceptance criteria.

## Unreleased bounded project-file ingestion

- Caps normal CleanroomX project JSON at 64 MiB before parsing and revision hashing, with bounded reads that detect growth beyond the ceiling.
- Rejects invalid UTF-8 project bytes as project-format errors and refuses saves above the same limit.
- Uses the same project-size authority for portable-bundle project members while preserving the existing bundle archive/member resource limits.
- Bounds saved project-revision envelopes and embedded project bytes before expensive decoding/restoration.
- Preserves project schema version 1 and all engineering equations, tolerances, units, and configured acceptance semantics.

## Unreleased portable project-bundle resource hardening

- Bounds untrusted portable-bundle inspection and extraction with explicit archive, manifest, project-member, dependency-member/count, and aggregate-payload ceilings.
- Rejects oversized archive files before SHA-256 hashing and bounds member streaming so malformed inputs cannot silently expand beyond declared/accepted sizes during verification or extraction.
- Applies the same project/dependency/manifest limits to export, preventing CleanroomX from publishing a portable bundle that this build would reject on re-open.
- Preserves project schema version 1, bundle schema version 1, deterministic stored-ZIP format, solver behavior, and engineering acceptance semantics.

## Unreleased next-level Phase 1 — project diagnostics

- Adds a deterministic read-only project diagnostics service that composes existing spatial validation, analysis parser validation, persisted engineering synchronization state, and run-history/application provenance instead of duplicating those authorities.
- Reports structured severity, affected element, explanation, and corrective action for spatial conflicts, invalid analysis inputs, ambiguous analysis names, synchronization conflicts/staleness, never-run analyses, stale current inputs, stale external dependencies, and orphan run-history evidence.
- Adds `cleanroomx-project-check` with strict JSON or Markdown output, source-revision stability checks, actionable exit codes, and the shared fsync-backed atomic output path.
- Adds focused regression coverage plus installed-wheel CLI smoke coverage and `docs/PROJECT_DIAGNOSTICS.md`.
- Prevents `cleanroomx-project-check --output` from replacing the checked project or a declared external engineering dependency through the same path or an existing same-file alias.
- Preserves project schema version 1, v0.102.1 release identity, solver equations/tolerances, configured engineering acceptance semantics, and project Undo/Redo state because diagnostics are read-only.

## Unreleased next-level Phase 1 — design requirements and air-system design

- Adds a data-driven `design_requirements` workflow that preserves explicit room/profile provenance and derives floor area, volume, ACH-based airflow targets, and explicitly entered sensible-load totals without inventing standards requirements.
- Adds an `air_system_design` workflow that compares explicit ACH, sensible-load, and minimum-outdoor-air drivers, identifies the governing preliminary supply airflow, proposes return/makeup balance, and estimates capacity-based FFU/terminal counts from user-supplied equipment data.
- Registers both workflows through the same application parser/runner/reporter boundary already used by the room-pressure network and established CleanroomX analyses.
- Adds real example inputs, focused fail-closed/numerical tests, full application-catalog end-to-end coverage, Markdown reports, and `docs/DESIGN_FOUNDATION.md`.
- Preserves the v0.102.1 release identity, project schema version, existing spatial model, existing solver equations/tolerances, and prior engineering acceptance semantics.

## Unreleased next-level Phase 1 — room pressure network

- Adds a first-class steady-state multizone room pressure/leakage network with explicit fixed-pressure boundaries and mechanical supply/return/exhaust inputs.
- Supports user-parameterized power-law and orifice pressure paths for doors, windows, undercuts, transfer grilles, pass boxes, penetrations, cracks, intentional leakage, and generic openings.
- Solves unknown room pressures simultaneously with damped Newton iteration, reported convergence tolerance/iterations, fail-closed non-convergence, deterministic path flows, local dQ/dP sensitivity, dominant leakage-path evidence, and fixed-boundary balance flow.
- Adds explicit minimum/optional-maximum pressure-differential targets; target failures remain visible as `solved_with_target_violations` rather than being collapsed into a pass.
- Registers the workflow in the shared desktop application catalog and adds `cleanroomx-pressure-network`, strict JSON input parsing, Markdown reporting, a demonstration case, and focused deterministic regression coverage.
- Documents the NIST CONTAM / EnergyPlus multizone pressure-flow model basis while keeping every project-specific coefficient, opening area, discharge coefficient, pressure offset, airflow, and acceptance target as explicit user input.
- Does not modify the validated v0.102.1 room-verification, HVAC, duct, fan/network, uncertainty, persistence, spatial, or provenance equations.

## v0.102.1 final spatial production closure — 2026-09-25

- Makes snapped 2D drag translation deterministic from immutable gesture-start coordinates and suppresses no-op drag persistence/history/autosave churn.
- Finalizes the post-v0.102 synchronized spatial workspace without moving the published `v0.102.0` tag.
- Keeps spatial-to-engineering synchronization strictly dimension-only, so spatial pressure never overwrites engineering `observed_pressure_pa` evidence.
- Adds explicit engineering-to-spatial **dimension-only** pull with complete mapping/value preflight and persisted synchronization provenance.
- Projects fresh completed verification pressure evidence into the 2D/3D view without persisting it into geometry; explicit spatial pressure remains the fallback and missing evidence remains unavailable.
- Uses the same fresh-or-spatial pressure evidence for synchronized 2D/3D pressure-cascade visualization.
- Centralizes deterministic 2D/3D viewport transforms, adds exact 3D fit-to-view, explicit 2D reset, and Shift+left-drag 3D orbit, and strengthens the installed-demo smoke to prove rooms and pressure relationships render in both views.
- Makes **Fit** compute the 3D camera zoom and both pan axes from every room corner at its real floor and ceiling elevation, with deterministic regression coverage; PR #473 head `332eb07ed1d4d27a028d7fe8886b3914da29c8d7` passed CI #1552 / `36171783101` before merge.
- Adds windows and generic wall openings as first-class persisted spatial object types.
- Fixes the recovery autosave Future-completion race: a finished worker remains coordinator-owned until its completion callback finalizes state, stale callbacks cannot clear newer work, and `wait_for_idle()` requires no active, pending, or tracked request; PR #479 head `4a802f43be7bc891e2c4de90b631ddea7c1fa9e4` passed CI #1565 / `36184210616`.
- PR #467 head `4be4fb840480df7a5f1e0313a73830313150d9dd` passed CI #1540 / `36170548238`; PR #472 head `8a34c3d649aee54c377b4194a6d619559d219421` passed CI #1551 / `36171758793`.
- Preserves spatial X/Y placement during pulls, engineering ownership of pressure evidence, project schema version 1, solver equations, numerical tolerances, and engineering acceptance criteria.

## v0.102.0 synchronized spatial closure — 2026-09-25

- Publishes the completed Design 2D + 3D workspace from one canonical persisted spatial model while preserving the immutable `v0.101.0` tag.
- Adds deterministic room-level engineering synchronization states: synchronized, geometry newer, engineering newer, conflicting, and unmapped.
- Persists a minimal last-synchronized geometry/mapping baseline so "newer" is proven instead of inferred, validates that provenance at the project persistence boundary, and preflights project-verification mappings before any engineering input is mutated.
- Retains floor metadata, room elevation/classification/stable analysis links, door/transfer openings, device placement, resize/snap/nudge controls, deterministic metrics, pressure overlays, and the shared-model 3D view.
- Final synchronization PR #442 head `db9169555127b1799f261f31113d18cdaf2518ed` passed CI run #1503 with **985 passed** on Python 3.11/3.12/3.13, Windows launcher smoke, clean-wheel checks, and Python 3.13 Tk/Xvfb GUI smoke. The merged main commit `2c8d0696170080d5c333ff1fc809f671aec1ac1d` has the identical Git tree `af3c534599ee0921f8f21c8a14bd7b6b3e209258`.
- Changes no solver equation, numerical tolerance, no-extrapolation/root-selection rule, uncertainty semantic, project schema version, unit convention, or engineering acceptance criterion.

## v0.101.0 Release 2 closure — 2026-09-25

- Assigns a new package/release identity to the completed Release 2 tree instead of moving or rewriting the already-published `v0.100.0` tag.
- Consolidates the CI-green Release 2 work: durable project persistence/recovery/history, bounded undo-redo, plugin API v1, immutable analysis evidence and run history, dependency freshness, verified portable bundles/reports, deterministic project batch automation, strict engineering JSON ingestion, precision-safe composition, explicit verification completeness, Markdown boundary hardening, and numerical-integrity gates.
- Synchronizes package/runtime/demo/test/CI version metadata at `0.101.0`.
- Changes no solver equation, numerical tolerance, no-extrapolation/root-selection rule, uncertainty semantic, project schema version, or engineering acceptance criterion.
- Requires the normal Python 3.11/3.12/3.13 full CI matrix, installed-wheel checks, GUI/CLI smoke coverage, Release 2 gates, project-batch smoke, and strict-ingestion regressions before tagging.

## Unreleased strict engineering JSON ingestion — 2026-09-25

- Routes all public file-backed engineering JSON loaders and dossier manifests through the shared strict JSON parser.
- Rejects non-standard `NaN`, `Infinity`, and `-Infinity` constants before model construction or solver execution.
- Rejects duplicate JSON object keys at the same ingestion boundary instead of silently accepting the last occurrence.
- Preserves UTF-8 file reading, ordinary JSON syntax errors, solver equations, numerical tolerances, engineering acceptance semantics, project schema version 1, and existing finite standards-compliant inputs.
- Adds focused regression coverage across every migrated engineering loader plus dossier library/CLI ingestion.

## Unreleased deterministic project batch automation — 2026-09-25

- Adds `cleanroomx-project-run` and `cleanroomx.project_batch.run_project_file()` for headless execution of complete or selected saved-project analyses through the existing application service.
- Binds the batch to one exact project SHA-256/size revision, executes in deterministic persisted project order, and rechecks the source before and after every attempted analysis.
- Stops scheduling new analyses if the source changes; isolates ordinary per-analysis exceptions unless fail-fast is requested.
- Preserves each completed `AnalysisRun`, including canonical input and external-dependency provenance, and emits strict JSON or Markdown with atomic file output.
- Routes user-controlled Markdown labels, paths, and errors through the shared Markdown escaping boundary.
- Keeps engineering PASS/FAIL/indeterminate states as domain results rather than process exit semantics; no project schema, solver equation, tolerance, convergence rule, or unit convention changes.

## Unreleased verification outcome integrity — 2026-09-25

- Adds explicit aggregate `status` and `complete` fields to room and multi-room verification reports so `not_checked` evidence is no longer surfaced by the application as an ordinary pass.
- Uses deterministic four-state aggregation: `fail` if any finding fails, `pass_with_unchecked` when evaluated passing findings coexist with unchecked findings, `pass` only when all findings are evaluated and passing, and `not_checked` when nothing is evaluated.
- Preserves the existing `passed` property and verification CLI exit-code behavior as backward-compatible no-failure semantics; no engineering equation, tolerance, project schema, input format, or configured acceptance rule changes.
- Integrates through the existing application result-status path and fallback Markdown reporting.
- Adds focused aggregate, room, project, and application-path regression coverage.

## Unreleased precision-safe HVAC composition — 2026-09-25

- Keeps full floating-point precision through duct-path, fixed-demand branch-flow, room thermal/air-balance, project aggregation, supply-fan, and fan-curve duty decisions.
- Applies existing result rounding only at the presentation boundary, so near-ties and threshold decisions are not changed by display precision.
- Uses `math.fsum` for pressure-path, continuity, airflow, surplus, and capacity aggregation where composition is order-sensitive.
- Preserves existing result shapes, project schema, equations, tolerances, units, and dependencies.

## Unreleased protected legacy migration saves — 2026-09-25

- Adds explicit migration provenance for both supported legacy project shapes without changing existing loader return contracts.
- Opens migrated legacy files as visibly unsaved converted copies while preserving the original file as path context.
- Routes the first normal Save through Save As and refuses the original legacy source as that first destination, preventing destructive one-way replacement.
- Keeps the original source protected after cancelled or failed saves; protection clears only after a validated schema-v1 copy is committed elsewhere.
- Preserves project schema version 1, additive-field migration behavior, solver equations, tolerances, and engineering acceptance semantics.


## Unreleased lossless project extension round trips — 2026-09-25

- Preserves unrecognized additive strict-JSON fields at the project-document top level, nested project block, and individual analysis records across load/edit/save cycles.
- Keeps CleanroomX-owned schema/model fields authoritative when extension maps contain colliding reserved keys.
- Carries unconsumed additive fields through supported legacy migrations where their source scope has a lossless schema-v1 destination, without inventing semantics for pre-schema fields.
- Retains strict-JSON validation, so non-finite or non-serializable extension values cannot bypass project-save validation.
- Preserves project schema version 1, existing constructor compatibility, solver equations, numerical tolerances, and analysis semantics.


## Unreleased atomic CLI output persistence — 2026-09-25

- Routes all 23 file-producing CLI/report commands through the existing shared `atomic_write_text()` persistence primitive instead of truncating destinations in place with `Path.write_text()`.
- Stages each report in the destination directory, flushes and fsyncs it, then atomically replaces the destination; if staging or replacement fails, the previously valid report remains intact and temporary files are cleaned up.
- Leaves stdout behavior, report formats, project schema version 1, solver equations, numerical tolerances, and engineering acceptance semantics unchanged.
- Adds failure-injection coverage with an existing report plus a regression invariant preventing output-capable CLI modules from reintroducing direct in-place writes, and adds the new tests to the v0.100 application/desktop compatibility gate.

## Unreleased analysis result freshness guard — 2026-09-25

- Binds every cached desktop result to the canonical SHA-256 of the exact analysis input already recorded in application execution provenance.
- Revalidates analysis kind and input identity before cache restore, background-run acceptance, and result/run-bundle/report export.
- Discards stale results with an actionable rerun status instead of relying only on mutation-site cache invalidation.
- Preserves project schema version 1, solver equations, numerical tolerances, acceptance semantics, run-bundle fields, and existing immediate invalidation behavior.
- Adds application- and GUI-level regression coverage for canonical identity, missing provenance, stale cache restoration, mid-run mutation, and stale export rejection.

## Unreleased external analysis input stability — 2026-09-25

- Makes file-backed `consistency` and `dossier` runs fail closed when any referenced engineering input changes, disappears, or cannot be fingerprinted consistently during execution.
- Captures revision-stable SHA-256, byte-size, and nanosecond modification-time evidence before and after execution; hashing reads reject file-identity/size/mtime changes instead of accepting a torn fingerprint.
- Raises an actionable `ExternalDependencyChangedError` and discards the computed run, so the desktop cannot publish potentially mixed-revision evidence as a completed analysis.
- Preserves project schema version 1, solver equations, numerical tolerances, acceptance semantics, stable-file workflow behavior, and existing external-dependency provenance fields; timestamp fields are additive.
- Adds regression coverage for single/multiple dependency changes, disappearance during execution, deterministic reporting, and unchanged dependencies.

## Unreleased external project write protection — 2026-09-25

- Binds each opened project to the exact stable on-disk content revision that was parsed, retrying if the file changes during open.
- Protects explicit project saves with SHA-256 optimistic write checks before serialization and immediately before atomic replacement.
- Blocks silent overwrite when another CleanroomX session or external editor changes, deletes, replaces, or races to create the destination.
- Keeps the user's in-memory work available for Save As, and prevents same-path Save As from bypassing the guard.
- Preserves the low-latency recovery checkpoint workflow, project schema, engineering solver behavior, and the legacy unguarded persistence helper for non-GUI callers.

## Unreleased low-latency recovery checkpoints — 2026-09-25

- Adds an event-driven recovery checkpoint path for dirty project/editor/spatial changes, reducing the normal crash-recovery exposure window from the periodic autosave interval to a 1.5-second idle debounce.
- Coalesces rapid edits by cancelling and rescheduling the pending checkpoint instead of emitting a recovery artifact for every keystroke or drag event.
- Reuses the existing background autosave worker, snapshot validation, duplicate suppression, bounded history rotation, and source fingerprinting; explicit project files remain untouched.
- Keeps the periodic autosave timer as a fallback and preserves `--autosave-interval-seconds 0` as a complete recovery-autosave disable switch.
- Cancels pending debounced callbacks when a project is saved, discarded, switched, or rebound so stale callbacks cannot write recovery state for the wrong project identity.
- Adds focused scheduler/checkpoint/save-cancellation regressions without changing project schema, solver equations, numerical tolerances, or engineering acceptance semantics.

## Unreleased startup crash recovery — 2026-09-25

- Detects readable recovery artifacts during normal desktop startup and exposes them in a dedicated Recovery Center; headless checks and automated smoke runs remain non-interactive.
- Shows project identity, recovery timestamp, original-project comparison state, source path, recovered analyses, and the captured raw editor draft before restoration.
- Supports explicit inspect, restore, discard, and continue-without-restoring actions. Unreadable recovery artifacts are reported and preserved rather than silently deleted.
- Restores into a separate dirty **unsaved copy** that requires **Save Project As**. The original project path is retained only as read/context for relative engineering file references, is never rebound as the save destination, and is rejected as the first recovered Save-As target so both versions remain available.
- Preserves both versions when the original file changed or is newer; successful Save As writes a new explicit project first and only then removes the recovery artifact.
- Hardens discard operations so only validated recovery artifacts inside the configured recovery directory can be deleted.
- Adds focused restore/discard/source-preservation/startup-precedence regressions without changing project schema version, solver equations, tolerances, or engineering acceptance semantics.

## Unreleased semantic recovery comparison — 2026-09-25

- Adds a deterministic, read-only semantic comparison between each recovery artifact and the current source project before restoration.
- Reports changed project metadata, recovery-only/source-only analyses, modified analyses, active-analysis selection changes, and raw editor-draft divergence.
- Handles missing or invalid source files explicitly without guessing a merge result, mutating the source, or changing the recovery artifact.
- Surfaces the comparison in **Inspect recovery** so operators can understand the delta before choosing whether to restore an unsaved copy.
- Keeps recovery safety semantics unchanged: no automatic merge, source overwrite, solver change, tolerance change, or engineering acceptance change.

## Unreleased autosave and crash-recovery foundation — 2026-09-25

- Adds a dedicated recovery-autosave service that writes only separate recovery artifacts; it never overwrites the user's explicitly saved `.cleanroomx.json` file.
- Runs recovery writes on a bounded single-worker background executor, coalesces pending snapshots, skips identical snapshots, and rotates a per-project recovery history.
- Fingerprints the source project with SHA-256, size, and modification time so later recovery logic can distinguish unchanged, changed, missing, and newer source files without making an automatic overwrite decision.
- Captures unsaved project metadata and raw JSON-editor draft text, including malformed drafts that cannot yet be committed to the authoritative project model.
- Adds a dedicated desktop autosave status indicator and `--autosave-interval-seconds` configuration; `0` disables autosave.
- Preserves prior-session recovery artifacts during current-session save/discard cleanup and invalidates in-flight current-session writes when a project is explicitly saved, discarded, replaced, or closed.
- Adds focused autosave, recovery-scan, source-comparison, history-rotation, malformed-artifact, GUI draft-capture, and scheduler regressions without changing engineering solver equations or acceptance logic.

## Unreleased spatial transactional edit history — 2026-09-25

- Consolidates spatial room/device edits into the same bounded application-wide **Undo/Redo** transaction stream used for project and analysis edits; a complete drag gesture is coalesced into one transaction.
- Restores room/device selection with each edit while deliberately preserving the current 2D/3D camera state, so geometry undo does not rewind the operator's viewport.
- Clears redo history after divergent edits and resets history when the active project object is replaced, preventing edits from one project being replayed into another.
- Spatial toolbar controls and Ctrl+Z/Ctrl+Y/Ctrl+Shift+Z delegate to the single project transaction history; there is no independent spatial undo stack.
- Adds regression coverage for bounded history, no-op suppression, snapshot isolation, redo invalidation, model restoration, selection restoration, and viewport preservation.

## Unreleased spatial workspace safety pass — 2026-09-25

- Adds deterministic validation for overlapping rooms, duplicate room names, orphan/unassigned devices, devices outside their assigned room footprint, and device elevations outside room height.
- Surfaces validation state directly in the synchronized 2D/3D workspace with a **Validate** action, warning outlines, and explicit overlap markers.
- Keeps validation advisory: it does not change solver equations, engineering acceptance logic, or persisted analysis inputs unless the existing explicit synchronization action is used.
- Adds regression coverage for both warning detection and clean spatial layouts.

## Unreleased performance optimization — 2026-09-24

- Reuses an already canonicalized network-state projection when computing its SHA-256 fingerprint, removing duplicate sorting/normalization work from supplied-point checks, bisection trace capture/replay, and selected-state replay without changing canonical bytes or audit semantics.
- Pre-indexes solved edge airflow values once per uncertainty aggregation, reducing edge-range extraction from repeated per-edge scans to linear indexing across corners and edges.
- Adds regression coverage proving the projection-hash fast path is identical to the existing canonical network-state fingerprint.
- Does not change solver equations, tolerances, candidate selection, replay independence across audit layers, uncertainty semantics, or engineering acceptance behavior.

## v0.100.0 consolidated desktop release — 2026-09-24

- Continues from current v0.99.1 `main`, including installed-wheel verification and the self-contained `cleanroomx-gui --demo` package resources.
- Adds canonical application-input SHA-256 identity and before/after hash/size evidence for external consistency/dossier dependencies; Diagnostics and run-bundle export preserve the evidence.
- Preserves external-file referents when consistency/dossier JSON is imported or a project is relocated with **Save Project As**; absolute-only dossier inputs can run before a project is saved.
- Uses durable same-directory atomic writes for project files and GUI exports, with user-visible export failures.
- Plots backend-computed system-pressure samples beside supplied fan curves with labeled series.
- Keeps abandoned analyses exclusive until their backend worker exits, preserves registry fail-fast validation before Tk startup, and invalidates cached results when project path context changes.
- CI keeps the v0.91-v0.95 compatibility gates, adds focused v0.100 application/desktop regressions, runs the complete suite on Python 3.11/3.12/3.13, builds/installs a clean wheel in every job, and executes the installed Tk/Xvfb demo smoke on Python 3.13.
- No validated solver equations, numerical tolerances, no-extrapolation rules, uncertainty semantics, or engineering acceptance criteria are changed.

## v0.99.1 installed desktop hardening — 2026-09-24

- Continues directly from integrated v0.99.0 `main`; no divergent release branch is used as the baseline.
- Keeps an abandoned analysis exclusive until its backend worker exits, suppressing the abandoned result without allowing a second overlapping computation to start.
- Packages the GUI demonstration project and its relative consistency/dossier dependencies inside the installable wheel and adds `cleanroomx-gui --demo` for repository-independent launch.
- Adds regressions for abandoned-run exclusivity and packaged-demo execution.
- Builds and installs a clean wheel in every Python 3.11/3.12/3.13 CI job, validates the installed application/resources, and runs the Python 3.13 Tk/Xvfb smoke from the installed wheel.
- Synchronizes package/runtime/demo/CI metadata at v0.99.1 without changing validated engineering solver semantics.

## v0.99 application registry integrity — 2026-09-24

- Continues from the current integrated v0.98 `main` descendant of the verified clean v0.91 → v0.95 lineage; the divergent older version-named branches remain excluded.
- Hardens the desktop application registry from callable-resolution-only checking to structural integrity validation: duplicate analysis keys are rejected, ordinary analyses must declare parser+runner bindings, and `consistency`/`dossier` must remain registered custom adapters.
- Makes registry validation return auditable metadata (analysis count, resolved callable count, custom adapters, and fallback-reporter count) and exposes that evidence through `application_info()` and headless `cleanroomx-gui --check`.
- Adds regressions for duplicate-key rejection, custom-adapter contract enforcement, metadata consistency, and headless GUI exposure.
- Bumps package/runtime/demo metadata to v0.99.0 and synchronizes CI version assertions while retaining the complete Python 3.11/3.12/3.13 suite, provenance compatibility gates, CLI smokes, and real Tk/Xvfb GUI smoke.
- This gate validates software registry completeness and wiring only; it does not establish engineering certification, CFD validity, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.

## v0.98 release completion — 2026-09-24

- Continues from live v0.97 application-completeness head `9338acd2a4cca5d903ecf01c5ec0996a82f522e8` on the verified clean v0.91 ancestry; divergent version-named branches were not used as the implementation baseline.
- Bumps package/runtime/demo metadata to v0.98.0 and synchronizes CI version assertions.
- Adds application-registry self-validation so headless `cleanroomx-gui --check` resolves every declared parser, runner, and reporter binding before reporting readiness.
- Adds a window-title dirty marker for unsaved project/editor changes, including project metadata, analysis selection, input edits, imports, additions, renames, and removals.
- Retains strict JSON handling, per-analysis result sessions, active-run mutation guards, complete application-workflow regressions, project persistence tests, legacy solver/provenance compatibility gates, and real Xvfb desktop smoke.
- The desktop application remains engineering screening/numerical provenance software; it does not by itself establish certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.

## v0.97 application completeness and GUI lifecycle hardening — 2026-09-24

- Executes every workflow in the shared application catalog against repository examples, including consistency and engineering-dossier adapters.
- Hardens strict project/editor JSON handling, unsaved-change prompts, input preservation while switching analyses, active-run mutation guards, open-project error handling, and stale-result invalidation.
- Retains results per analysis so switching between completed analyses restores the matching result/report/diagnostics without associating output with a different input.
- Commits the loaded editor state during save operations even when the visible tree selection changes independently.
- Preserves the v0.91-v0.95 numerical/provenance compatibility gates and the v0.96 desktop architecture.

## v0.96 desktop application and project workflow — 2026-09-24

- Adds a shared application-service registry over the existing validated CleanroomX backend parsers, solvers, reporters, consistency checks, and engineering dossier workflow.
- Adds a stable versioned `cleanroomx.project` document with strict JSON serialization, atomic save/open, active-analysis tracking, unique analysis identifiers, and supported legacy single-analysis migration.
- Adds a real Tkinter desktop application for project and analysis management, structured JSON editing/inspection, validation, background execution, results, diagnostics, Markdown reports, fan-curve plotting, and JSON/Markdown export.
- Adds the installed `cleanroomx-gui` console entry point plus `--check` headless capability validation and `--smoke` real-window smoke execution.
- Adds an end-to-end demonstration project spanning facility verification, HVAC, fan operating point, nonlinear fan/variable-friction loop analysis, bounded uncertainty, consistency, and dossier workflows.
- Adds application/project/GUI regression tests and a Python 3.13 Xvfb CI smoke that launches the installed desktop command and executes the active demo analysis.
- Hardens project persistence to strict JSON, preserves uncommitted editor state across analysis switching, prompts before destructive project replacement/exit, and blocks conflicting analysis mutation/input changes while a run is active.
- Invalidates retained results when their owning analysis is removed so stale outputs cannot be exported after deletion.
- Adds an application-level end-to-end regression matrix covering every workflow exposed by the desktop catalog.
- Preserves the v0.95 solver-result integrity linkage and the complete v0.91-v0.94 replay/provenance compatibility gates.
- Bumps package/runtime/demo metadata to v0.96.0.
- The GUI exposes engineering screening and numerical/provenance evidence; it does not by itself establish cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.

## v0.95 solver-result integrity linkage — 2026-09-24

- Adds a deterministic SHA-256 identity to the complete standalone nonlinear fan/variable-friction solver result while excluding only its own integrity block.
- Canonicalizes signed zero and semantically named node/edge/closure collections for solver-result identity while preserving chronological and search ordering.
- Adds an independent self-audit that distinguishes missing integrity evidence from digest/metadata inconsistency and detects post-solve result-object corruption.
- Propagates solver-result integrity through nominal plus every evaluated nonlinear uncertainty corner, with explicit expected/evidence coverage, consistent/inconsistent/incomplete counts, exact corner indices, and separate coverage-gap versus corruption details.
- Preserves the same linkage in engineering dossiers and surfaces concise integrity coverage in standalone uncertainty and dossier Markdown.
- Keeps this solver-result identity distinct from the v0.57 top-level uncertainty-result digest and from v0.85-v0.94 replay/projection evidence.
- Preserves fan candidate discovery, no-extrapolation policy, root selection, numerical tolerances, nonlinear convergence, power calculations, uncertainty-corner enumeration, and engineering-status semantics.
- Adds regression coverage for recomputation, corruption detection, signed-zero/named-collection canonicalization, complete corner linkage, corrupted/missing corner evidence, unresolved statuses, dossier propagation, and aggregate dossier counts.
- Solver-result hashes are deterministic software-content identity evidence only; they do not establish source authenticity, cleanroom/ISO certification, CFD validity, fan acceptance, commissioning/TAB acceptance, manufacturer approval, stall/surge safety, physical uncertainty, or statistical confidence.
- Bumped package/runtime metadata to v0.95.0.

## v0.94 canonical solver provenance hardening — 2026-09-24

- Expands the shared canonical nonlinear network-result projection from final node/edge/pressure-power state to include network/status/reference-node identity, inner Newton iteration count, configured mass-balance tolerance, variable-friction convergence/configuration, and chronological outer-iteration history.
- Normalizes floating-point signed zero only inside canonical identity/projection representation, so numerically equivalent `-0.0` and `0.0` do not create different deterministic identities while solver outputs and physics remain unchanged.
- Sorts semantically named node, edge, and variable-friction closure collections before canonical serialization, while deliberately preserving order for chronological iteration history and all solver/search sequences whose order is meaningful.
- Reuses the single shared deterministic projection comparator for supplied-point, full-bisection, terminal, and selected replay; no parallel recursive comparator was added.
- Keeps SHA-256 identity distinct from field-level projection equality and preserves exact mismatch paths, values/types/presence, mismatch kinds, numerical errors, complete/incomplete coverage, uncertainty-corner provenance, and dossier propagation.
- Adds direct regression coverage for signed-zero stability, named-collection order invariance, history-order sensitivity, solver-metadata/configuration corruption localization, uncertainty propagation, dossier propagation, Markdown visibility, and strict `allow_nan=False` JSON serialization.
- Preserves fan candidate discovery/priority, interpolation and no-extrapolation behavior, root selection, numerical tolerances, nonlinear convergence, power calculations, uncertainty-corner enumeration, engineering statuses, and all v0.85-v0.93 replay semantics.
- Canonical SHA-256 values are deterministic content identities only; they do not prove source authenticity, cleanroom certification, CFD validity, fan acceptance, commissioning, global-root uniqueness, physical stability, stall/surge limits, manufacturer approval, physical uncertainty, or statistical confidence.
- Bumped package/runtime metadata to v0.94.0.

## v0.93 supplied fan-point network-state fingerprint and projection replay — 2026-09-24

- Retains the canonical internal network-state SHA-256 and full canonical projection for every successfully evaluated supplied fan-curve point before operating-point candidate selection.
- Independently re-solves each exact supplied airflow and compares the retained SHA-256 and field-level projection separately using the existing shared deterministic network-state comparator.
- Reports point-indexed deterministic JSON mismatch paths, recorded/recomputed values and types, mismatch kinds, numerical absolute errors when meaningful, all mismatches in deterministic point/path order, and tied per-field worst-error witnesses.
- Separates actual hash/projection corruption from incomplete supplied-point evaluation, missing retained state, and independent replay failure; complete no-intersection cases remain fully auditable while partial pre-failure coverage stays explicit.
- Aggregates supplied-point replay across nonlinear uncertainty corners and engineering dossiers with exact corner/point/path provenance, coverage gaps, mismatch totals, and maximum numerical witnesses.
- Preserves v0.85-v0.92 candidate discovery, fan interpolation/no-extrapolation, root-selection priority, solver tolerances, nonlinear convergence, power, uncertainty-corner, engineering-status, and replay semantics.
- This replay is deterministic numerical/provenance verification only; it is not cleanroom certification, CFD validation, fan acceptance, commissioning evidence, proof of global root uniqueness or physical stability, stall/surge analysis, manufacturer operating-envelope validation, physical uncertainty quantification, or statistical confidence analysis.
- Bumped package/runtime metadata to v0.93.0.

## v0.92 full per-bisection network-state projection replay diagnostics — 2026-09-24

- Retains canonical low/midpoint/high internal network-state projections on every bounded-bisection trace row alongside the existing v0.87 SHA-256 fingerprints.
- Reconstructs the exact retained search-origin airflow sequence and independently re-solves every applicable low/midpoint/high state without routing through presentation rounding.
- Reuses the v0.90/v0.91 deterministic projection comparator to report every JSON-style mismatch with exact iteration, bracket position, path, recorded/recomputed values, type evidence, mismatch kind, and numerical absolute error when meaningful.
- Separates SHA-256 replay from field-level projection replay and reports checked-versus-expected iteration/state-position coverage, incomplete-coverage gaps, deterministic replay verdicts, exact violation provenance, and tied per-field worst numerical witnesses.
- Aggregates full-trace projection replay through nonlinear uncertainty JSON/Markdown and engineering dossiers while preserving solved, no-intersection, iteration-limit, and non-converged engineering semantics.
- Preserves all v0.85-v0.91 root-selection, interpolation/no-extrapolation, tolerance, iteration-budget, convergence, power, uncertainty-corner, and replay behavior.
- Projection replay is deterministic numerical/provenance verification only; it is not cleanroom certification, CFD validation, fan acceptance, commissioning evidence, proof of global root uniqueness or physical stability, stall/surge analysis, manufacturer operating-envelope validation, physical uncertainty quantification, or statistical confidence analysis.
- Bumped package/runtime metadata to v0.92.0.

## v0.91 selected operating network-state projection replay diagnostics — 2026-09-24

- Retains the canonical selected operating network-state projection alongside the existing selected-state SHA-256 fingerprint.
- Independently re-solves the exact retained selected airflow and compares node, edge, pressure-power, and variable-friction closure projection fields with the fresh solved state.
- Localizes selected projection corruption to deterministic JSON-style field paths such as `$.nodes[0].relative_pressure_pa`, including cases where the retained selected-state SHA-256 itself remains unchanged.
- Propagates projection replay applicability/coverage, consistency, mismatch counts, exact paths, recorded/recomputed values, type evidence, numerical absolute errors when meaningful, tied per-field worst-error witnesses, violating uncertainty-corner indices, standalone-report evidence, and engineering-dossier evidence while preserving the existing pressure and fingerprint replay diagnostics.
- Projection replay is numerical/provenance verification only; it is not cleanroom certification, CFD validation, fan acceptance, commissioning evidence, proof of global root uniqueness, stall/surge analysis, or physical uncertainty quantification.
- Preserves v0.90 terminal projection replay, v0.89 selected fingerprint replay, root selection, no-extrapolation behavior, solver tolerances, iteration budgets, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.91.0.

## v0.90 terminal network-state projection replay diagnostics — 2026-09-24

- Retains canonical low/high terminal network-state projections alongside their SHA-256 fingerprints on solved final and post-decision iteration-limit brackets.
- Independently re-solves each terminal endpoint and compares the retained canonical node, edge, pressure-power, and variable-friction closure projection with the fresh projection.
- Localizes projection corruption to deterministic JSON-style field paths such as `$.nodes[0].relative_pressure_pa`, even when the retained SHA-256 fingerprint itself is not modified.
- Aggregates projection-replay consistency, exact violating endpoint positions, mismatch paths, and corner-level details through nonlinear uncertainty summaries, standalone reports, and engineering dossiers.
- Preserves v0.89 selected-operating-state fingerprint replay, v0.88 terminal fingerprint replay, v0.87 full-trace fingerprints, pressure-component replay, solver tolerances, root selection, no-extrapolation behavior, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.90.0.

## v0.89 selected operating network-state fingerprint replay — 2026-09-24

- Extends the v0.85 selected operating-state replay from scalar fan/loop/system/residual pressures to the canonical internal nonlinear network state.
- Retains a SHA-256 fingerprint of the selected solved node, edge, pressure-power, and variable-friction closure state and independently recomputes it from a fresh solve at the retained selected airflow.
- Detects selected operating-state internal corruption even when the retained selected airflow, search origin, and all scalar pressure/residual evidence remain unchanged.
- Propagates selected network-state replay consistency and exact recorded/recomputed hashes through nonlinear uncertainty summaries, standalone reports, engineering dossiers, and regression coverage.
- Preserves v0.88 terminal-bracket network-state replay, v0.87 full-trace network-state replay, root-selection/no-extrapolation behavior, numerical tolerances, iteration budgets, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.89.0.

## v0.88 terminal-bracket network-state fingerprint replay — 2026-09-24

- Retains canonical SHA-256 internal network-state fingerprints on solved final and post-decision iteration-limit terminal bracket low/high endpoints.
- Independently re-solves both terminal endpoints and compares canonical node, edge, pressure-power, and variable-friction closure state fingerprints.
- Detects terminal internal-state corruption even when terminal fan, loop-network, total-system pressures and retained trace replay evidence remain unchanged.
- Propagates terminal network-state replay consistency, exact violating endpoint positions plus recorded/recomputed hashes, uncertainty-corner provenance, standalone reports, and engineering dossiers.
- Preserves v0.87 full-trace network-state replay, v0.86 terminal pressure-component replay, root selection, iteration budgets, no-extrapolation behavior, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.88.0.

## v0.87 independent internal network-state fingerprint replay — 2026-09-24

- Retains a SHA-256 fingerprint for the canonical internal nonlinear network state at every low, midpoint, and high bounded-bisection position.
- Canonical state covers solved node pressures/balances, edge flows/resistances and pressure-law residuals, pressure-power balance, and variable-friction closure evidence.
- Freshly re-solves every reconstructed bisection state and compares the retained fingerprint with the independently recomputed fingerprint.
- Detects internal network-state provenance corruption even when scalar fan/loop/system pressure, residual, bracket-geometry, full-bracket replay, selected-state replay, and v0.86 terminal-bracket replay evidence remain unchanged.
- Propagates network-state replay coverage and exact violation-corner indices through standalone reports, nonlinear uncertainty summaries, engineering dossiers, and solved/iteration-limit regressions.
- Preserves root selection, bisection decisions, terminal-bracket replay, fan interpolation, nonlinear solver tolerances, no-extrapolation behavior, and all existing engineering acceptance semantics.
- Bumped package/runtime metadata to v0.87.0.

## v0.86 terminal-bracket pressure-component replay — 2026-09-24

- Retains low/high fan, nonlinear loop-network, and total system pressure on solved final bisection brackets and post-decision iteration-limit remaining brackets.
- Independently replays the terminal low/high pressure components from the selected supplied fan segment and the complete retained L/H/T decision chain.
- Closes the post-final-decision iteration-limit provenance gap where a newly replaced endpoint previously retained its residual but not a directly replay-auditable pressure-component state.
- Extends v0.84 exact mismatch provenance to terminal brackets with exact position/component, recorded/recomputed pressure, absolute error, violation records, and tied maximum-error witnesses.
- Propagates terminal replay consistency, violation corners/details, aggregate violation counts, maximum error, and tied worst witnesses through nonlinear uncertainty summaries and reports.
- Preserves v0.85 selected operating-state replay, v0.84 exact per-step mismatch provenance, v0.83 full-bracket replay, root-selection/no-extrapolation behavior, iteration budgets, and engineering acceptance semantics.
- Bumped package/runtime metadata to v0.86.0.


## v0.85 selected operating-state independent replay — 2026-09-24

- Adds a fresh nonlinear replay of every solved selected operating airflow after the bounded search completes, independently recomputing fan pressure, loop-network pressure, total system pressure, and fan-minus-system residual.
- Anchors the selected airflow to its retained search origin: the terminal bisection midpoint for bounded-bisection solutions or the exact supplied fan-curve point for direct tolerance contacts.
- Records per-component replay errors, exact violations, maximum error, and tied maximum-error witnesses without changing the existing 1e-9 Pa numerical replay tolerance or any engineering acceptance criterion.
- Propagates selected-state replay coverage, origin mismatches, violation corners/details, and worst replay-error evidence across nonlinear uncertainty studies and Markdown reports.
- Adds common-mode pressure-corruption regression coverage and supplied-point origin coverage.
- Bumped package/runtime metadata to v0.85.0.


## v0.84 exact pressure-component replay violation provenance — 2026-09-24

- Adds deterministic violation records for every independent pressure-component replay mismatch with exact bisection iteration, bracket position (low/midpoint/high), pressure component (fan/loop-network/system), recorded value, independently recomputed value, and absolute error.
- Preserves tied maximum-error witnesses so the worst replay discrepancy can be traced to the exact retained component state instead of only a scalar maximum.
- Propagates exact pressure-component replay violation details, aggregate violation counts, and tied maximum-error witnesses across evaluated nonlinear uncertainty corners.
- Extends standalone and uncertainty Markdown reports with the new violation/witness provenance while preserving all v0.83 compatibility aliases and solver behavior.
- No engineering acceptance criteria, root-selection policy, interpolation behavior, or numerical tolerance changed; this is audit/provenance hardening only.
- Bumped package/runtime metadata to v0.84.0.


## v0.83 full-bracket pressure-component replay — 2026-09-24

- Retains low and high endpoint fan pressure, nonlinear loop-network pressure, and total system pressure in every bounded-bisection trace step, complementing the v0.82 midpoint pressure state.
- Independently reconstructs and re-solves low, midpoint, and high pressure components from the selected supplied fan segment and active bisection decision chain.
- Adds explicit low-endpoint, high-endpoint, midpoint, and complete-bracket replay verdicts while preserving the existing v0.82 midpoint aliases for compatibility.
- Detects endpoint common-mode pressure corruption that leaves low/high residuals, midpoint pressure evidence, decision semantics, raw-state geometry, and v0.81 residual replay unchanged.
- Uses the existing strict 1e-9 Pa numerical replay tolerance and propagates complete-bracket violations through nonlinear uncertainty summaries and reports.
- Preserves bounded root selection, no-extrapolation behavior, iteration budgets, solver acceptance tolerances, and all engineering acceptance criteria; this remains deterministic implementation-provenance hardening.
- Bumped package/runtime metadata to v0.83.0.


## v0.82 independent pressure-component replay — 2026-09-24

- Independently replays each retained bisection midpoint's fan pressure, nonlinear loop-network pressure, and total system pressure from the selected supplied fan segment and a fresh variable-friction network solve.
- Compares the replayed pressure components directly with their retained trace values instead of relying only on the v0.80 algebraic identities or the v0.81 fan-minus-system residual.
- Detects common-mode pressure corruption where fan, loop, and total system pressures shift together while the residual and all retained-state pressure identities remain self-consistent.
- Retains complete per-step component-replay coverage, a strict 1e-9 Pa numerical tolerance, exact uncertainty-corner violation indices, and tied maximum component-replay error provenance.
- Propagates component-replay evidence through standalone loop reports, nonlinear uncertainty reports, engineering dossiers, and regression coverage for solved and iteration-limit traces.
- Preserves root selection, decision semantics, iteration budgets, fan-curve no-extrapolation behavior, and all existing engineering acceptance criteria; this remains numerical implementation provenance only.
- Bumped package/runtime metadata to v0.82.0.

## v0.81 independent fan/system residual replay — 2026-09-24

- Reconstructs every retained bounded-bisection low/high/midpoint airflow from the selected supplied fan segment and recorded L/H/T decision chain, then freshly re-solves the nonlinear variable-friction loop at each replayed state.
- Recomputes interpolated fan pressure and total system pressure independently of retained trace pressure/residual fields, and checks every retained low/high/midpoint fan-minus-system residual against that fresh model evaluation.
- Keeps the v0.80 pressure-state identity audit intact as a complementary retained-state check; v0.81 additionally detects self-consistent stored fan-pressure/residual corruption that can satisfy those identities.
- Retains per-step replay evidence, a strict 1e-9 Pa comparison tolerance, maximum replay error, exact nonlinear uncertainty-corner violation indices, and tied worst-error provenance.
- Propagates the replay evidence through standalone loop reports, nonlinear uncertainty reports, engineering dossiers, README/docs, solved cases, and iteration-limit cases.
- Adds regression coverage where terminal fan pressure and residual are corrupted together so raw-state, pressure-state, decision-semantic, and origin replay checks remain consistent while independent model replay correctly fails.
- Does not change candidate priority, bounded root selection, root-acceptance tolerance, iteration budgets, fan-curve no-extrapolation behavior, or any engineering acceptance criterion.
- Bumped package/runtime metadata to v0.81.0.


## v0.80 bisection trace pressure-state audit — 2026-09-24

- Retains midpoint fan pressure, variable-friction loop pressure, fixed pressure, total system pressure, and fan-minus-system residual for every bounded-bisection trace evaluation.
- Independently checks the retained pressure identities `system = fixed + loop` and `residual = fan - system`, and anchors each retained fixed-pressure component to the study input.
- Aggregates exact nonlinear uncertainty-corner indices for pressure-state audit failures plus tied maximum system-pressure and residual identity errors.
- Surfaces the new evidence in standalone fan/variable-friction loop reports, nonlinear uncertainty reports, and engineering dossiers.
- Adds direct corruption regressions that distinguish total-system pressure inconsistency from fixed-pressure provenance corruption, while preserving v0.79 raw-state, v0.78 decision-semantics, v0.77 origin replay, and iteration-limit behavior.
- Does not change candidate priority, root selection, root-acceptance tolerance, iteration budgets, fan-curve no-extrapolation behavior, or any engineering acceptance criterion.
- Treats pressure-state checks strictly as numerical implementation provenance; they are not physical airflow uncertainty, interpolation-error bounds, root uniqueness/stability evidence, stall/surge evidence, commissioning/certification evidence, or equipment acceptance.
- Bumped package/runtime metadata to v0.80.0.

## v0.79 independent bisection trace raw-state audit — 2026-09-24

- Independently recomputes strict sign-change from retained low/high fan-minus-system residuals for every bounded-bisection trace step.
- Independently recomputes each retained airflow midpoint from the numeric bracket endpoints and records the absolute midpoint-centering error.
- Checks the stored strict-sign-change and midpoint-validity flags against those recomputed numeric facts instead of trusting the flags as evidence.
- Aggregates exact nonlinear uncertainty-corner indices for numeric sign failures, sign-flag mismatches, numeric midpoint failures, midpoint-flag mismatches, and combined raw-state audit failures, plus tied maximum midpoint-error witnesses.
- Adds solved, iteration-limit, flag-corruption, and self-consistent corrupted-midpoint regression coverage while preserving the merged v0.78 decision-semantics audit and v0.77 origin replay.
- Does not change candidate priority, root selection, root-acceptance tolerance, iteration budgets, fan-curve no-extrapolation behavior, or any engineering acceptance criterion.
- Treats raw-state checks strictly as numerical implementation provenance; they are not physical airflow uncertainty, interpolation-error bounds, root uniqueness/stability evidence, stall/surge evidence, commissioning/certification evidence, or equipment acceptance.
- Bumped package/runtime metadata to v0.79.0.

## v0.78 bisection trace decision-semantics audit — 2026-09-24

- Independently verifies every retained bounded-bisection L/H/T decision against the recorded midpoint fan-minus-system residual and the configured operating-pressure tolerance.
- Retains per-step recorded/expected decision evidence plus exact violating iteration numbers, separate from state-transition replay and origin-to-terminal replay.
- Aggregates exact nonlinear uncertainty-corner indices for decision-semantic violations and surfaces the evidence in standalone loop, uncertainty, and engineering-dossier Markdown.
- Adds solved, iteration-limit, and deliberate decision-corruption regression coverage while preserving v0.76 geometry checks and v0.77 origin replay.
- Does not change candidate priority, root selection, root-acceptance rules, iteration budgets, fan-curve no-extrapolation behavior, or any engineering acceptance criterion.
- Treats decision semantics strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, root uniqueness/stability evidence, a stall/surge criterion, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.78.0.

## v0.77 bisection trace origin-to-terminal replay — 2026-09-24

- Anchors every retained bounded-bisection decision trace to the exact initial signed-residual bracket selected from adjacent supplied fan-curve points.
- Reconstructs the complete L/H/T decision chain from that origin and independently verifies every recorded airflow/residual bracket state.
- Verifies the reconstructed terminal bracket against the solved final bracket or, for iteration-limit outcomes, the retained remaining active bracket.
- Aggregates exact nonlinear uncertainty-corner indices for origin-to-terminal replay violations and surfaces the evidence in standalone loop, uncertainty, and engineering-dossier Markdown.
- Preserves v0.76 per-step width/normalized-width geometry audits and adds solved plus iteration-limit regression coverage without changing candidate priority, root-acceptance rules, iteration budgets, or no-extrapolation behavior.
- Treats the replay strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, root uniqueness/stability evidence, a stall/surge criterion, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.77.0.

## v0.76 bisection decision-trace geometry consistency — 2026-09-24

- Audits every retained bounded-bisection trace record's `width_m3_h` against its recorded low/high airflow endpoints.
- Audits every retained trace record's normalized supplied-segment width against the exact binary contraction implied by its one-based bisection iteration.
- Retains per-step expected/recorded width evidence and absolute consistency errors, with aggregate exact uncertainty-corner violation indices and worst-error witnesses.
- Applies the same trace-geometry audit to solved pressure-tolerance and non-converged iteration-limit traces without changing root selection, iteration budgets, or terminal replay semantics.
- Surfaces the evidence in standalone fan-loop, nonlinear uncertainty, and engineering-dossier Markdown.
- Adds a corruption-detection regression that deliberately alters retained width fields and verifies the audit fails those fields while preserving the independent replay checks.
- Treats trace geometry strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, a continuous-root guarantee, stability/stall/surge evidence, commissioning/certification evidence, or an equipment-acceptance criterion.
- Bumped package/runtime metadata to v0.76.0.

## v0.75 iteration-limit decision-trace terminal replay — 2026-09-24

- Extends retained bounded-bisection decision traces to non-converged searches that exhaust `max_operating_iterations`.
- Keeps iteration-limit outcomes explicitly non-converged with no accepted operating point and no fabricated terminal `T` decision.
- Replays the final recorded `L`/`H` decision into the retained remaining signed-residual bracket and audits exact airflow/residual endpoint agreement.
- Aggregates solved and iteration-limit trace coverage, terminal-outcome consistency, final replay violations, and maximum trace length across nonlinear uncertainty corners.
- Surfaces the evidence in standalone loop, uncertainty, and engineering-dossier Markdown with direct solver, uncertainty, and dossier regression coverage.
- Treats the trace and terminal replay strictly as numerical implementation provenance; they are not physical airflow uncertainty, interpolation-error bounds, continuous-root guarantees, stability/stall/surge evidence, manufacturer operating limits, commissioning/certification evidence, or equipment-acceptance criteria.
- Bumped package/runtime metadata to v0.75.0.

## v0.74 supplied-point candidate index-separation audit — 2026-09-24

- Retains exact supplied-point index intervals for solver-eligible tolerance-contact points and positive-to-negative sign-change segments.
- Measures selected-to-alternative discrete candidate separation directly in supplied-point index steps, independently of nonuniform airflow spacing.
- Retains tied nearest alternatives in index space and aggregates the minimum index-interval separation across uncertainty corners with exact source-corner provenance.
- Surfaces the evidence in standalone nonlinear fan-loop, uncertainty, and engineering-dossier Markdown alongside absolute-airflow, full-curve-span, and minimum-supplied-spacing separation evidence.
- Adds direct solver, uncertainty, and dossier regression coverage without changing candidate priority, bounded root solving, bisection trace/replay semantics, or no-extrapolation behavior.
- Treats supplied-point index separation strictly as discrete sample-grid topology; it is not physical uncertainty, an interpolation-error estimate, a continuous root-separation guarantee, stability/stall/surge evidence, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.74.0.

## v0.73 bisection decision-trace replay audit — 2026-09-24

- Replays every nonterminal successful bounded-bisection L/H decision into the next retained trace record and verifies both airflow-bracket and signed-residual-bracket state transitions.
- Verifies trace iteration numbering is contiguous from one in addition to the existing trace-length, strict-sign, midpoint-geometry, and terminal-position checks.
- Retains per-transition replay evidence with exact from/to iteration numbers and separate airflow/residual transition checks.
- Aggregates exact uncertainty-corner indices for iteration-sequence and state-transition replay violations.
- Surfaces the new replay audit in standalone fan-loop, uncertainty, and engineering-dossier Markdown and adds direct regression coverage.
- Preserves operating-point selection, supplied-curve no-extrapolation behavior, and all v0.72 decision-trace semantics.
- Treats replay evidence strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, root uniqueness/stability evidence, a manufacturer operating region, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.73.0.

## v0.72 bounded-bisection decision-trace provenance — 2026-09-24

- Retains every midpoint evaluation used by a successful bounded fan/system bisection solve, including the active signed-residual bracket, midpoint residual, normalized bracket width, and exact endpoint-replacement or tolerance-acceptance decision.
- Encodes the deterministic decision path as an auditable L/H/T sequence: replace the positive-residual low endpoint, replace the negative-residual high endpoint, or accept the midpoint on the configured pressure tolerance.
- Audits trace length against operating iterations, strict sign bracketing before every evaluation, arithmetic midpoint geometry, and terminal tolerance-decision placement.
- Propagates decision-trace evidence across nonlinear uncertainty corners with exact violation corner indices and tied source-corner provenance for the maximum retained trace length.
- Surfaces trace provenance in standalone fan-loop, nonlinear uncertainty, and engineering-dossier Markdown.
- Adds direct solver, uncertainty, and dossier regression coverage across Python 3.11, 3.12, and 3.13.
- Preserves v0.70 iteration-limit bisection provenance and v0.71 supplied-grid-resolution normalization without changing operating-point selection or no-extrapolation behavior.
- Treats the trace strictly as numerical implementation provenance; it is not physical airflow uncertainty, interpolation error, a continuous root guarantee, stability/stall/surge evidence, a manufacturer operating limit, commissioning/certification evidence, or an equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.72.0.

## v0.71 supplied-grid resolution normalization — 2026-09-24

- Records minimum and maximum adjacent supplied fan-curve airflow spacing plus the max/min spacing ratio inside the nonlinear residual-topology audit.
- Normalizes each selected-to-alternative discrete candidate interval gap by the minimum adjacent supplied-point spacing, alongside the existing full-curve-span normalization.
- Aggregates the minimum sampling-resolution-normalized separation across uncertainty corners with exact tied source-corner provenance and the corresponding supplied-point spacing.
- Surfaces the new evidence in standalone nonlinear fan-loop and uncertainty Markdown.
- Adds direct solver and uncertainty regression coverage while preserving all existing no-extrapolation and unresolved-case withholding rules.
- Treats supplied-grid normalization strictly as sampled-data numerical topology evidence; it is not an interpolation-error estimate, continuous root-separation guarantee, physical robustness/stability margin, stall/surge criterion, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.
- Bumped package/runtime metadata to v0.71.0.

## v0.70 iteration-limit bisection provenance — 2026-09-24

- Preserves bounded-bisection search provenance when the configured operating-point iteration budget is exhausted before the pressure residual reaches tolerance.
- Retains the last evaluated midpoint/residual and the remaining active strict-sign bisection bracket, including width, half-width, supplied-segment-normalized width, completed contraction steps, and binary-width consistency evidence.
- Keeps iteration-limit outcomes explicitly non-converged with no accepted or fabricated operating point.
- Aggregates iteration-limit search evidence across nonlinear uncertainty corners, including exact affected corner indices, remaining-bracket invariant coverage, strict-sign violations, and maximum width-fraction consistency error with tied source provenance.
- Surfaces unresolved iteration-limit search geometry in standalone fan-loop, uncertainty, and engineering-dossier Markdown while keeping solved final-bracket evidence separate.
- Adds direct solver and uncertainty regression coverage across the supported Python matrix.
- Preserves v0.69 bidirectional sampled residual topology and all existing no-extrapolation, unresolved-case withholding, and solver-candidate rules.
- Treats remaining bracket geometry as numerical implementation/search evidence only; it is not physical airflow uncertainty, an interpolation-error bound, a continuous worst-case guarantee, a stability/stall/surge criterion, or an equipment-acceptance limit.
- Bumped package/runtime metadata to v0.70.0.

## v0.69 bidirectional sampled residual sign-change topology audit — 2026-09-24

- Retains strict negative-to-positive fan-minus-system residual sign-change segments across supplied fan-curve samples as explicit audit-only evidence.
- Keeps the operating-point solver unchanged: tolerance-contact points and strict positive-to-negative sign-change segments remain the only discrete solver candidates.
- Reports reverse sign-change segments per case, total bidirectional strict sign-change count, and uncertainty-corner reverse-crossing counts and exact corner indices.
- Surfaces the same audit-only evidence in standalone nonlinear fan-loop, uncertainty, and engineering-dossier Markdown.
- Adds regression coverage proving a reverse sampled crossing is visible in the audit while the solver candidate list remains empty for that feature.
- Preserves v0.68 scale-aware alternative-candidate separation, v0.67 bisection implementation-invariant auditing, and all no-extrapolation/unresolved-case withholding rules.
- Treats reverse sampled crossings as discrete numerical topology only; they do not establish an additional continuous root, dynamic stability, stall/surge behavior, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.
- Bumped package/runtime metadata to v0.69.0.

## v0.68 scale-aware alternative crossing-candidate separation — 2026-09-24

- Normalizes each v0.66 selected-to-alternative discrete candidate airflow gap by the exact supplied fan-curve airflow span used for that nonlinear solve.
- Retains the normalized fraction on every alternative candidate feature and on the nearest tied alternative evidence without evaluating or extrapolating any additional fan-curve point.
- Aggregates the minimum normalized separation across solved uncertainty corners with exact tied source-corner provenance and the corresponding supplied-curve airflow span.
- Surfaces absolute and normalized candidate separation in standalone fan-loop, nonlinear uncertainty, and engineering-dossier Markdown.
- Adds direct multi-candidate arithmetic tests plus uncertainty and dossier regression coverage.
- Preserves v0.67 bisection implementation-invariant auditing and all existing no-extrapolation and unresolved-case withholding rules.
- Treats normalized separation as sampled-data numerical topology evidence only; it is not a physical robustness margin, continuous root-separation guarantee, stability/stall/surge criterion, manufacturer operating region, commissioning/certification result, or equipment-acceptance limit.
- Bumped package/runtime metadata to v0.68.0.

## v0.67 bisection implementation-invariant audit — 2026-09-24

- Audits retained bounded-bisection search geometry directly from the unrounded live solver state without changing the operating-point solve.
- Records whether the active terminal bracket preserves the strict positive/negative residual sign change and whether the accepted airflow is the active bracket midpoint within a floating-point implementation comparison.
- Records completed binary contraction steps, the iteration-implied width fraction of the original supplied segment, the actual width fraction, and their absolute floating-point consistency error.
- Keeps the invariant audit inapplicable to direct supplied-point tolerance contacts rather than inventing bisection evidence.
- Aggregates invariant-evidence counts, exact sign/midpoint violation corner indices, and tied source-corner provenance for the maximum raw width-fraction consistency error.
- Surfaces invariant evidence in standalone fan-loop, nonlinear uncertainty, and engineering-dossier reports while preserving v0.66 alternative-candidate separation evidence.
- Adds solver, uncertainty, and dossier regression coverage.
- Treats these as implementation-verification diagnostics only; no engineering acceptance threshold, physical uncertainty, interpolation-error bound, stability criterion, or equipment limit is introduced.
- Bumped package/runtime metadata to v0.67.0.

## v0.66 alternative crossing-candidate separation audit — 2026-09-24

- Extends solved nonlinear fan/variable-friction crossing provenance with airflow separation to every additional discrete supplied-point candidate feature.
- Treats supplied-point tolerance contacts as point intervals and strict sign-change candidates as their exact supplied-point airflow intervals.
- Reports the selected airflow's gap to every alternative discrete candidate interval, including explicit zero-gap overlap, while retaining solver-priority rank and tied nearest alternatives.
- Aggregates alternative-separation coverage, overlap corner indices, and the minimum selected-to-alternative interval gap with exact tied source-corner provenance.
- Preserves v0.65 bounded root-search geometry and v0.64 pressure-residual airflow-equivalence evidence in standalone, uncertainty, and dossier reporting.
- Adds deterministic solver, uncertainty, and dossier regression coverage across Python 3.11, 3.12, and 3.13.
- Treats this as discrete sampled-data numerical topology evidence only; it does not estimate another continuous root, prove multiple physical intersections, or define stability, stall/surge, manufacturer-region, commissioning, certification, or equipment-acceptance criteria.
- Bumped package/runtime metadata to v0.66.0.

## v0.65 bounded operating-point root-search geometry — 2026-09-24

- Retains the final active signed-residual bisection interval immediately before a bounded nonlinear fan/system midpoint satisfies the configured operating-pressure tolerance.
- Records final bracket low/high airflow, signed endpoint residuals, width, half-width, selected midpoint/residual, iteration number, and width normalized by the original supplied interpolation-segment span.
- Distinguishes bounded-bisection solutions from direct supplied-point tolerance contacts; direct contacts preserve their selected supplied-point index and do not fabricate bisection evidence.
- Propagates operating-point search evidence through nonlinear uncertainty corners and aggregates method counts, complete solved-corner coverage, and worst final bracket width/half-width/normalized width with exact tied source-corner provenance.
- Surfaces final root-search geometry in standalone fan-loop, nonlinear uncertainty, and engineering-dossier Markdown.
- Adds direct solver, uncertainty, partial-coverage, and dossier regression coverage.
- Treats bracket width and half-width strictly as numerical search-geometry evidence, not physical airflow uncertainty, interpolation-error bounds, continuous worst-case guarantees, or equipment-acceptance limits.
- Bumped package/runtime metadata to v0.65.0.

## v0.64 pressure-residual airflow-equivalence audit — 2026-09-24

- Maps the already configured operating-pressure solver tolerance through each solved corner's local fan-minus-system secant gradient into an equivalent airflow magnitude.
- Maps each corner's actual signed solved pressure residual through the same local gradient into absolute airflow-equivalent residual and signed linearized airflow-correction evidence.
- Normalizes both equivalents by the active supplied-point interpolation-bracket airflow span for scale-aware diagnostics.
- Aggregates worst evaluated equivalents with exact tied source-corner provenance and explicit complete-versus-partial coverage.
- Reuses existing supplied-point bracket and crossing-conditioning evidence only; no extra fan-curve evaluation, extrapolation, or new acceptance threshold is introduced.
- Treats the values as first-order numerical solver diagnostics, not measurement uncertainty, fan-performance uncertainty, interpolation-error bounds, continuous worst-case guarantees, stability criteria, or equipment acceptance limits.
- Surfaces the new evidence in standalone Markdown and engineering dossiers and adds complete/zero-solved-corner regression coverage.
- Bumped package/runtime metadata to v0.64.0.

## v0.63 selected crossing-candidate provenance — 2026-09-24

- Orders discrete supplied-point crossing candidates using the nonlinear solver's actual selection policy: tolerance-contact fan points first in point order, followed by strict positive-to-negative sign-change segments in segment order.
- Records the exact selected candidate for every solved nonlinear fan/variable-friction case, including candidate kind, zero-based solver-priority rank, additional candidate count, and whether the selected sampled feature is the only discrete candidate.
- Leaves selected-candidate fields unset for no-intersection and non-converged cases rather than fabricating a choice.
- Propagates selected-candidate provenance through nonlinear uncertainty corners and aggregates selected-evidence coverage, first-priority-selection coverage, and exact solved-corner indices where additional discrete candidates remain.
- Surfaces the selection policy and selected-candidate evidence in standalone reports while extending engineering-dossier residual-topology summaries.
- Adds deterministic regression coverage for multiple synthetic discrete candidates and for repository example/uncertainty/dossier propagation.
- Preserves the independently added v0.62 interpolation-segment position audit.
- Treats this as deterministic sampled-data solver-choice provenance only; it does not prove continuous physical intersection count or uniqueness and does not define dynamic stability, stall/surge, manufacturer-region, commissioning, certification, or equipment-acceptance criteria.
- Bumped package/runtime metadata to v0.63.0.

## v0.62 fan-curve interpolation segment-position audit — 2026-09-24

- Adds per-solved-corner evidence for the exact supplied fan-curve interpolation segment containing the nonlinear operating point.
- Reports segment airflow span, lower/upper supplied-point clearance, nearest supplied segment endpoint, normalized segment position, and normalized nearest-endpoint clearance.
- Aggregates minimum absolute/normalized supplied-point clearance and maximum active segment span with exact tied source-corner provenance.
- Preserves complete-versus-partial coverage explicitly; unresolved corners do not receive fabricated segment-position evidence.
- Surfaces the same evidence in standalone nonlinear uncertainty Markdown and engineering-dossier tables.
- Adds regression coverage for arithmetic, extrema provenance, reporting, dossier propagation, and zero-solved-corner behavior.
- Treats supplied-point proximity as interpolation-geometry provenance only; it is not an interpolation-error estimate, uncertainty bound, stall/surge margin, manufacturer operating region, or equipment-acceptance threshold.
- Bumped package/runtime metadata to v0.62.0.

## v0.61 supplied-point residual-topology audit — 2026-09-24

- Adds a discrete fan-minus-system residual-topology audit to the nonlinear fan/variable-friction operating-point solver using the supplied fan-curve points already evaluated during bounded root search.
- Records expected/evaluated point counts, complete versus partial point coverage, tolerance-contact points, strict sign-change segments, residual transitions, sampled monotonic non-increasing behavior within the configured pressure tolerance, and the largest positive residual increase.
- Preserves partial audit evidence when network evaluation becomes non-converged instead of implying that all supplied fan points were checked.
- Propagates the audit into every nonlinear uncertainty corner and aggregates complete point coverage, sampled-monotonicity counts, residual-increase corner indices, multiple discrete candidate-feature corner indices, and tied source provenance for the largest positive residual increase when present.
- Surfaces the evidence in standalone nonlinear-loop reports, uncertainty reports, and engineering-dossier tables.
- Adds regression coverage for solved, no-intersection, non-converged, uncertainty-corner, and dossier paths.
- Explicitly states that candidate crossing features and sampled residual monotonicity are not a count or proof of continuous physical intersections, dynamic stability, stall/surge limits, manufacturer operating region, or equipment acceptance.
- Bumped package/runtime metadata to v0.61.0.

## v0.60 fan/system local crossing-conditioning audit — 2026-09-24

- Derives fan-pressure, system-pressure, and signed fan-minus-system secant slopes from each solved corner's existing supplied-point intersection bracket.
- Reports absolute residual-gradient magnitude plus the reciprocal local airflow-per-pressure gradient when the bracket residual slope is nonzero.
- Computes the straight-line secant-root airflow and its absolute/normalized difference from the solved nonlinear operating airflow without any extra fan-curve evaluation or extrapolation.
- Aggregates minimum absolute residual slope and maximum secant-root disagreement with exact tied source-corner provenance.
- Preserves partial diagnostic evidence for indeterminate studies while keeping complete-study coverage explicit.
- Surfaces the same evidence in standalone Markdown and engineering-dossier tables.
- Adds regression coverage for arithmetic, provenance, report output, dossier propagation, and zero-solved-corner behavior.
- Treats the new quantities as numerical root-conditioning diagnostics only; no dynamic stability, stall/surge, manufacturer-region, commissioning, certification, or equipment-acceptance threshold is inferred.
- Bumped package/runtime metadata to v0.60.0.

## v0.59 fan/system intersection-bracket provenance — 2026-09-24

- Retains the exact supplied fan-curve interpolation endpoints that bound every solved nonlinear uncertainty operating point.
- Preserves endpoint fan pressure, system pressure, and signed fan-minus-system residual without any new solver evaluation or fan-curve extrapolation.
- Distinguishes strict sign-change brackets from supplied-point/root contacts that are within the configured operating-pressure tolerance.
- Aggregates solved-corner bracket coverage plus minimum nearest-endpoint pressure-gap and endpoint-residual-span evidence with exact tied source-corner provenance.
- Includes the new bracket evidence inside the existing canonical SHA-256 nonlinear-result integrity scope.
- Preserves v0.58 complete per-metric power-coverage auditing and its withholding rules for partial metrics.
- Surfaces the new evidence in standalone Markdown, engineering dossiers, and nonlinear uncertainty documentation.
- Adds regression coverage for complete studies and zero-solved-corner/indeterminate studies.
- Treats bracket evidence as numerical root-enclosure provenance only; it is not a stall/surge, manufacturer operating-region, commissioning, certification, or equipment-acceptance margin.
- Bumped package/runtime metadata to v0.59.0.

## v0.58 complete per-metric power-coverage audit — 2026-09-24

- Requires every evaluated solved corner to provide a power metric before CleanroomX emits that metric's min/max range, extrema provenance, or nominal-relative excursion.
- Adds explicit `complete`, `partial`, and `unavailable` coverage states with available/total corner counts and exact missing corner indices for fluid air power, shaft power, electrical input, and specific fan power.
- Exposes the nominal solver power record directly as `nominal_power_evidence`.
- Prevents a partially populated power metric from being summarized as though it covered the complete deterministic corner study.
- Surfaces electrical-input and SFP coverage states in engineering-dossier Markdown and all power-metric coverage states in standalone uncertainty reports.
- Preserves v0.57 deterministic result-integrity evidence plus v0.56 solver-iteration budget evidence and earlier bounded-solver diagnostics.
- Adds regression coverage for partial metric coverage, missing explicit efficiencies, complete coverage, nominal power evidence, and report output.
- Bumped package/runtime metadata to v0.58.0.

## v0.57 deterministic nonlinear result integrity — 2026-09-24

- Adds a canonical SHA-256 digest to every fan/variable-friction nonlinear uncertainty result.
- Hashes the complete result before the integrity block using compact UTF-8 JSON with sorted keys, explicit canonicalization metadata, and a versioned scope identifier.
- Keeps result-integrity evidence separate from engineering acceptance: the digest identifies exact computed content but does not authenticate source authority, calibration, certification, or equipment suitability.
- Surfaces the full result digest in standalone uncertainty Markdown and engineering dossiers.
- Adds dossier summary counts for present/missing nonlinear result-integrity records without changing existing engineering status decisions.
- Adds regressions that independently recompute the digest, verify deterministic repeatability, verify input-sensitive changes, and confirm dossier propagation.
- Bumped package/runtime metadata to v0.57.0.

## v0.56 configured solver-iteration budget audit — 2026-09-24

- Exposes the selected operating network's inner Newton iteration count alongside the existing outer Darcy-friction and operating-point iteration diagnostics.
- Aggregates worst solved-corner outer, Newton, and operating-point iteration counts with exact tied source-corner provenance.
- Preserves the study's existing `max_outer_iterations`, `max_newton_iterations`, and `max_operating_iterations` settings as explicit configured iteration limits.
- Reports utilization ratio and remaining iterations for each configured solver iteration budget, with a separate complete/partial aggregate audit state.
- Keeps the v0.52 residual-tolerance audit unchanged while preserving v0.53 nominal-relative excursions, v0.54 fan-curve boundary clearance, and v0.55 no-intersection endpoint diagnostics.
- Treats iteration-budget utilization strictly as numerical convergence evidence, not an equipment, commissioning, certification, or cleanroom acceptance margin.
- Surfaces the new audit in standalone Markdown and engineering-dossier reporting and adds regression coverage for complete and zero-solved-corner studies.
- Bumped package/runtime metadata to v0.56.0.

## v0.55 no-intersection supplied-endpoint diagnostics — 2026-09-24

- Adds explicit supplied-endpoint diagnostics for nonlinear uncertainty corners whose fan/system operating point does not intersect inside the available fan-curve range.
- Identifies whether each unresolved case is bounded by the lower or upper supplied airflow endpoint and records the endpoint airflow, fan pressure, system pressure, signed fan-minus-system pressure margin, mismatch type, and absolute pressure gap.
- Aggregates lower-boundary and upper-boundary no-intersection counts and retains tie-aware source-corner provenance for the largest evaluated endpoint pressure gap.
- Preserves the strict no-extrapolation boundary: the diagnostic does not estimate a missing operating point, fan capacity beyond supplied data, stall/surge margin, manufacturer operating region, or equipment acceptance.
- Surfaces no-intersection boundary evidence in standalone Markdown reports, engineering-dossier tables, and dossier executive summaries.
- Adds regression coverage for both lower-boundary fan-pressure-deficit and upper-boundary fan-pressure-surplus cases plus dossier aggregation.
- Bumped package/runtime metadata to v0.55.0.

## v0.54 supplied fan-curve boundary-clearance audit — 2026-09-24

- Adds per-solved-corner airflow distance from the operating point to both endpoints of that corner's exact supplied or speed-transformed fan-curve airflow range.
- Reports lower, upper, and nearest endpoint headroom in m³/h together with normalized airflow position, normalized nearest-boundary headroom, and the nearest endpoint identity.
- Aggregates the minimum nearest-boundary headroom across solved evaluated corners with tie-aware source-corner provenance and preserves the exact active fan/system/duct uncertainty context.
- Keeps boundary-clearance evidence explicitly diagnostic: no minimum acceptable headroom, stall/surge margin, manufacturer operating region, or equipment-acceptance criterion is inferred.
- Marks complete versus partial study coverage independently, so indeterminate analyses may retain solved-corner diagnostic evidence without fabricating a complete uncertainty envelope.
- Surfaces the new evidence in standalone Markdown reports and engineering-dossier tables, with regression coverage for exact arithmetic, provenance, zero-solved-corner behavior, and dossier integration.
- Bumped package/runtime metadata to v0.54.0.

## v0.53 nominal-relative corner excursion evidence — 2026-09-24

- Adds nominal-centered absolute and percentage excursion evidence for complete nonlinear fan/variable-friction uncertainty operating-point envelopes.
- Covers operating airflow, fan pressure, system pressure, and fan air power, plus available fluid/shaft/electrical/SFP power-chain ranges.
- Percentage excursion is withheld when the solved nominal value is effectively zero rather than inventing an unstable denominator.
- Keeps excursions conditional on complete corner coverage; indeterminate studies emit no nominal-relative envelope evidence.
- Explicitly treats the new values as evaluated-corner summaries rather than sensitivity coefficients or guarantees about continuous interior extrema.
- Surfaces operating-point excursions in standalone Markdown reports and a compact airflow-excursion column in engineering dossiers.
- Adds regression coverage for excursion arithmetic, power-chain availability, reporting, dossier integration, and indeterminate withholding.
- Bumped package/runtime metadata to v0.53.0.

## v0.52 configured solver-tolerance utilization audit — 2026-09-24

- Extends nonlinear fan/variable-friction uncertainty solver-quality evidence with explicit checks against the operating-pressure, resistance-closure, and mass-balance tolerances already configured for the solver.
- Reports each worst solved-corner metric's configured tolerance, utilization ratio, and remaining numerical margin without introducing any new acceptance threshold.
- Adds an aggregate status that distinguishes complete within-tolerance coverage, incomplete study coverage, unavailable checks, and any detected configured-tolerance exceedance.
- Keeps pressure-law residual and iteration counts as diagnostics only because the workflow has no configured acceptance threshold for those quantities.
- Surfaces the configured solver-tolerance audit in standalone Markdown reports and integrated engineering-dossier tables.
- Adds regression coverage for complete studies, zero-solved-corner studies, utilization/margin arithmetic, report output, and dossier integration.
- Bumped package/runtime metadata to v0.52.0.

## v0.51 aggregate nonlinear solver-quality evidence — 2026-09-24

- Added a compact solver-quality summary across nonlinear fan/variable-friction uncertainty corners.
- Reports worst solved-corner absolute operating-pressure residual, Darcy resistance-closure error, mass-balance residual, pressure-law residual, network outer iterations, and operating-point iterations.
- Retains every tied source corner for each worst metric, including active fan/system/duct uncertainty context and the observed signed value where applicable.
- Preserves configured pressure, resistance-closure, and mass-balance tolerances without inventing thresholds for pressure-law residual or iteration counts.
- Distinguishes evaluated-corner coverage from complete-study coverage, including nominal-case status, so partial evidence is not presented as complete verification.
- Extended Markdown reporting and regression coverage for complete and zero-solved-corner studies.
- Bumped package/runtime metadata to v0.51.0.

## v0.50 efficiency-chain power corner evidence — 2026-09-24

- Preserves each solved nonlinear uncertainty corner's existing fan-side power evidence instead of discarding it after the operating-point solve.
- Adds complete-study evaluated-corner ranges for fluid air power, shaft power, electrical input, and specific fan power.
- Adds tie-aware source-corner attribution for every available power-chain lower/upper extreme using the same active fan/system/duct input context as other extrema witnesses.
- Reports shaft power only with an explicit fan efficiency, and electrical input / specific fan power only with explicit fan, motor, and VFD efficiencies; no efficiency is inferred.
- Keeps efficiency values fixed in this workflow rather than silently treating them as uncertain inputs.
- Withholds complete power-chain ranges and extrema witnesses whenever any nonlinear uncertainty corner is unresolved.
- Adds standalone Markdown and engineering-dossier reporting plus regression coverage for exact source resolution, missing-efficiency behavior, indeterminate withholding, and dossier columns.
- Bumped package/runtime metadata to v0.50.0.

## v0.49 evaluated-corner air-power envelope and provenance — 2026-09-24

- Added fan air-power min/max across every solved nonlinear uncertainty corner in complete studies.
- Extends compact first-witness operating-point extrema and tie-aware source attribution to `air_power_kw`.
- Markdown uncertainty reports now surface nominal air power, bounded evaluated-corner air-power range, critical cases, and witness provenance.
- Engineering dossier uncertainty tables now include the complete-study air-power corner range.
- Keeps the result explicitly bounded to evaluated corners: no continuous interior extremum, equipment efficiency, motor/VFD acceptance, or manufacturer guarantee is inferred from the corner range.
- Indeterminate studies continue to withhold the complete operating-point envelope, including air power.
- Added exact-corner regression coverage for air-power calculation, witnesses, reports, and dossier integration.
- Bumped package/runtime metadata to v0.49.0.

## v0.48 tie-aware internal edge-flow extrema provenance — 2026-09-24

- Added tie-aware source attribution for every internal edge-airflow lower/upper extremum in complete nonlinear uncertainty studies.
- Each edge extremum now preserves every evaluated corner sharing the same extreme value, including fixed pressure, fan speed/scenario, fan-point overrides, and duct physical/geometry overrides.
- Retains the existing compact first-witness edge corner indices for backward-compatible direct lookup.
- Keeps edge extrema-source evidence conditional on a complete study; indeterminate studies continue to emit neither complete edge-flow ranges nor fabricated edge witnesses.
- Markdown reports now include an internal edge-airflow witness-provenance table.
- Added regression coverage for exact source-corner resolution, tied whole-curve scenarios, report output, and indeterminate withholding.
- Bumped package/runtime metadata to v0.48.0.

## v0.47 uncertainty corner outcome diagnostics — 2026-09-24

- Added deterministic status accounting across every evaluated nonlinear fan/variable-friction uncertainty corner.
- Records solver termination-reason counts directly from each corner's existing solver diagnostics.
- Adds exact unresolved corner indices plus their fixed-pressure, fan-speed/scenario, fan-point, and duct uncertainty input context.
- Keeps unresolved-corner evidence diagnostic only: indeterminate studies still emit no complete operating-point or internal edge-flow envelope.
- Markdown reports now surface status/termination summaries and a compact unresolved-corner table.
- Added regression coverage for both all-solved accounting and indeterminate corner traceability.
- Bumped package/runtime metadata to v0.47.0.

## v0.46 uncertainty envelope witness provenance — 2026-09-23

- Added exact evaluated-corner witnesses for nonlinear uncertainty operating-point minima and maxima.
- Preserves the compact zero-based first-witness corner index/value for each airflow, fan-pressure, and system-pressure envelope bound.
- Adds tie-aware `operating_point_extrema_sources` evidence that records every evaluated corner sharing an extremum, including its fixed pressure, configured fan speed/scenario, and any active fan-point or duct physical/geometry overrides.
- Extended every internal edge-airflow range with the exact lower/upper corner indices that produced those extrema.
- Keeps all witness evidence conditional on a complete envelope; indeterminate analyses do not fabricate extreme-case attribution.
- Markdown uncertainty reports now include an envelope-witness provenance table and internal edge-airflow witness table, while JSON retains direct indices into the full corner evidence array.
- Added regression coverage that resolves every operating-point and edge-flow witness back to the exact reported corner value and verifies the richer source attribution.
- Bumped package/runtime metadata to v0.46.0.

## v0.45 correlated whole fan-curve scenarios — 2026-09-23

- Added explicit named whole fan-curve scenarios to nonlinear fan/variable-friction uncertainty analysis so point-to-point dependence can be preserved instead of forcing independent Cartesian point perturbations.
- Evaluates the nominal supplied curve plus each configured scenario as complete curves, crossed only with the configured fixed-pressure, fan-speed, and duct physical/geometry uncertainty dimensions.
- Allows whole-curve scenarios to combine with bounded fan-speed ratio using the existing affinity-law transform before each complete nonlinear loop solve.
- Makes whole-curve scenarios mutually exclusive with independent fan-point pressure/airflow-coordinate bounds, preventing accidental mixing of correlated and independent fan-performance models.
- Validates scenario fan curves through the existing nonnegative, strictly increasing airflow and non-increasing pressure requirements; rejects duplicate names and reserves `nominal` for the baseline curve.
- Includes scenario count in the pre-materialization `max_corner_cases` guard, preserves per-scenario provenance, reports scenario identity in Markdown/JSON corner evidence, and adds standalone plus dossier regression coverage.
- Added `examples/fan_variable_friction_curve_scenarios_demo.json` and bumped package/runtime metadata to v0.45.0.

## v0.44 bounded fan-speed ratio uncertainty — 2026-09-23

- Added an optional user-supplied fan speed-ratio interval to nonlinear fan/variable-friction corner analysis.
- Builds each bounded reference fan curve from configured point-pressure/airflow-coordinate bounds, then reuses the existing CleanroomX affinity-law transform before solving the complete nonlinear loop.
- Scales airflow with speed ratio and pressure with speed ratio squared while preserving the transformed supplied-data range and strict no-extrapolation behavior.
- Keeps the new input fully opt-in so legacy uncertainty studies retain their prior fan-curve naming, provenance completeness, corner counts, and solver behavior when no speed ratio is configured.
- Rejects speed-ratio intervals whose lower bound is not strictly positive and includes configured speed bounds in the pre-materialization corner-limit check.
- Added JSON loading, Markdown corner evidence, a reproducible speed-uncertainty example, and regression coverage.
- Bumped package/runtime metadata to v0.44.0.

## v0.43 bounded fan-curve airflow-coordinate uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to user-supplied absolute airflow-coordinate bounds at selected supplied fan-curve point indices.
- Keeps nominal airflow coordinates single-sourced in the supplied fan curve; uncertainty entries identify an existing zero-based point index and provide only an absolute airflow bound plus optional provenance.
- Combines fan-airflow corners with fan-pressure, fixed-pressure, and duct physical/geometry uncertainty dimensions, then re-solves the complete nonlinear Darcy-friction network at every corner.
- Rejects negative airflow intervals, unknown/duplicate point indices, repeated nominal airflow values, and any interval combination capable of producing non-increasing supplied airflow coordinates.
- Preserves strict supplied fan-curve range behavior: no extrapolation is introduced, and unresolved corners suppress a complete envelope.
- Added Markdown evidence, a reproducible airflow-coordinate uncertainty example, provenance tracking, regression coverage, and package metadata alignment.
- Enforces `max_corner_cases` before materializing any Cartesian products, preventing rejected high-dimensional studies from allocating oversized intermediate combination lists.
- Bumped package/runtime metadata to v0.43.0.

## v0.42 bounded fan-curve point pressure uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to user-supplied absolute pressure bounds at selected supplied fan-curve airflow points.
- Keeps nominal point pressure single-sourced in the fan curve; uncertainty entries identify an existing airflow coordinate and provide only an absolute pressure bound plus optional provenance.
- Combines fan-pressure corners with fixed-pressure and duct physical/geometry uncertainty dimensions, then re-solves the complete nonlinear Darcy-friction network at every corner.
- Rejects negative pressure intervals, unknown/duplicate airflow-point references, repeated nominal pressures, and any interval combination capable of making pressure increase with airflow.
- Preserves the supplied airflow coordinates and strict no-extrapolation fan boundary.
- Added Markdown evidence, a reproducible fan-curve uncertainty example, provenance tracking, and regression coverage.
- Bumped package/runtime metadata to v0.42.0.

## v0.41 bounded rectangular duct-geometry uncertainty — 2026-09-23

- Preserves explicit circular diameter and rectangular width/height in geometry-derived loop-resistance evidence.
- Extends nonlinear fan/variable-friction corner analysis to user-supplied absolute rectangular width and height bounds.
- Rebuilds rectangular area, hydraulic diameter, Reynolds/friction evidence, and resistance at every geometry corner before each complete nonlinear fan/network solve.
- Rejects shape-mismatched dimension bounds, nonpositive dimensional intervals, repeated nominal values, and geometry corners whose minimum hydraulic diameter would not exceed the maximum bounded roughness.
- Added per-corner rectangular dimension evidence, Markdown reporting, a reproducible rectangular example, and regression coverage.
- Bumped package/runtime metadata to v0.41.0.

## v0.40 bounded nonlinear duct-geometry uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to user-supplied absolute bounds on automatic-friction duct length and circular-duct diameter.
- Rebuilds affected duct geometry and Darcy evidence at every geometry corner before every complete nonlinear fan/network solve; no fixed-equivalent-resistance shortcut is introduced.
- Keeps nominal geometry single-sourced in loop-network evidence and rejects repeated nominal values in uncertainty blocks.
- Rejects nonpositive bounded lengths/diameters and diameter ranges that would make the maximum bounded roughness reach or exceed the minimum bounded diameter.
- Keeps rectangular width/height uncertainty outside scope because current stored rectangular evidence does not preserve an unambiguous dimension orientation.
- Added interval/provenance reporting, per-corner geometry evidence, Markdown output, a reproducible geometry example, and regression coverage.
- Bumped package/runtime metadata to v0.40.0.

## v0.39 bounded physical Darcy-input uncertainty — 2026-09-23

- Extended nonlinear fan/variable-friction corner analysis to user-supplied absolute bounds on automatic-friction edge roughness, kinematic viscosity, and air density while retaining fixed-pressure and local-loss K uncertainty.
- Rebuilds affected duct-geometry evidence at every physical-input corner before every complete nonlinear fan/network solve; no frozen equivalent-resistance shortcut is introduced.
- Keeps nominal physical values single-sourced in loop-network geometry and rejects repeated nominals in uncertainty blocks.
- Rejects nonphysical bounded intervals: negative roughness/local K, nonpositive viscosity/density, and roughness reaching the hydraulic diameter.
- Added per-corner physical-input evidence, interval/provenance reporting, Markdown output, a reproducible physical-input example, and regression coverage.
- Replaced the stale duplicate uncertainty-model definition with a compatibility re-export of the canonical study model.
- Bumped package/runtime metadata to v0.39.0.

## v0.38 dossier-integrated nonlinear fan / loop uncertainty — 2026-09-23

- Integrated v0.37 fan/variable-friction loop uncertainty analyses into engineering dossier manifests.
- Added SHA-256 source fingerprints, executive-summary analysis/corner counts, full JSON evidence retention, and Markdown corner-envelope reporting.\n- Extended HVAC-to-fan operating-airflow consistency to every evaluated nonlinear uncertainty corner; unresolved corners remain `not_comparable` and never receive fabricated airflow values.
- Propagates indeterminate nonlinear uncertainty analyses into dossier attention while tracking missing uncertainty provenance separately as unresolved traceability.
- Extends optional HVAC/fan operating-airflow consistency to every evaluated nonlinear uncertainty corner; unresolved or non-converged corners remain not comparable.
- Preserves the v0.37 numerical boundary: every corner still uses the complete nonlinear Darcy-friction fan/loop solver, and unresolved corners never produce a complete envelope.
- Added a reproducible dossier manifest plus end-to-end, adverse-state, missing-provenance, missing-source, and deterministic-output regression coverage.
- Bumped package/runtime metadata to v0.38.0.

## v0.37 nonlinear fan / variable-friction uncertainty — 2026-09-23

- Added deterministic bounded corner analysis around the v0.33 nonlinear fan/variable-friction loop solver.
- Supports explicit absolute uncertainty on fixed system pressure and selected automatic-friction duct local-loss coefficients without duplicating nominal K values outside the loop geometry.
- Rebuilds affected geometry-edge evidence and re-solves the complete Darcy-friction network at every bounded fan/system evaluation for every corner.
- Preserves strict supplied-range fan behavior; no-intersection and numerical non-convergence make the uncertainty result indeterminate and suppress complete operating-point/edge-flow envelopes.
- Tracks fan-curve, fixed-pressure, and local-loss uncertainty provenance separately from numerical solution status.
- Deduplicates zero-width uncertainty dimensions and enforces an explicit max_corner_cases limit instead of silently truncating combinations.
- Added JSON loading, Markdown/JSON reporting, the cleanroomx-fan-loop-friction-uncertainty CLI, reproducible example data, documentation, and regression coverage.
- Bumped package/runtime metadata to v0.37.0.

## v0.36 nonlinear-network validation hardening — 2026-09-23

- Added pre-solve validation for every loop edge identified as automatic Darcy-friction geometry.
- Requires complete stored geometry, density/local-loss, roughness, kinematic-viscosity, positive reference-airflow, hydraulic-diameter/area, and positive stored friction-factor evidence.
- Reconstructs the stored automatic-friction calculation at the declared reference airflow before iteration so malformed provenance cannot be hidden by a near-zero-flow freeze.
- Added regression coverage for incomplete, zero, NaN, and infinite stored automatic-friction evidence.
- Retains intentional parallel physical paths; existing connected-graph, self-loop, injection-balance, two-terminal fan-boundary, and finite solver-control validation remains unchanged.
- Bumped package/runtime metadata to v0.36.0.

## v0.35 dossier-integrated nonlinear fan / loop workflows — 2026-09-23

- Integrated v0.33 fan/variable-friction loop studies and v0.34 fan-speed/variable-friction loop studies into dossier manifests.
- Added SHA-256 source fingerprints, full JSON evidence retention, executive-summary counts, and Markdown solver diagnostics for both nonlinear workflow families.
- Propagates both bounded no-intersection and numerical `non_converged` cases into dossier attention; numerical non-convergence is never reported as PASS.
- Extended HVAC-to-fan operating-airflow consistency to solved nonlinear loop and nonlinear speed cases while preserving unresolved/non-converged cases as not comparable.
- Added a combined reproducible dossier example plus end-to-end, deterministic-fingerprint, missing-source, adverse-state, and cross-consistency regression coverage.
- Bumped package/runtime metadata to v0.35.0.

## v0.34 fan-speed / variable-friction loop coupling — 2026-09-23

- Added explicit affinity-law fan-speed studies over the v0.33 bounded fan/variable-friction loop solver.
- Reuses `scale_fan_curve_for_speed` for every configured speed ratio; no fan-scaling equations are duplicated.
- Re-solves the complete loop and Darcy-friction closure at every transformed fan-curve point and bounded operating-point airflow.
- Preserves transformed fan-curve bounds with no extrapolation and reports solved, `no_intersection_in_supplied_range`, and `non_converged` states independently per speed.
- Reports optional rpm, operating airflow/pressure, signed network edge flows, Reynolds/friction evidence, resistance closure, continuity, edge-law residuals, and fan/system residuals.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-loop-friction-speed` CLI, example data, documentation, and fixed-resistance compatibility/non-convergence regression coverage.
- Bumped package and runtime metadata to v0.34.0.

## v0.33 bounded fan / variable-friction loop coupling — 2026-09-23

- Added direct coupling between supplied fan pressure/airflow data and the v0.30 variable-friction two-terminal loop solver.
- Re-solves the complete loop and updates automatic Darcy friction at every supplied fan point and every bounded operating-point bisection airflow instead of reducing the system to one fixed equivalent quadratic resistance.
- Preserves strict no-extrapolation behavior for fan data and reports `no_intersection_in_supplied_range` when no bounded crossing exists.
- Adds explicit `non_converged` results when variable-friction network closure or bounded operating-point iteration cannot satisfy configured limits; no fabricated operating point is emitted.
- Reports fan/system residuals, network continuity and edge-law residuals, Darcy resistance-closure evidence, iteration diagnostics, and fluid air power.
- Keeps explicit-resistance and user-supplied-friction edges fixed while iterating only geometry edges configured with roughness and kinematic viscosity.
- Added validated JSON solver controls, Markdown/JSON reporting, the `cleanroomx-fan-loop-friction` CLI, a reproducible example, focused regression tests, and engineering-boundary documentation.
- Added a fixed-resistance compatibility regression against the existing v0.26 fan/loop solver.
- Bumped package and runtime metadata to v0.33.0 while retaining the v0.32 dossier integrations.


## v0.32 dossier-integrated fan/loop uncertainty and speed studies — 2026-09-23

- Integrated bounded fan/loop-network uncertainty analyses into engineering dossier manifests with SHA-256 source fingerprints, executive summaries, Markdown reporting, and full JSON evidence preservation.
- Propagates indeterminate fan/loop uncertainty corners into dossier attention state while tracking missing uncertainty provenance separately as unresolved traceability.
- Integrated fan-speed/fixed-resistance-loop studies into dossier manifests with per-speed operating points, internal-network continuity evidence, fan/system residuals, and source fingerprints.
- Extended HVAC-to-fan operating-airflow consistency to fan-speed/loop-network cases; unresolved transformed-curve intersections remain not comparable rather than becoming failures.
- Added an end-to-end combined dossier example, missing-source and deterministic-fingerprint regression coverage, and adverse-state summary tests.
- Bumped package/runtime metadata to v0.32.0 without changing the underlying v0.29 or v0.31 numerical solvers.


## v0.31 bounded fan / loop-network uncertainty — 2026-09-23

- Added deterministic lower/upper corner analysis around the v0.26 passive two-terminal fan/loop-network workflow while preserving v0.29 fan-speed loop studies and v0.30 variable-friction loop solving.
- Supports explicit absolute uncertainty on fixed system pressure and on any named fixed loop-edge quadratic resistance without duplicating nominal resistance values outside the loop-network input.
- Rebuilds and solves every unique configured corner, derives each corner's equivalent loop resistance, intersects it with supplied fan data without extrapolation, and re-solves the complete loop when bounded.
- Reports operating-airflow/system-pressure and internal edge-flow min/max across evaluated corners only when the nominal case and every corner are solved; unresolved corners make the analysis `indeterminate`.
- Preserves adjusted-edge provenance and per-corner solver residuals; internal edge-flow corner ranges are diagnostic evaluated-corner evidence rather than claimed continuous-interval extrema.
- Deduplicates zero-width uncertainty dimensions and rejects analyses exceeding the explicit `max_corner_cases` limit (default 256) instead of silently truncating the uncertainty space.
- Tracks fan-curve, fixed-pressure, and configured edge-resistance uncertainty provenance separately from numerical solution status.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-loop-uncertainty` CLI, example data, documentation, and regression tests.
- Bumped package/runtime metadata to v0.31.0.

## v0.30 variable-friction loop solving — 2026-09-23

- Added an optional outer iteration around the validated fixed-resistance loop solver for geometry-derived edges configured with automatic Darcy friction.
- Recomputes Reynolds number and Darcy friction from each automatic edge's absolute solved airflow, then rebuilds the Darcy-Weisbach plus local-K quadratic resistance.
- Supports configurable resistance-closure tolerance, friction-factor update relaxation, outer-iteration limits, and inner mass-balance/Newton tolerances.
- Preserves direct resistance inputs and geometry edges with user-supplied friction factors as fixed.
- Explicitly freezes automatic-friction edges at configured near-zero airflow instead of inventing Reynolds or friction values at zero velocity.
- Preserves the existing circular laminar 64/Re and turbulent Colebrook model; noncircular automatic laminar flow remains rejected explicitly.
- Added edge-level target/used resistance closure evidence, iteration history, Markdown/JSON reporting, the cleanroomx-loop-friction CLI, example data, documentation, and regression tests.
- Bumped package/runtime metadata to v0.30.0 while preserving v0.29 fan-speed/loop studies.

## v0.29 bounded fan-speed / loop-network study — 2026-09-23

- Added explicit fan-speed sweeps over passive two-terminal fixed-resistance loop networks.
- Reused the existing affinity-law fan-curve transform and v0.26 bounded fan/loop-network solver for every speed case rather than introducing a second operating-point implementation.
- Re-solves the original mesh at each bounded operating airflow and reports signed edge flows, node pressures, continuity/pressure-law residuals, equivalent-network residual, and fan/system residual.
- Preserves no-intersection cases without fan-curve extrapolation and reports the overall study as attention-required when any configured speed case is unresolved.
- Added optional reference-rpm reporting, JSON/Markdown reporting, the `cleanroomx-fan-loop-speed` CLI, example data, documentation, CLI regression coverage, and v0.29.0 metadata.
- Keeps variable-friction iteration, inferred VFD limits, motor/drive limits, controls, leakage, system effect, stall/surge acceptance, transients, and manufacturer selection outside scope.

## v0.28 loop-workflow dossier integration — 2026-09-23

- Integrated v0.26 fan/loop-network studies into engineering dossier manifests with SHA-256 source fingerprints, executive component summaries, Markdown reporting, and unresolved-intersection attention tracking.
- Integrated v0.27 explicit loop damper-resistance scenario studies into the same dossier workflow with case counts and baseline solver-residual evidence.
- Extended dossier HVAC-to-fan operating-airflow consistency so solved fan/loop-network operating points participate alongside standalone fan/system, reference-flow fan/duct, passive parallel-network, and fan-speed cases.
- Preserved unsolved fan/loop studies as unresolved/not-comparable in airflow consistency rather than converting them into failures.
- Added end-to-end dossier and consistency regression coverage plus an integrated loop-workflow dossier example.
- Bumped package/runtime metadata to v0.28.0 without changing the underlying fan, loop-network, or damper physical models.

## v0.27 explicit loop damper-resistance scenarios — 2026-09-23

- Added deterministic loop-network scenario studies for explicit user-supplied edge resistance multipliers.
- Solves the unchanged baseline plus each named throttling case with the existing fixed-resistance loop solver.
- Restricts configured multipliers to finite values greater than or equal to 1.0, representing added/throttled quadratic resistance rather than inferred damper position.
- Reports per-case adjusted resistance evidence, edge-flow redistribution versus baseline, and continuity/pressure-law residuals.
- Preserves the underlying explicit or geometry-derived resistance provenance inside each adjusted-edge evidence record.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-damper-study` CLI, example data, documentation, regression tests, and v0.27.0 metadata.
- Keeps automatic balancing, actuator dynamics, damper K inference, control loops, leakage, and variable-friction iteration outside scope.

## v0.26 bounded fan / loop-network coupling — 2026-09-23

- Added two-terminal coupling between supplied fan curves and connected fixed-resistance loop networks.
- Derives an equivalent loop resistance from a reference through-flow solve, using the exact quadratic scaling of fixed `R·Q·|Q|` edges.
- Requires equal/opposite fan discharge and suction reference injections and zero external injection at every other node.
- Intersects `fixed_pressure + R_eq·Q²` with the supplied fan curve without extrapolation, then re-solves the original loop at the operating airflow.
- Reports reference and operating network evidence, signed edge flows, node pressures, continuity/pressure-law residuals, equivalent-network residual, and fan/system residual.
- Reuses v0.25 explicit or geometry-derived loop edges unchanged; geometry/reference-flow friction remains frozen at its declared basis.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-fan-loop` CLI, example data, documentation, and focused regression tests.
- Bumped package/runtime metadata to v0.26.0.

## v0.25 geometry-derived fixed loop resistance — 2026-09-23

- Added optional derivation of loop-edge quadratic resistance from explicit circular or rectangular duct geometry.
- Uses Darcy-Weisbach straight-duct friction plus an explicit local-loss coefficient: `R = 0.5·ρ·(fL/Dh + K)/A²`.
- Supports either a user-supplied Darcy friction factor or automatic friction from explicit roughness, kinematic viscosity, and reference airflow.
- Automatic friction is resolved once at the declared reference airflow; the derived resistance remains fixed during nonlinear loop balancing.
- Preserves explicit `resistance_pa_per_m3_s_squared` inputs unchanged and rejects ambiguous edges that provide both resistance sources.
- Adds resistance-basis and derivation evidence to JSON/Markdown loop reports.
- Added a geometry-derived loop example and regression coverage for circular/rectangular geometry, automatic friction, loader validation, reporting, and backward compatibility.
- Bumped package/runtime metadata to v0.25.0.

## v0.24 fan/system operating-point uncertainty — 2026-09-23

- Added deterministic bounded uncertainty analysis for user-supplied fixed system pressure and quadratic system resistance.
- Evaluates every unique lower/upper system-curve corner with the existing no-extrapolation fan/system solver.
- Reports a complete airflow/pressure operating-point envelope only when the nominal case and every bounded corner intersect the supplied fan curve; otherwise the analysis remains `indeterminate`.
- Keeps air power as nominal/corner evidence rather than labeling corner extrema as a conservative power envelope, because `Q × ΔP` can have an interior extremum along a fan-curve segment.
- Added fan-curve and system-input provenance tracking, Markdown/JSON reporting, the `cleanroomx-fan-uncertainty` CLI, example data, documentation, and regression tests.
- Integrated fan/system uncertainty into engineering dossiers with SHA-256 source traceability, attention-state handling, and missing-provenance tracking.
- Bumped package/runtime metadata to v0.24.0 while preserving v0.23.1 loop-network hardening.

## v0.23.1 loop-network injection-balance hardening — 2026-09-23

- Tightened loop-network global node-injection validation to a fixed absolute tolerance of 1e-6 m³/h.
- Removed flow-magnitude-relative scaling that could admit a materially nonzero net source/sink mismatch in very large-flow inputs.
- Added regression coverage proving a 0.1 m³/h imbalance is rejected even when opposing node flows are near 1e9 m³/h.
- Bumped package/runtime metadata to v0.23.1.

## v0.23 fixed-resistance looped airflow networks — 2026-09-23

- Added a connected steady-state pressure-node solver for airflow networks with arbitrary loops.
- Uses explicit fixed quadratic edge laws `ΔP = R·Q·|Q|` and balanced user-supplied node injections.
- Added spanning-tree initialization plus damped Newton/backtracking for nonlinear node-continuity solution.
- Reports signed reverse flow, relative node pressures, per-node mass-balance residuals, and per-edge pressure-law residuals.
- Validates finite positive resistances, balanced injections, unique edge names, valid node references, and graph connectivity.
- Added JSON loading, Markdown/JSON reporting, the `cleanroomx-loop-flow` CLI, example data, engineering-scope documentation, and regression tests.
- Preserves v0.21 automatic Darcy-friction screening and v0.22 dossier airflow-consistency work; looped networks remain explicit fixed-resistance models.
- Keeps looped-network geometry/friction inference, leakage, dampers, controls, fan coupling, compressibility, and transient behavior outside this bounded solver.
- Bumped package/runtime metadata to v0.23.0.

## v0.22 HVAC / fan operating-airflow consistency — 2026-09-23

- Added dossier-integrated comparison of HVAC total governing airflow against standalone fan/system, reference-flow fan/duct, passive parallel-network, and fan-speed operating points.
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
