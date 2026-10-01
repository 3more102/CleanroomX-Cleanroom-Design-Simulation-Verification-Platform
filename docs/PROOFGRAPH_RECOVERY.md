# Particle recovery ProofGraph commissioning adapter

This Release 3 slice projects the existing measured particle-recovery workflow
into the canonical ProofGraph model without creating another recovery solver or
another acceptance rule.

## Authority boundary

The adapter calls `analyze_recovery_test` once and preserves its canonical
criterion status. It does not infer ISO cleanroom limits, a recovery-time
requirement, uncertainty allowance, or an interpolation rule.

The explicit project inputs remain authoritative:

- particle size;
- target concentration;
- optional maximum recovery time;
- measured time/concentration samples;
- supplied absolute concentration uncertainty;
- instrument identity;
- sample location;
- occupancy state;
- method/protocol reference.

## Commissioning evidence

Each measured sample becomes `CommissioningEvidence` containing the exact
nominal concentration, supplied uncertainty, bounded lower/upper interval,
sample time, and canonical relation to the configured target.

The log-linear fit remains diagnostic only. Its fitted crossing time and
effective ACH are not used as acceptance evidence.

## Fail-closed traceability

A canonical PASS, FAIL, or INDETERMINATE is promoted to the same ProofGraph
verdict only when the recovery record identifies all of:

- instrument ID;
- sample location;
- method/protocol reference.

If any of those fields is missing, ProofGraph records the canonical status in
verification-run metadata but emits `unknown` as the auditable verdict.

A canonical `incomplete` result maps to ProofGraph `unknown`.
A canonical `not_checked` result remains `not_checked`.

This preserves the distinction between a numerical screening result and a
traceable commissioning verdict.

## Scope

The adapter does not establish cleanroom certification, commissioning/TAB
acceptance, calibration validity, regulatory compliance, or completeness of an
external standard. Those remain governed by the applicable project procedures,
licensed standards, calibrated instrumentation, and qualified engineering
judgment.
