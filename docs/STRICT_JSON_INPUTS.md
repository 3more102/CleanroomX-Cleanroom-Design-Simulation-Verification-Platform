# Strict JSON file input safety

CleanroomX file-backed engineering loaders share the canonical
`load_strict_json()` boundary.

## Resource ceiling

Ordinary strict-JSON engineering inputs are limited to 64 MiB before JSON
parsing. The canonical reader also performs a bounded read, so a file that
grows after the initial metadata check cannot force an unbounded allocation.
The desktop **Import Analysis Input JSON** workflow uses this same boundary,
including the 64 MiB ceiling, before rebasing any file references from the
selected source directory into the active project context.

Specialized formats with their own documented limits, such as normal project
documents, assurance snapshots, portable bundles, and IFC sources, retain
their dedicated limits.

## Revision stability

The reader opens the input in binary mode and compares the opened file revision
before and after the bounded read with the path revision observed immediately
afterwards. A size, modification-time, or file-identity change fails closed
instead of parsing bytes from a path that changed during ingestion.

UTF-8 decoding, duplicate-key rejection, non-finite-number rejection, and
nesting handling continue through the existing strict JSON parser. These are
input-safety controls; they do not change engineering equations, tolerances,
units, or acceptance criteria.
