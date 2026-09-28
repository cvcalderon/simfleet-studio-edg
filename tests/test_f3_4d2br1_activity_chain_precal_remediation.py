from pathlib import Path

import pandas as pd
import pytest
import yaml

from simfleet_edg.evaluation.activity_chain_purpose_attribution import (
    DIRECT_PURPOSE,
    attribute_generated_purpose,
    fit_purpose_attribution,
    resolve_return_previous_probability,
    validate_purpose_semantics,
)

CFG = Path("configs/f3/f3_4d2br1_activity_chain_precal_remediation_v1.yaml")


def fixture_frame() -> pd.DataFrame:
    rows = []
    for i in range(30):
        rows.append(
            {
                "prefix_second_last_activity": "WORK",
                "prefix_last_activity": "SHOPPING",
                "target_destination_activity": "WORK",
                "remaining_trips": 1,
                "source_trip_count_analogue": 3,
                "canonical_trip_purpose": (
                    "RETURN_PREVIOUS" if i < 3 else "WORK_COMMUTE"
                ),
                "fit_weight_W_GEW": 1.0,
            }
        )
    rows.append(
        {
            "prefix_second_last_activity": "HOME",
            "prefix_last_activity": "WORK",
            "target_destination_activity": "SHOPPING",
            "remaining_trips": 0,
            "source_trip_count_analogue": 2,
            "canonical_trip_purpose": "SHOPPING",
            "fit_weight_W_GEW": 1.0,
        }
    )
    return pd.DataFrame(rows)


def test_direct_mapping_exact():
    assert DIRECT_PURPOSE["HOME"] == "RETURN_HOME"
    assert DIRECT_PURPOSE["WORK"] == "WORK_COMMUTE"
    assert len(DIRECT_PURPOSE) == 9


def test_semantic_validation_passes_fixture():
    assert validate_purpose_semantics(fixture_frame()) == {
        "return_previous_violations": 0,
        "direct_mapping_violations": 0,
    }


def test_l1_probability_uses_weighted_mle_and_raw_n():
    artifact = fit_purpose_attribution(fixture_frame(), source_n_min=30)
    state = {
        "prefix_second_last_activity": "WORK",
        "prefix_last_activity": "SHOPPING",
        "target_destination_activity": "WORK",
        "remaining_trips": 1,
        "source_trip_count_analogue": 3,
    }
    level, probability, source_n = resolve_return_previous_probability(
        artifact, state
    )
    assert level == "L1"
    assert source_n == 30
    assert probability == pytest.approx(0.1)


def test_noneligible_transition_maps_directly():
    artifact = fit_purpose_attribution(fixture_frame(), source_n_min=30)
    state = {
        "prefix_second_last_activity": "HOME",
        "prefix_last_activity": "WORK",
        "target_destination_activity": "SHOPPING",
        "remaining_trips": 0,
        "source_trip_count_analogue": 2,
    }
    assert attribute_generated_purpose(artifact, state, u=0.0) == "SHOPPING"


def test_return_eligible_uses_binary_draw():
    artifact = fit_purpose_attribution(fixture_frame(), source_n_min=30)
    state = {
        "prefix_second_last_activity": "WORK",
        "prefix_last_activity": "SHOPPING",
        "target_destination_activity": "WORK",
        "remaining_trips": 1,
        "source_trip_count_analogue": 3,
    }
    assert (
        attribute_generated_purpose(artifact, state, u=0.05)
        == "RETURN_PREVIOUS"
    )
    assert (
        attribute_generated_purpose(artifact, state, u=0.5)
        == "WORK_COMMUTE"
    )


def test_contract_extends_cal_inputs_without_opening_cal():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["cal_input_extension"]["physical_rows_total"] == 1853
    assert len(cfg["cal_input_extension"]["files"]) == 3
    assert cfg["boundaries"]["cal_rows_read_by_this_phase"] == 0
    assert cfg["boundaries"]["real_cal_open_authorized"] is False


def test_propagated_return_home_denominator():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    prop = cfg["propagated_observability"]
    assert prop["fixed_source_cohort"]["context_row_ids"] == 319
    assert prop["cohort_reselection_by_generated_mobile_state"] is False
    assert (
        prop["guardrails"]["M2-RET-01"]["no_trip_day_contribution"]
        == "EXCLUDED_FROM_DENOMINATOR"
    )
    assert prop["primary_metric"]["redefine_in_propagated"] is False
