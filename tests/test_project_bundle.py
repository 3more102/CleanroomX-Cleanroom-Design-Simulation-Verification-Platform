from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

import cleanroomx.gui as gui_module
import cleanroomx.project_bundle as bundle_module
from cleanroomx.application import run_analysis
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document
from cleanroomx.project_bundle import (
    PROJECT_BUNDLE_MANIFEST,
    ProjectBundleError,
    export_project_bundle,
    export_project_bundle_from_path,
    extract_project_bundle,
    inspect_project_bundle,
)
from cleanroomx.project_bundle_cli import main as bundle_cli_main


ROOT = Path(__file__).resolve().parents[1]


def _copy_example(directory: Path, name: str) -> Path:
    target = directory / name
    target.write_bytes((ROOT / "examples" / name).read_bytes())
    return target


def _consistency_project() -> ProjectDocument:
    return ProjectDocument(
        name="Portable consistency",
        analyses=[
            AnalysisDocument(
                id="consistency-1",
                name="Consistency",
                kind="consistency",
                input={
                    "verification_project": "facility_project.json",
                    "hvac_project": "consistency_hvac_demo.json",
                    "room_airflow_abs_tolerance_m3_h": 0.0,
                    "require_same_room_set": True,
                },
            )
        ],
        active_analysis_id="consistency-1",
    )


def _rewrite_zip(
    source: Path,
    target: Path,
    transform,
) -> None:
    with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_STORED
    ) as changed:
        for info in original.infolist():
            data = original.read(info.filename)
            new_name, new_data = transform(info.filename, data)
            if new_name is not None:
                changed.writestr(new_name, new_data)


