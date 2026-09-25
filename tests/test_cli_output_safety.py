from __future__ import annotations

from pathlib import Path


def test_cli_file_outputs_use_shared_atomic_writer():
    package_dir = Path(__file__).resolve().parents[1] / "src" / "cleanroomx"
    output_modules: list[str] = []
    direct_write_offenders: list[str] = []
    missing_atomic_writer: list[str] = []

    for path in sorted(package_dir.glob("*_cli.py")):
        source = path.read_text(encoding="utf-8")
        if "args.output" not in source:
            continue
        output_modules.append(path.name)
        if ".write_text(" in source:
            direct_write_offenders.append(path.name)
        if "atomic_write_text" not in source:
            missing_atomic_writer.append(path.name)

    assert output_modules, "expected at least one CLI with file output support"
    assert direct_write_offenders == []
    assert missing_atomic_writer == []
