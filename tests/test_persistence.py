from __future__ import annotations

import pytest

from cleanroomx.persistence import atomic_write_text


def test_atomic_write_before_replace_failure_preserves_existing_destination(tmp_path):
    target = tmp_path / "result.json"
    target.write_text("old-result\n", encoding="utf-8")

    def fail_precondition() -> None:
        raise RuntimeError("revision changed")

    with pytest.raises(RuntimeError, match="revision changed"):
        atomic_write_text(target, "new-result\n", before_replace=fail_precondition)

    assert target.read_text(encoding="utf-8") == "old-result\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_creates_parent_and_writes_unicode_text(tmp_path):
    target = tmp_path / "reports" / "result.md"
    content = "Pressure: 12.5 Pa — airflow 1,200 m³/h\n"

    saved = atomic_write_text(target, content)

    assert saved == target
    assert target.read_text(encoding="utf-8") == content
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []
