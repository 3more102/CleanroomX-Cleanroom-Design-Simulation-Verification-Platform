from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "production_acceptance.py"


def test_production_acceptance_contract_passes_and_emits_evidence(tmp_path: Path) -> None:
    output = tmp_path / "production-acceptance.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "cleanroomx.production-acceptance"
    assert payload["schema_version"] == 1
    assert payload["status"] == "pass"
    assert payload["summary"]["fail_count"] == 0
    assert payload["summary"]["check_count"] >= 8
    assert all(item["passed"] is True for item in payload["checks"])
    assert "does not establish regulatory certification" in payload["boundary"]
