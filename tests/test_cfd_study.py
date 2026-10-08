import copy
import math

import pytest

from cleanroomx.cfd_study import analyze_cfd_study, validate_study


def base_study():
    return {
        "schema_version": "cleanroomx.cfd-study.v1",
        "name": "Explicitly synthetic CFD field test fixture",
        "room": {"length_m": 2, "width_m": 1, "height_m": 1},
        "analysis": {"contaminant_limit": 5, "contaminant_unit": "particles/m3",
                     "max_unrepresented_volume_fraction": 0,
                     "max_flow_imbalance_fraction": 0},
        "cases": [],
    }


def case(config, values, reverse, speeds=(1.0, 1.0)):
    return {"configuration": config, "source_location_m": [0.5, 0.5, 0.5],
            "inlet_flow_m3_s": 1, "outlet_flow_m3_s": 1,
            "solver": {"name": "synthetic test adapter", "run_id": f"test-{config}",
                       "mesh_cells": 2, "source_reference": "fixture:synthetic-not-CFD"},
            "cells": [{"volume_m3": 1, "velocity_m_s": [speed, 0, 0],
                       "contaminant_concentration": concentration, "recirculating": rc}
                      for concentration, rc, speed in zip(values, reverse, speeds)]}


def test_unique_pareto_dominance_on_synthetic_data_only():
    study = base_study()
    study["cases"] = [
        case(1, (10, 10), (True, True), (0.1, 2.0)),
        case(2, (10, 0), (True, False), (0.5, 1.5)),
        case(3, (0, 0), (False, False), (1.0, 1.0)),
    ]
    report = analyze_cfd_study(study)
    assert report["comparison_status"] == "comparable"
    assert report["unique_pareto_dominant_configuration"] == 3
    assert report["cases"][2]["metrics"]["contaminant_exceedance_volume_fraction"] == 0
    assert report["cases"][0]["metrics"]["recirculation_volume_fraction"] == 1
    assert analyze_cfd_study(study)["input_canonical_sha256"] == report["input_canonical_sha256"]


def test_no_preselected_winner_from_document():
    study = {"schema_version": "cleanroomx.cfd-study.v1", "name": "No CFD results", "room": None,
             "analysis": {}, "cases": [{"configuration": i, "cells": []} for i in (1, 2, 3)]}
    report = analyze_cfd_study(study)
    assert report["comparison_status"] == "insufficient_evidence"
    assert report["unique_pareto_dominant_configuration"] is None
    assert report["room_volume_m3"] is None


def test_failing_coverage_and_different_source_block_comparison():
    study = base_study()
    study["cases"] = [case(i, (1, 1), (False, False)) for i in (1, 2, 3)]
    study["cases"][2]["source_location_m"] = [1.1, 0.5, 0.5]
    study["cases"][0]["cells"][0]["volume_m3"] = 0.5
    report = analyze_cfd_study(study)
    assert report["comparison_status"] == "insufficient_evidence"
    assert any("source positions differ" in msg for msg in report["comparison_blockers"])


def test_tradeoff_has_no_unique_dominant_case():
    study = base_study()
    study["cases"] = [case(1, (0, 0), (True, True)),
                      case(2, (10, 10), (False, False)),
                      case(3, (10, 10), (True, True))]
    report = analyze_cfd_study(study)
    assert report["comparison_status"] == "comparable"
    assert report["unique_pareto_dominant_configuration"] is None


@pytest.mark.parametrize("change", [
    lambda s: s.update(analysis={"contaminant_limit": math.nan}),
    lambda s: s["cases"][0].update(configuration=True),
    lambda s: s["cases"][0]["cells"][0].update(volume_m3=3.0),
    lambda s: s["cases"][0]["cells"][0].update(recirculating=1),
    lambda s: s["cases"][0].update(unexpected=123),
    lambda s: s["cases"][0].update(source_location_m=[8, 0, 0]),
])
def test_strict_rejection(change):
    study = base_study()
    study["cases"] = [case(1, (1, 1), (False, False))]
    change(study)
    with pytest.raises(ValueError):
        validate_study(study)
