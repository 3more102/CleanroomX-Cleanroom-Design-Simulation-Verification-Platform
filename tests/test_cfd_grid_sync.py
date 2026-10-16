import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cleanroomx.cfd_grid_sync import (
    run_grid_sync,
    sync_grid_proofgraph_once,
    watch_signature,
)


def _graph_factory(*, body=None, on_build=None):
    def build(family, *, grid_study_specs):
        if on_build is not None:
            on_build()
        return SimpleNamespace(to_dict=lambda: body or {
            "schema": "cleanroomx.proofgraph",
            "family": Path(family).name,
            "grid_studies": list(grid_study_specs),
        })

    return build


def _publisher(calls):
    def publish(command, path, payload, *, protected_inputs):
        calls.append((command, Path(path), payload, tuple(protected_inputs)))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(payload, encoding="utf-8")
        return True

    return publish


def test_sync_publishes_once_then_skips_unchanged(tmp_path):
    family = tmp_path / "family"
    family.mkdir()
    (family / "manifest.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "CleanroomX" / "proofgraph.json"
    calls = []

    first = sync_grid_proofgraph_once(
        family,
        output,
        graph_factory=_graph_factory(),
        publisher=_publisher(calls),
    )
    second = sync_grid_proofgraph_once(
        family,
        output,
        graph_factory=_graph_factory(),
        publisher=_publisher(calls),
    )

    assert first["status"] == "synced"
    assert second == {"status": "unchanged", "sha256": first["sha256"]}
    assert len(calls) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["family"] == "family"
    assert family in calls[0][3]


def test_sync_refuses_proofgraph_output_inside_source_family(tmp_path):
    family = tmp_path / "family"
    family.mkdir()

    with pytest.raises(ValueError, match="outside the OpenFOAM family"):
        sync_grid_proofgraph_once(
            family,
            family / "proofgraph.json",
            graph_factory=_graph_factory(),
            publisher=_publisher([]),
        )


def test_sync_does_not_publish_if_source_changes_during_graph_build(tmp_path):
    family = tmp_path / "family"
    family.mkdir()
    (family / "manifest.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "proofgraph.json"
    calls = []

    def change_source():
        (family / "grid_run_evidence.json").write_text("{}", encoding="utf-8")

    result = sync_grid_proofgraph_once(
        family,
        output,
        graph_factory=_graph_factory(on_build=change_source),
        publisher=_publisher(calls),
    )

    assert result == {"status": "source_changed_during_sync"}
    assert calls == []
    assert not output.exists()


def test_watch_signature_tracks_family_and_referenced_vtk_and_logs(tmp_path):
    family = tmp_path / "family"
    family.mkdir()
    (family / "manifest.json").write_text("{}", encoding="utf-8")
    studies = tmp_path / "studies"
    studies.mkdir()
    spec = studies / "configuration_1.json"
    vtk = studies / "fine.vtu"
    log = studies / "fine.log"
    vtk.write_bytes(b"vtk-a")
    log.write_text("log-a", encoding="utf-8")
    spec.write_text(json.dumps({
        "runs": [{"vtk_file": vtk.name, "solver_log": log.name}],
    }), encoding="utf-8")

    before = watch_signature(family, [spec])
    vtk.write_bytes(b"vtk-b-different")
    after_vtk = watch_signature(family, [spec])
    log.write_text("log-b", encoding="utf-8")
    after_log = watch_signature(family, [spec])
    (family / "simpleFoam.log").write_text("new solver output", encoding="utf-8")
    after_family = watch_signature(family, [spec])

    assert before != after_vtk
    assert after_vtk != after_log
    assert after_log != after_family


def test_run_grid_sync_once_writes_export_and_returns_success(tmp_path, capsys):
    family = tmp_path / "family"
    family.mkdir()
    (family / "manifest.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "proofgraph.json"
    code = run_grid_sync(
        family,
        output,
        once=True,
        graph_factory=_graph_factory(),
        publisher=_publisher([]),
    )

    assert code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["family"] == "family"
    assert json.loads(capsys.readouterr().out)["status"] == "synced"


def test_live_sync_restores_export_if_it_is_removed(tmp_path, monkeypatch):
    import cleanroomx.cfd_grid_sync as sync

    family = tmp_path / "family"
    family.mkdir()
    (family / "manifest.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "proofgraph.json"
    calls = []
    waits = 0

    def sleep(_interval):
        nonlocal waits
        waits += 1
        if waits == 1:
            output.unlink()
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(sync.time, "sleep", sleep)
    code = run_grid_sync(
        family,
        output,
        graph_factory=_graph_factory(),
        publisher=_publisher(calls),
    )

    assert code == 130
    assert len(calls) == 2
    assert output.is_file()


@pytest.mark.parametrize("interval", [True, 0, 0.01, float("inf"), "2"])
def test_sync_rejects_invalid_poll_interval(tmp_path, interval):
    family = tmp_path / "family"
    family.mkdir()
    with pytest.raises(ValueError, match="interval_seconds"):
        run_grid_sync(family, tmp_path / "proofgraph.json", interval_seconds=interval)
