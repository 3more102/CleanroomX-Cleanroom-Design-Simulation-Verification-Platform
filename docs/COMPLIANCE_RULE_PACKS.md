# Compliance rule packs

CleanroomX provides a deterministic rule-pack foundation for comparing explicit project evidence against explicit acceptance criteria.

The rule-pack engine does **not** embed proprietary standards text or infer hidden numerical limits from a cleanroom class. Rule packs are intended for criteria that the project team is authorized to use, such as licensed standard-derived requirements, public authoritative requirements, user-entered URS criteria, owner standards, or project specifications.

## Versioned rule-pack identity

A rule pack uses:

- schema \`cleanroomx.compliance-rule-pack\`;
- schema version \`1\`;
- a stable pack \`id\`;
- an explicit pack \`version\`;
- a human-readable \`title\`;
- a declared \`source\`;
- uniquely identified rules.

Every analysis result records the normalized rule-pack identity and a canonical SHA-256 digest so later evidence can be tied to the exact criteria evaluated.

## Supported deterministic operators

The initial engine supports:

- \`exists\`;
- \`equals\`;
- \`min\`;
- \`max\`;
- \`range\`;
- \`one_of\`.

Evidence is addressed with RFC 6901 JSON Pointer paths. Numeric tolerances are explicit absolute tolerances; no implicit tolerance is added by the software.

## Evidence semantics

A present value is evaluated as pass or fail. A missing evidence path is \`not_checked\`, never silently promoted to pass.

Aggregate status is:

- \`pass\` when every rule passes;
- \`fail\` when one or more rules fail;
- \`pass_with_unchecked\` when no rule fails but some evidence is missing;
- \`not_checked\` when all rule evidence is missing.

Each finding retains rule identity, evidence path, operator, expected value, actual value, delta where meaningful, unit, tolerance, source, and reference.

## Regulatory boundary

A CleanroomX rule-pack result evaluates only the supplied evidence against the supplied criteria. It is not by itself a regulatory approval, cleanroom certification, commissioning/TAB acceptance, or proof that the supplied pack completely represents an external standard.

The repository intentionally does not ship copyrighted standards clauses or universal numerical cleanroom limits. See [Standards and source policy](STANDARDS.md).
