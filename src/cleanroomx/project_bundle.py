from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Callable
import zipfile

from . import __version__
from .application import (
    _external_dependency_references,
    _resolve_relative,
    _stable_file_fingerprint,
)
from .persistence import atomic_write_generated
from .project import (
    ProjectDocument,
    ProjectFormatError,
    _project_document_text,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
    project_from_dict,
)


PROJECT_BUNDLE_SCHEMA = "cleanroomx.project-bundle"
PROJECT_BUNDLE_SCHEMA_VERSION = 1
PROJECT_BUNDLE_MANIFEST = "manifest.json"
PROJECT_BUNDLE_PROJECT = "project.cleanroomx.json"
_DEPENDENCY_DIRECTORY = "dependencies"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FIELD_INDEX_RE = re.compile(r"^([^\[\]]+)\[(\d+)\]$")
_COPY_CHUNK_SIZE = 1024 * 1024


class ProjectBundleError(ValueError):
    """Raised when a portable project bundle is incomplete, unsafe, or corrupted."""


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_archive_path(value: str, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ProjectBundleError(f"{field} must be a safe relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ProjectBundleError(f"{field} must be a safe relative POSIX path")
    if any(":" in part for part in path.parts):
        raise ProjectBundleError(f"{field} contains an unsafe path component")
    return path


def _dependency_filename(index: int, source: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", source.name).strip(".-")
    if not stem:
        stem = "dependency.json"
    if len(stem) > 120:
        suffix = source.suffix[:20]
        keep = max(1, 120 - len(suffix))
        stem = stem[:keep] + suffix
    return f"{_DEPENDENCY_DIRECTORY}/{index:04d}-{stem}"


def _set_reference(payload: dict, field: str, value: str) -> None:
    match = _FIELD_INDEX_RE.fullmatch(field)
    if match is None:
        if field not in payload:
            raise ProjectBundleError(f"dependency field disappeared while packaging: {field}")
        payload[field] = value
        return
    key, raw_index = match.groups()
    items = payload.get(key)
    index = int(raw_index)
    if not isinstance(items, list) or index >= len(items):
        raise ProjectBundleError(f"dependency field disappeared while packaging: {field}")
    items[index] = value


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _write_zip_bytes(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    archive.writestr(_zip_info(name), data)


def _copy_dependency(
    archive: zipfile.ZipFile,
    archive_path: str,
    source: Path,
    *,
    expected_sha256: str,
    expected_size: int,
) -> None:
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as src, archive.open(
        _zip_info(archive_path), mode="w", force_zip64=True
    ) as dst:
        for chunk in iter(lambda: src.read(_COPY_CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
            dst.write(chunk)
    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise ProjectBundleError(
            f"dependency changed while portable bundle was being written: {source}"
        )


def _build_portable_project(
    project: ProjectDocument,
    *,
    source_base: Path | None,
) -> tuple[ProjectDocument, list[dict[str, Any]], dict[str, Path]]:
    portable = copy.deepcopy(project)
    project_from_dict(portable.to_dict())

    source_to_record: dict[str, dict[str, Any]] = {}
    archive_to_source: dict[str, Path] = {}

    for analysis in portable.analyses:
        for field, declared_path in _external_dependency_references(
            analysis.kind, analysis.input
        ):
            try:
                source = _resolve_relative(source_base, declared_path)
            except ValueError as exc:
                raise ProjectBundleError(
                    f"analysis {analysis.id!r} uses relative dependency {declared_path!r}; "
                    "save the project first or provide a source base directory"
                ) from exc
            source = source.expanduser().resolve(strict=False)
            if not source.is_file():
                raise ProjectBundleError(
                    f"analysis {analysis.id!r} dependency does not exist or is not a file: "
                    f"{declared_path}"
                )

            source_key = os.path.normcase(str(source))
            record = source_to_record.get(source_key)
            if record is None:
                archive_path = _dependency_filename(len(source_to_record) + 1, source)
                try:
                    fingerprint = _stable_file_fingerprint(source)
                except (OSError, RuntimeError) as exc:
                    raise ProjectBundleError(
                        f"dependency is unavailable or changing while packaging: {source}"
                    ) from exc
                record = {
                    "path": archive_path,
                    "size_bytes": fingerprint["size_bytes"],
                    "sha256": fingerprint["sha256"],
                    "references": [],
                }
                source_to_record[source_key] = record
                archive_to_source[archive_path] = source

            record["references"].append(
                {"analysis_id": analysis.id, "field": field}
            )
            _set_reference(analysis.input, field, record["path"])

    records = sorted(source_to_record.values(), key=lambda item: item["path"])
    for record in records:
        record["references"] = sorted(
            record["references"],
            key=lambda item: (item["analysis_id"], item["field"]),
        )
    return portable, records, archive_to_source


def export_project_bundle(
    path: str | Path,
    project: ProjectDocument,
    *,
    source_base: str | Path | None = None,
    source_project_path: str | Path | None = None,
    before_replace: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Create an atomic, deterministic, self-contained portable project bundle."""
    destination = Path(path).expanduser()
    destination_resolved = destination.resolve(strict=False)
    if source_project_path is not None:
        protected_project = Path(source_project_path).expanduser().resolve(strict=False)
        if os.path.normcase(str(destination_resolved)) == os.path.normcase(
            str(protected_project)
        ):
            raise ProjectBundleError(
                "portable bundle destination cannot overwrite the source project"
            )
    base = None if source_base is None else Path(source_base).expanduser().resolve(strict=False)
    portable, dependencies, archive_to_source = _build_portable_project(
        project, source_base=base
    )
    destination_key = os.path.normcase(str(destination_resolved))
    if any(
        os.path.normcase(str(source.resolve(strict=False))) == destination_key
        for source in archive_to_source.values()
    ):
        raise ProjectBundleError(
            "portable bundle destination cannot overwrite a packaged dependency"
        )
    project_bytes = _project_document_text(portable).encode("utf-8")
    manifest = {
        "schema": PROJECT_BUNDLE_SCHEMA,
        "schema_version": PROJECT_BUNDLE_SCHEMA_VERSION,
        "cleanroomx_version": __version__,
        "project": {
            "path": PROJECT_BUNDLE_PROJECT,
            "size_bytes": len(project_bytes),
            "sha256": _sha256_bytes(project_bytes),
        },
        "dependencies": dependencies,
    }
    manifest_bytes = _canonical_json_bytes(manifest)

    def generate_bundle(temp_path: Path) -> None:
        with zipfile.ZipFile(
            temp_path,
            mode="w",
            compression=zipfile.ZIP_STORED,
            allowZip64=True,
        ) as archive:
            archive.comment = b""
            _write_zip_bytes(archive, PROJECT_BUNDLE_MANIFEST, manifest_bytes)
            _write_zip_bytes(archive, PROJECT_BUNDLE_PROJECT, project_bytes)
            for dependency in dependencies:
                archive_path = dependency["path"]
                _copy_dependency(
                    archive,
                    archive_path,
                    archive_to_source[archive_path],
                    expected_sha256=dependency["sha256"],
                    expected_size=dependency["size_bytes"],
                )

    atomic_write_generated(
        destination,
        generate_bundle,
        before_replace=before_replace,
    )

    fingerprint = _stable_file_fingerprint(destination.resolve(strict=False))
    return {
        "bundle_path": str(destination),
        "bundle_sha256": fingerprint["sha256"],
        "bundle_size_bytes": fingerprint["size_bytes"],
        "project_name": portable.name,
        "dependency_count": len(dependencies),
        "dependency_bytes": sum(item["size_bytes"] for item in dependencies),
    }


def export_project_bundle_from_path(
    project_path: str | Path,
    bundle_path: str | Path,
) -> dict[str, Any]:
    source = Path(project_path).expanduser().resolve(strict=False)
    project, revision = load_project_document_with_revision(source)

    def assert_source_unchanged() -> None:
        try:
            current = capture_project_file_revision(source)
        except OSError as exc:
            raise ProjectBundleError(
                f"source project became unavailable while packaging: {source}"
            ) from exc
        if not project_file_revision_matches(revision, current):
            raise ProjectBundleError(
                f"project changed while portable bundle was being created: {source}"
            )

    return export_project_bundle(
        bundle_path,
        project,
        source_base=source.parent,
        source_project_path=source,
        before_replace=assert_source_unchanged,
    )


def _load_manifest(
    archive: zipfile.ZipFile,
) -> tuple[dict[str, Any], bytes]:
    try:
        info = archive.getinfo(PROJECT_BUNDLE_MANIFEST)
    except KeyError as exc:
        raise ProjectBundleError("bundle manifest is missing") from exc
    if info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 0x1:
        raise ProjectBundleError("bundle manifest must be stored and unencrypted")
    if info.file_size > 1024 * 1024:
        raise ProjectBundleError("bundle manifest is unexpectedly large")
    try:
        raw_bytes = archive.read(info)
        raw = raw_bytes.decode("utf-8")
        data = json.loads(
            raw,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ProjectBundleError(
                    f"non-finite JSON constant is not allowed in bundle manifest: {value}"
                )
            ),
        )
    except UnicodeDecodeError as exc:
        raise ProjectBundleError("bundle manifest is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ProjectBundleError(
            f"invalid bundle manifest JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(data, dict):
        raise ProjectBundleError("bundle manifest must be a JSON object")
    return data, raw_bytes


def _validated_integrity_record(
    value: Any,
    *,
    field: str,
) -> tuple[str, int, str]:
    if not isinstance(value, dict):
        raise ProjectBundleError(f"{field} must be an object")
    archive_path = str(_safe_archive_path(value.get("path"), field=f"{field}.path"))
    size = value.get("size_bytes")
    digest = value.get("sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ProjectBundleError(f"{field}.size_bytes must be a non-negative integer")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise ProjectBundleError(f"{field}.sha256 must be a lowercase SHA-256 digest")
    return archive_path, size, digest


def _hash_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with archive.open(info, mode="r") as stream:
        for chunk in iter(lambda: stream.read(_COPY_CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _verify_member(
    archive: zipfile.ZipFile,
    archive_path: str,
    expected_size: int,
    expected_sha256: str,
) -> None:
    try:
        info = archive.getinfo(archive_path)
    except KeyError as exc:
        raise ProjectBundleError(f"bundle member is missing: {archive_path}") from exc
    if info.compress_type != zipfile.ZIP_STORED:
        raise ProjectBundleError(
            f"bundle member uses unsupported compression: {archive_path}"
        )
    if info.flag_bits & 0x1:
        raise ProjectBundleError(f"encrypted bundle member is not supported: {archive_path}")
    if info.file_size != expected_size:
        raise ProjectBundleError(f"bundle member size mismatch: {archive_path}")
    actual_size, actual_sha256 = _hash_member(archive, info)
    if actual_size != expected_size or actual_sha256 != expected_sha256:
        raise ProjectBundleError(f"bundle member integrity check failed: {archive_path}")


def _read_project_member(
    archive: zipfile.ZipFile,
    archive_path: str,
) -> ProjectDocument:
    try:
        text = archive.read(archive_path).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectBundleError("bundled project is not UTF-8") from exc
    try:
        data = json.loads(
            text,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ProjectFormatError(f"non-finite JSON constant is not allowed: {value}")
            ),
        )
        return project_from_dict(data)
    except (json.JSONDecodeError, ProjectFormatError) as exc:
        raise ProjectBundleError(f"bundled project is invalid: {exc}") from exc


def _manifest_reference_set(dependencies: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    references: set[tuple[str, str, str]] = set()
    for index, dependency in enumerate(dependencies):
        refs = dependency.get("references")
        if not isinstance(refs, list):
            raise ProjectBundleError(
                f"dependencies[{index}].references must be an array"
            )
        for ref_index, reference in enumerate(refs):
            if not isinstance(reference, dict):
                raise ProjectBundleError(
                    f"dependencies[{index}].references[{ref_index}] must be an object"
                )
            analysis_id = reference.get("analysis_id")
            field = reference.get("field")
            if not isinstance(analysis_id, str) or not analysis_id:
                raise ProjectBundleError("bundle dependency reference has invalid analysis_id")
            if not isinstance(field, str) or not field:
                raise ProjectBundleError("bundle dependency reference has invalid field")
            item = (dependency["path"], analysis_id, field)
            if item in references:
                raise ProjectBundleError("bundle contains a duplicate dependency reference")
            references.add(item)
    return references


def inspect_project_bundle(path: str | Path) -> dict[str, Any]:
    """Validate bundle structure, hashes, project schema, and internal references."""
    source = Path(path).expanduser()
    source_resolved = source.resolve(strict=False)
    try:
        bundle_before = _stable_file_fingerprint(source_resolved)
    except (OSError, RuntimeError) as exc:
        raise ProjectBundleError(f"bundle is unavailable or changing: {source}") from exc
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ProjectBundleError("bundle contains duplicate archive member names")
            for info in infos:
                _safe_archive_path(info.filename, field="archive member")
                if info.is_dir():
                    raise ProjectBundleError(
                        f"bundle contains an unexpected directory entry: {info.filename}"
                    )

            manifest, manifest_bytes = _load_manifest(archive)
            if manifest.get("schema") != PROJECT_BUNDLE_SCHEMA:
                raise ProjectBundleError(
                    f"bundle schema must be {PROJECT_BUNDLE_SCHEMA!r}"
                )
            version = manifest.get("schema_version")
            if version != PROJECT_BUNDLE_SCHEMA_VERSION:
                raise ProjectBundleError(
                    f"unsupported bundle schema version {version!r}; "
                    f"this build supports {PROJECT_BUNDLE_SCHEMA_VERSION}"
                )
            cleanroomx_version = manifest.get("cleanroomx_version")
            if not isinstance(cleanroomx_version, str) or not cleanroomx_version.strip():
                raise ProjectBundleError(
                    "bundle manifest cleanroomx_version must be a non-empty string"
                )

            project_path, project_size, project_sha256 = _validated_integrity_record(
                manifest.get("project"),
                field="project",
            )
            if project_path != PROJECT_BUNDLE_PROJECT:
                raise ProjectBundleError(
                    f"bundle project path must be {PROJECT_BUNDLE_PROJECT!r}"
                )

            dependencies = manifest.get("dependencies")
            if not isinstance(dependencies, list):
                raise ProjectBundleError("dependencies must be an array")
            normalized_dependencies: list[dict[str, Any]] = []
            dependency_paths: set[str] = set()
            for index, raw_dependency in enumerate(dependencies):
                archive_path, size, digest = _validated_integrity_record(
                    raw_dependency,
                    field=f"dependencies[{index}]",
                )
                if not archive_path.startswith(f"{_DEPENDENCY_DIRECTORY}/"):
                    raise ProjectBundleError(
                        f"dependency must be under {_DEPENDENCY_DIRECTORY}/: {archive_path}"
                    )
                if archive_path in dependency_paths:
                    raise ProjectBundleError(
                        f"bundle contains duplicate dependency path: {archive_path}"
                    )
                dependency_paths.add(archive_path)
                normalized = dict(raw_dependency)
                normalized["path"] = archive_path
                normalized["size_bytes"] = size
                normalized["sha256"] = digest
                normalized_dependencies.append(normalized)

            expected_members = {
                PROJECT_BUNDLE_MANIFEST,
                project_path,
                *dependency_paths,
            }
            if set(names) != expected_members:
                unexpected = sorted(set(names) - expected_members)
                missing = sorted(expected_members - set(names))
                detail = []
                if unexpected:
                    detail.append("unexpected: " + ", ".join(unexpected))
                if missing:
                    detail.append("missing: " + ", ".join(missing))
                raise ProjectBundleError(
                    "bundle member set does not match manifest"
                    + (f" ({'; '.join(detail)})" if detail else "")
                )

            _verify_member(archive, project_path, project_size, project_sha256)
            for dependency in normalized_dependencies:
                _verify_member(
                    archive,
                    dependency["path"],
                    dependency["size_bytes"],
                    dependency["sha256"],
                )

            bundled_project = _read_project_member(archive, project_path)
            actual_references: set[tuple[str, str, str]] = set()
            for analysis in bundled_project.analyses:
                for field, declared_path in _external_dependency_references(
                    analysis.kind, analysis.input
                ):
                    normalized_path = str(
                        _safe_archive_path(
                            declared_path,
                            field=f"analysis {analysis.id!r} dependency {field}",
                        )
                    )
                    if normalized_path not in dependency_paths:
                        raise ProjectBundleError(
                            f"analysis {analysis.id!r} references unbundled dependency: "
                            f"{declared_path}"
                        )
                    actual_references.add((normalized_path, analysis.id, field))

            manifest_references = _manifest_reference_set(normalized_dependencies)
            if manifest_references != actual_references:
                raise ProjectBundleError(
                    "bundle dependency-reference manifest does not match the project"
                )
    except zipfile.BadZipFile as exc:
        raise ProjectBundleError("file is not a valid CleanroomX project bundle") from exc

    try:
        bundle_after = _stable_file_fingerprint(source_resolved)
    except (OSError, RuntimeError) as exc:
        raise ProjectBundleError(f"bundle changed during verification: {source}") from exc
    if (
        bundle_before["size_bytes"] != bundle_after["size_bytes"]
        or bundle_before["sha256"] != bundle_after["sha256"]
    ):
        raise ProjectBundleError(f"bundle changed during verification: {source}")

    return {
        "schema": PROJECT_BUNDLE_SCHEMA,
        "schema_version": PROJECT_BUNDLE_SCHEMA_VERSION,
        "bundle_path": str(source),
        "bundle_sha256": bundle_before["sha256"],
        "bundle_size_bytes": bundle_before["size_bytes"],
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "manifest_size_bytes": len(manifest_bytes),
        "project_name": bundled_project.name,
        "project_path": project_path,
        "project_sha256": project_sha256,
        "project_size_bytes": project_size,
        "dependency_count": len(normalized_dependencies),
        "dependency_bytes": sum(
            dependency["size_bytes"] for dependency in normalized_dependencies
        ),
        "dependencies": normalized_dependencies,
    }


def extract_project_bundle(
    path: str | Path,
    destination: str | Path,
) -> Path:
    """Verify and transactionally extract a bundle into a new or empty directory."""
    source = Path(path).expanduser()
    report = inspect_project_bundle(source)
    target = Path(destination).expanduser().resolve(strict=False)
    if target.exists():
        if not target.is_dir():
            raise ProjectBundleError(f"extraction destination is not a directory: {target}")
        if any(target.iterdir()):
            raise ProjectBundleError(
                f"extraction destination must be empty: {target}"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name or 'cleanroomx-bundle'}.",
            suffix=".tmp",
            dir=target.parent,
        )
    )
    published = False
    try:
        expected = {
            PROJECT_BUNDLE_MANIFEST: (
                report["manifest_size_bytes"],
                report["manifest_sha256"],
            ),
            report["project_path"]: (
                report["project_size_bytes"],
                report["project_sha256"],
            ),
            **{
                item["path"]: (item["size_bytes"], item["sha256"])
                for item in report["dependencies"]
            },
        }
        try:
            with zipfile.ZipFile(source, mode="r") as archive:
                for member, (expected_size, expected_sha256) in expected.items():
                    safe = _safe_archive_path(member, field="archive member")
                    output = stage.joinpath(*safe.parts)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open(member, mode="r") as src, output.open("xb") as dst:
                        for chunk in iter(lambda: src.read(_COPY_CHUNK_SIZE), b""):
                            digest.update(chunk)
                            size += len(chunk)
                            dst.write(chunk)
                        dst.flush()
                        os.fsync(dst.fileno())
                    if size != expected_size or digest.hexdigest() != expected_sha256:
                        raise ProjectBundleError(
                            f"bundle changed during extraction: {member}"
                        )
        except (KeyError, zipfile.BadZipFile) as exc:
            raise ProjectBundleError("bundle changed during extraction") from exc

        try:
            bundle_after_copy = _stable_file_fingerprint(source.resolve(strict=False))
        except (OSError, RuntimeError) as exc:
            raise ProjectBundleError("bundle changed during extraction") from exc
        if (
            bundle_after_copy["size_bytes"] != report["bundle_size_bytes"]
            or bundle_after_copy["sha256"] != report["bundle_sha256"]
        ):
            raise ProjectBundleError("bundle changed during extraction")

        extracted_project = stage.joinpath(*PurePosixPath(report["project_path"]).parts)
        load_project_document_with_revision(extracted_project)

        if target.exists():
            target.rmdir()
        os.replace(stage, target)
        published = True
    finally:
        if not published:
            shutil.rmtree(stage, ignore_errors=True)

    return target.joinpath(*PurePosixPath(report["project_path"]).parts)
