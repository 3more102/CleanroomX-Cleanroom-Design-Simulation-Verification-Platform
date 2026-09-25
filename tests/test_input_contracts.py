from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.application import validate_analysis_input
from cleanroomx.dossier import build_dossier
from cleanroomx.input_contracts import validate_dossier_input_contract


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_consistency_rejects_misspelled_required_room_set_option() -> None:
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
        "require_same_room_sets": True,
    }

    with pytest.raises(ValueError, match="require_same_room_sets") as raised:
        validate_analysis_input("consistency", payload, base_dir=EXAMPLES)

    assert "did you mean 'require_same_room_set'?" in str(raised.value)


def test_dossier_rejects_misspelled_source_list_in_application_path() -> None:
    payload = _example("dossier_variable_friction_uncertainty_demo.json")
    referenced = payload.pop("fan_variable_friction_uncertainty_analyses")
    payload["fan_variable_friction_uncertainty_analysis"] = referenced

    with pytest.raises(
        ValueError,
        match="fan_variable_friction_uncertainty_analysis",
    ):
        validate_analysis_input("dossier", payload, base_dir=EXAMPLES)


def test_dossier_rejects_unknown_consistency_check_name() -> None:
    payload = _example("dossier_consistency_demo.json")
    config = payload["consistency_checks"].pop("verification_hvac_airflow")
    payload["consistency_checks"]["verification_hvac_airflows"] = config

    with pytest.raises(ValueError, match="verification_hvac_airflows"):
        validate_analysis_input("dossier", payload, base_dir=EXAMPLES)


def test_dossier_rejects_misspelled_nested_consistency_option() -> None:
    payload = _example("dossier_consistency_demo.json")
    config = payload["consistency_checks"]["verification_hvac_airflow"]
    config["require_same_room_sets"] = config.pop("require_same_room_set")

    with pytest.raises(ValueError, match="require_same_room_sets"):
        validate_analysis_input("dossier", payload, base_dir=EXAMPLES)


def test_direct_dossier_execution_uses_same_fail_closed_contract(tmp_path) -> None:
    manifest = {
        "name": "Typo guard",
        "verification_project": str((EXAMPLES / "facility_project.json").resolve()),
        "verification_projects": [
            str((EXAMPLES / "facility_project.json").resolve())
        ],
    }
    path = tmp_path / "dossier.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="verification_projects"):
        build_dossier(path)


def test_dossier_metadata_fields_remain_compatible() -> None:
    validate_dossier_input_contract(
        {
            "name": "Controlled dossier",
            "project_reference": "PRJ-001",
            "revision": "A",
            "prepared_by": "Engineering",
            "notes": "Controlled input",
            "verification_project": "facility_project.json",
        }
    )


def test_unknown_field_error_order_is_deterministic() -> None:
    with pytest.raises(ValueError) as raised:
        validate_dossier_input_contract(
            {
                "name": "Bad keys",
                "verification_project": "facility_project.json",
                "zzz_typo": 1,
                "aaa_typo": 2,
            }
        )

    message = str(raised.value)
    assert message.index("'aaa_typo'") < message.index("'zzz_typo'")
