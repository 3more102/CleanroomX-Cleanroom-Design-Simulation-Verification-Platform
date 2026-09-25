from __future__ import annotations

from collections.abc import Mapping
from difflib import get_close_matches
from typing import Any


CONSISTENCY_INPUT_KEYS = frozenset(
    {
        "verification_project",
        "hvac_project",
        "room_airflow_abs_tolerance_m3_h",
        "require_same_room_set",
    }
)

DOSSIER_SINGLE_PATH_KEYS = (
    "verification_project",
    "hvac_project",
)

DOSSIER_LIST_PATH_KEYS = (
    "recovery_tests",
    "qualification_analyses",
    "uncertainty_rooms",
    "thermal_uncertainty_analyses",
    "psychrometric_uncertainty_analyses",
    "fan_operating_point_studies",
    "fan_system_uncertainty_analyses",
    "fan_duct_network_studies",
    "fan_parallel_network_studies",
    "fan_loop_network_studies",
    "fan_loop_uncertainty_analyses",
    "damper_studies",
    "fan_speed_studies",
    "fan_loop_speed_studies",
    "fan_variable_friction_loop_studies",
    "fan_variable_friction_speed_studies",
    "fan_variable_friction_uncertainty_analyses",
)

DOSSIER_METADATA_KEYS = frozenset(
    {
        "name",
        "project_reference",
        "revision",
        "prepared_by",
        "notes",
        "consistency_checks",
    }
)

DOSSIER_INPUT_KEYS = frozenset(
    set(DOSSIER_METADATA_KEYS)
    | set(DOSSIER_SINGLE_PATH_KEYS)
    | set(DOSSIER_LIST_PATH_KEYS)
)

DOSSIER_CONSISTENCY_CHECK_KEYS = frozenset(
    {
        "verification_hvac_airflow",
        "hvac_fan_operating_airflow",
    }
)

DOSSIER_CONSISTENCY_OPTION_KEYS = {
    "verification_hvac_airflow": frozenset(
        {
            "room_airflow_abs_tolerance_m3_h",
            "require_same_room_set",
        }
    ),
    "hvac_fan_operating_airflow": frozenset(
        {
            "airflow_abs_tolerance_m3_h",
        }
    ),
}


def _render_unknown_fields(
    values: list[Any],
    allowed: frozenset[str] | set[str],
) -> str:
    rendered: list[str] = []
    candidates = sorted(allowed)
    for value in sorted(values, key=repr):
        detail = repr(value)
        if isinstance(value, str):
            matches = get_close_matches(value, candidates, n=1, cutoff=0.75)
            if matches:
                detail += f" (did you mean {matches[0]!r}?)"
        rendered.append(detail)
    return ", ".join(rendered)


def reject_unknown_fields(
    data: Mapping[Any, Any],
    allowed: frozenset[str] | set[str],
    *,
    context: str,
) -> None:
    """Reject unrecognized mapping keys deterministically.

    File-backed engineering workflows use optional fields heavily. Silently ignoring
    a misspelled key can therefore change a calculation or omit dossier evidence by
    falling back to a default. This boundary fails closed before any analysis runs.
    """
    unknown = [key for key in data if key not in allowed]
    if unknown:
        raise ValueError(
            f"unsupported {context} field(s): {_render_unknown_fields(unknown, allowed)}"
        )


def validate_consistency_input_contract(payload: Mapping[Any, Any]) -> None:
    reject_unknown_fields(
        payload,
        CONSISTENCY_INPUT_KEYS,
        context="consistency input",
    )


def validate_dossier_input_contract(payload: Mapping[Any, Any]) -> None:
    reject_unknown_fields(
        payload,
        DOSSIER_INPUT_KEYS,
        context="dossier manifest",
    )

    checks = payload.get("consistency_checks", {})
    if not isinstance(checks, dict):
        return

    reject_unknown_fields(
        checks,
        DOSSIER_CONSISTENCY_CHECK_KEYS,
        context="dossier consistency check",
    )

    for check_name, allowed_options in DOSSIER_CONSISTENCY_OPTION_KEYS.items():
        config = checks.get(check_name)
        if isinstance(config, dict):
            reject_unknown_fields(
                config,
                allowed_options,
                context=f"{check_name} option",
            )
