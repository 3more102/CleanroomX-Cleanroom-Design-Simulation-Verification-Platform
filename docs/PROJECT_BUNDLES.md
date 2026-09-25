# Portable Project Bundles

CleanroomX portable project bundles package a desktop project together with every external analysis input currently registered by the application layer. The feature is intended for reproducible handoff, review, archival, and transfer between workstations without leaving consistency or dossier inputs behind.

## Format

A bundle uses the `.cleanroomx.zip` extension and contains only:

- `manifest.json` — bundle schema/version plus SHA-256 and byte-size integrity records;
- `project.cleanroomx.json` — the normal CleanroomX schema-v1 project document;
- `dependencies/...` — deduplicated external input files referenced by consistency and dossier analyses.

The bundled project is a copy. Its external references are rewritten to relative paths under `dependencies/`; the live project in memory and the original saved project are not modified.

The bundle format is `cleanroomx.project-bundle`, schema version 1. Project schema version 1 remains unchanged.

## Integrity and determinism

Export uses the existing application dependency registry instead of a second list of path-bearing fields. Each dependency is fingerprinted before packaging and hashed again while it is copied. If a source disappears or changes during export, the bundle is not published.

All entries use stored ZIP members with fixed metadata and deterministic ordering. Repeating an export from identical project/dependency bytes produces identical bundle bytes.

Verification rejects:

- invalid or unsupported bundle schemas;
- duplicate or undeclared archive members;
- absolute paths, parent traversal, Windows drive-style path components, and backslash paths;
- encrypted or unexpectedly compressed members;
- project/dependency size or SHA-256 mismatches;
- invalid bundled project JSON or unsupported project schemas;
- project references that are not represented by the manifest;
- manifest references that do not exist in the bundled project.

## Transactional extraction

Extraction never uses `ZipFile.extractall()`. The bundle is fully verified first, then every expected member is copied into a private sibling staging directory and re-hashed while copying. The final directory is published with a single rename only after the extracted project can be loaded successfully.

The destination must be new or empty. Existing non-empty directories are never merged with or overwritten.

## Desktop workflow

Use **File → Export Portable Project Bundle...** to package the current project. Relative external references require a saved project (or a restored project with a known source location) so CleanroomX has an unambiguous base directory.

Use **File → Open Portable Project Bundle...** to choose a bundle and a parent directory. CleanroomX extracts it into a child directory named from the bundle and opens the extracted project.

## CLI

```bash
cleanroomx-project-bundle export project.cleanroomx.json review.cleanroomx.zip
cleanroomx-project-bundle verify review.cleanroomx.zip
cleanroomx-project-bundle extract review.cleanroomx.zip ./review
```

Commands print strict JSON on success and return exit code 2 with an actionable error on invalid/corrupt bundles, missing/changing dependencies, or unsafe extraction conditions.

## Scope and limitations

The packager follows the application registry's external dependency references. In v0.100, those are the file-backed consistency and dossier workflows. Inline analysis inputs need no additional files. The feature does not embed arbitrary paths found in free-form metadata, reports, credentials, or unrelated files.

Portable bundles are not a replacement for project revision control or long-term backup policy. They preserve the exact packaged bytes and their integrity evidence; they do not claim that the engineering inputs themselves are correct or approved.
