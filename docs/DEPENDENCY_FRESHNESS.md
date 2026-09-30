# Engineering dependency freshness

CleanroomX models evidence freshness with an explicit revision dependency graph.
The graph records only dependencies supplied by the calling workflow; it does not
infer scientific causality merely because analyses coexist in one project.

## States

Each node resolves to one of five states:

- `current`: the node is valid and every declared dependency is present at the
  exact revision recorded by the node.
- `stale`: at least one otherwise-resolved dependency is historical, stale, or
  now has a different revision.
- `historical`: the node is explicitly retained as historical evidence.
- `unresolved`: the node or one of its required dependencies does not currently
  resolve to valid revision evidence.
- `invalid`: the node's own integrity evidence is invalid.

Unresolved evidence takes precedence over stale evidence when both conditions
occur in one dependency closure. The model does not manufacture missing
revisions or silently promote incomplete evidence to `current`.

## Graph integrity

Self-dependencies and dependency cycles are rejected. Cycle validation is
deterministic and uses an explicit traversal stack, so a valid deep graph is not
limited by Python's recursion depth. Cycle diagnostics preserve the discovered
dependency path.

## Scale and determinism

For one fixed graph, acyclicity validation builds the adjacency map once and
traverses nodes and declared edges iteratively. Freshness resolution memoizes
resolved states across a complete `states()` or `snapshot()` call, avoiding
repeated full-chain traversal for every node. Snapshot nodes and dependency
bindings remain deterministically ordered.

The implementation is therefore linear in graph nodes plus declared edges for
one validation or complete state-resolution pass, aside from deterministic key
sorting used for stable output.

## Scope boundary

This graph is lifecycle bookkeeping, not an engineering solver. It answers
whether explicitly declared evidence dependencies still match their bound
revisions. It does not infer which analyses should depend on one another,
recalculate stale analyses automatically, or turn a freshness state into a
compliance verdict.