def test_bundle_round_trip_is_self_contained_and_executable(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    project_path = save_project_document(
        source / "portable.cleanroomx.json",
        _consistency_project(),
    )

    bundle = tmp_path / "portable.cleanroomx.zip"
    export_report = export_project_bundle_from_path(project_path, bundle)
    verify_report = inspect_project_bundle(bundle)

    assert export_report["dependency_count"] == 2
    assert verify_report["dependency_count"] == 2
    assert verify_report["bundle_sha256"] == export_report["bundle_sha256"]
    assert len(verify_report["dependencies"]) == 2
    assert all(
        dependency["path"].startswith("dependencies/")
        for dependency in verify_report["dependencies"]
    )

    extracted_root = tmp_path / "extracted"
    extracted_project_path = extract_project_bundle(bundle, extracted_root)
    raw_project = json.loads(extracted_project_path.read_text(encoding="utf-8"))
    input_data = raw_project["analyses"][0]["input"]
    assert input_data["verification_project"].startswith("dependencies/")
    assert input_data["hvac_project"].startswith("dependencies/")
    assert not Path(input_data["verification_project"]).is_absolute()
    assert not Path(input_data["hvac_project"]).is_absolute()

    run = run_analysis(
        "consistency",
        input_data,
        base_dir=extracted_project_path.parent,
    )
    assert run.result["shared_room_count"] > 0
    assert run.diagnostics["application_execution_provenance"][
        "external_dependencies_stable"
    ] is True


def test_bundle_export_is_deterministic_for_identical_project_and_dependencies(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    project = _consistency_project()

    first = tmp_path / "first.cleanroomx.zip"
    second = tmp_path / "second.cleanroomx.zip"
    first_report = export_project_bundle(first, project, source_base=source)
    second_report = export_project_bundle(second, project, source_base=source)

    assert first.read_bytes() == second.read_bytes()
    assert first_report["bundle_sha256"] == second_report["bundle_sha256"]


def test_bundle_deduplicates_same_dependency_and_preserves_reference_map(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    shared = source / "shared.json"
    shared.write_text('{"name":"shared"}\n', encoding="utf-8")
    project = ProjectDocument(
        name="Deduplicated",
        analyses=[
            AnalysisDocument(
                id="consistency-1",
                name="Consistency",
                kind="consistency",
                input={
                    "verification_project": "shared.json",
                    "hvac_project": "./shared.json",
                },
            )
        ],
        active_analysis_id="consistency-1",
    )

    bundle = tmp_path / "deduplicated.cleanroomx.zip"
    export_project_bundle(bundle, project, source_base=source)
    report = inspect_project_bundle(bundle)

    assert report["dependency_count"] == 1
    references = report["dependencies"][0]["references"]
    assert references == [
        {"analysis_id": "consistency-1", "field": "hvac_project"},
        {"analysis_id": "consistency-1", "field": "verification_project"},
    ]


def test_bundle_export_rejects_missing_dependency_without_publishing(tmp_path):
    project = ProjectDocument(
        name="Missing",
        analyses=[
            AnalysisDocument(
                id="consistency-1",
                name="Consistency",
                kind="consistency",
                input={
                    "verification_project": "missing.json",
                    "hvac_project": "also-missing.json",
                },
            )
        ],
        active_analysis_id="consistency-1",
    )
    target = tmp_path / "missing.cleanroomx.zip"

    with pytest.raises(ProjectBundleError, match="does not exist"):
        export_project_bundle(target, project, source_base=tmp_path)

    assert not target.exists()


def test_bundle_export_aborts_if_dependency_changes_after_fingerprint(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    first = source / "facility_project.json"
    second = source / "consistency_hvac_demo.json"
    _copy_example(source, first.name)
    _copy_example(source, second.name)
    original_builder = bundle_module._build_portable_project

    def mutate_after_fingerprint(*args, **kwargs):
        result = original_builder(*args, **kwargs)
        first.write_text(
            first.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(
        bundle_module,
        "_build_portable_project",
        mutate_after_fingerprint,
    )
    target = tmp_path / "changing.cleanroomx.zip"

    with pytest.raises(ProjectBundleError, match="changed while portable bundle"):
        export_project_bundle(target, _consistency_project(), source_base=source)

    assert not target.exists()
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_bundle_verifier_detects_dependency_corruption(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    valid = tmp_path / "valid.cleanroomx.zip"
    export_project_bundle(valid, _consistency_project(), source_base=source)
    report = inspect_project_bundle(valid)
    corrupt_path = report["dependencies"][0]["path"]

    corrupt = tmp_path / "corrupt.cleanroomx.zip"

    def transform(name: str, data: bytes):
        if name == corrupt_path:
            return name, data + b"corruption"
        return name, data

    _rewrite_zip(valid, corrupt, transform)

    with pytest.raises(ProjectBundleError, match="size mismatch|integrity check"):
        inspect_project_bundle(corrupt)


def test_bundle_verifier_rejects_path_traversal_member(tmp_path):
    malicious = tmp_path / "traversal.cleanroomx.zip"
    with zipfile.ZipFile(malicious, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            PROJECT_BUNDLE_MANIFEST,
            json.dumps(
                {
                    "schema": "cleanroomx.project-bundle",
                    "schema_version": 1,
                    "project": {
                        "path": "project.cleanroomx.json",
                        "size_bytes": 0,
                        "sha256": "0" * 64,
                    },
                    "dependencies": [],
                }
            ),
        )
        archive.writestr("../outside.json", b"unsafe")

    with pytest.raises(ProjectBundleError, match="safe relative POSIX path"):
        inspect_project_bundle(malicious)


def test_bundle_verifier_rejects_unmanifested_member(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    valid = tmp_path / "valid.cleanroomx.zip"
    export_project_bundle(valid, _consistency_project(), source_base=source)
    unexpected = tmp_path / "unexpected.cleanroomx.zip"

    def transform(name: str, data: bytes):
        return name, data

    _rewrite_zip(valid, unexpected, transform)
    with zipfile.ZipFile(unexpected, "a", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("unexpected.txt", b"not declared")

    with pytest.raises(ProjectBundleError, match="member set does not match manifest"):
        inspect_project_bundle(unexpected)


def test_bundle_extraction_refuses_nonempty_destination_without_modifying_it(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    bundle = tmp_path / "portable.cleanroomx.zip"
    export_project_bundle(bundle, _consistency_project(), source_base=source)

    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("unchanged", encoding="utf-8")

    with pytest.raises(ProjectBundleError, match="must be empty"):
        extract_project_bundle(bundle, destination)

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(destination.iterdir()) == [sentinel]


def test_bundle_cli_export_verify_extract_round_trip(tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    project_path = save_project_document(
        source / "portable.cleanroomx.json",
        _consistency_project(),
    )
    bundle = tmp_path / "portable.cleanroomx.zip"

    assert bundle_cli_main(["export", str(project_path), str(bundle)]) == 0
    export_output = json.loads(capsys.readouterr().out)
    assert export_output["dependency_count"] == 2

    assert bundle_cli_main(["verify", str(bundle)]) == 0
    verify_output = json.loads(capsys.readouterr().out)
    assert verify_output["dependency_count"] == 2

    destination = tmp_path / "portable-folder"
    assert bundle_cli_main(["extract", str(bundle), str(destination)]) == 0
    extract_output = json.loads(capsys.readouterr().out)
    extracted_project = Path(extract_output["project_path"])
    assert extracted_project.is_file()
    assert extracted_project.parent == destination


def test_bundle_cli_reports_corruption_without_traceback(tmp_path, capsys):
    invalid = tmp_path / "not-a-bundle.zip"
    invalid.write_bytes(b"not a zip")

    assert bundle_cli_main(["verify", str(invalid)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "project bundle error" in captured.err.lower()


class _Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_desktop_exports_portable_bundle_through_real_service(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    target = tmp_path / "desktop.cleanroomx.zip"

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app.project = _consistency_project()
    app.project_path = source / "live.cleanroomx.json"
    app._recovery_source_path = None
    app._editor_analysis_id = None
    app.name_var = _Value(app.project.name)
    app.description_var = _Value("")
    app.status_var = _Value("")

    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(target),
    )
    messages = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showinfo",
        lambda title, message, parent=None: messages.append((title, message)),
    )

    app.export_portable_project_bundle()

    report = inspect_project_bundle(target)
    assert report["dependency_count"] == 2
    assert "Portable project exported" in app.status_var.value
    assert messages and messages[0][0] == "Portable project exported"


def test_desktop_opens_bundle_only_after_verified_extraction(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    bundle = tmp_path / "handoff.cleanroomx.zip"
    export_project_bundle(bundle, _consistency_project(), source_base=source)

    extraction_parent = tmp_path / "opened"
    extraction_parent.mkdir()
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app._running = False
    app.status_var = _Value("")
    app._confirm_project_replacement = lambda: True
    opened = []
    app.load_project_path = lambda path: opened.append(Path(path))

    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **kwargs: str(bundle),
    )
    monkeypatch.setattr(
        gui_module.filedialog,
        "askdirectory",
        lambda **kwargs: str(extraction_parent),
    )

    app.open_portable_project_bundle()

    assert opened == [
        extraction_parent / "handoff" / "project.cleanroomx.json"
    ]
    assert opened[0].is_file()
    assert "Opened portable project" in app.status_var.value


def test_bundle_export_never_overwrites_source_project(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    project_path = save_project_document(
        source / "portable.cleanroomx.json",
        _consistency_project(),
    )
    original = project_path.read_bytes()

    with pytest.raises(ProjectBundleError, match="cannot overwrite the source project"):
        export_project_bundle_from_path(project_path, project_path)

    assert project_path.read_bytes() == original


def test_bundle_export_never_overwrites_packaged_dependency(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    dependency = _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    original = dependency.read_bytes()

    with pytest.raises(ProjectBundleError, match="cannot overwrite a packaged dependency"):
        export_project_bundle(
            dependency,
            _consistency_project(),
            source_base=source,
        )

    assert dependency.read_bytes() == original


def test_bundle_export_project_race_preserves_existing_bundle(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    project_path = save_project_document(
        source / "portable.cleanroomx.json",
        _consistency_project(),
    )
    target = tmp_path / "portable.cleanroomx.zip"
    target.write_bytes(b"previous verified bundle bytes")
    previous = target.read_bytes()

    original_copy = bundle_module._copy_dependency
    changed = False

    def copy_then_change_project(*args, **kwargs):
        nonlocal changed
        original_copy(*args, **kwargs)
        if not changed:
            project_path.write_text(
                project_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            changed = True

    monkeypatch.setattr(bundle_module, "_copy_dependency", copy_then_change_project)

    with pytest.raises(ProjectBundleError, match="project changed"):
        export_project_bundle_from_path(project_path, target)

    assert target.read_bytes() == previous
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_bundle_verification_rejects_archive_revision_change(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    bundle = tmp_path / "stable.cleanroomx.zip"
    export_project_bundle(bundle, _consistency_project(), source_base=source)

    original_fingerprint = bundle_module._stable_file_fingerprint
    calls = 0

    def changed_second_fingerprint(path):
        nonlocal calls
        calls += 1
        result = original_fingerprint(path)
        if calls == 2:
            result = dict(result)
            result["sha256"] = "0" * 64
        return result

    monkeypatch.setattr(
        bundle_module,
        "_stable_file_fingerprint",
        changed_second_fingerprint,
    )

    with pytest.raises(ProjectBundleError, match="changed during verification"):
        inspect_project_bundle(bundle)


def test_bundle_extraction_does_not_publish_if_archive_changes_during_copy(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    _copy_example(source, "facility_project.json")
    _copy_example(source, "consistency_hvac_demo.json")
    bundle = tmp_path / "stable.cleanroomx.zip"
    export_project_bundle(bundle, _consistency_project(), source_base=source)

    original_fingerprint = bundle_module._stable_file_fingerprint
    calls = 0

    def changed_after_inspection(path):
        nonlocal calls
        calls += 1
        result = original_fingerprint(path)
        if calls == 3:
            result = dict(result)
            result["sha256"] = "f" * 64
        return result

    monkeypatch.setattr(
        bundle_module,
        "_stable_file_fingerprint",
        changed_after_inspection,
    )
    destination = tmp_path / "extracted"

    with pytest.raises(ProjectBundleError, match="changed during extraction"):
        extract_project_bundle(bundle, destination)

    assert not destination.exists()
    assert not list(tmp_path.glob(".extracted.*.tmp"))
