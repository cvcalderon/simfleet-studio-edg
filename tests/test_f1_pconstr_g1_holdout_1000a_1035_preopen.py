import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from simfleet_edg.population.senior_holdout_metrics import (
    LEAF_CATEGORIES,
    classify_household_senior_status,
    evaluate_senior_holdout_counts,
    person_leaf_counts,
    total_variation_distance_from_counts,
)

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_leaf_classification() -> None:
    assert classify_household_senior_status([70]) == "SINGLE_SENIOR_HOUSEHOLD"
    assert classify_household_senior_status([70, 80]) == "TWO_PERSON_ALL_SENIOR_HOUSEHOLD"
    assert classify_household_senior_status([65, 70, 99]) == "MULTIPERSON_ALL_SENIOR_HOUSEHOLD"
    assert classify_household_senior_status([64, 65]) == "SENIOR_AND_YOUNGER_HOUSEHOLD"
    assert classify_household_senior_status([1, 64]) == "NO_SENIOR_HOUSEHOLD"


def test_person_counts_are_person_weighted_not_household_weighted() -> None:
    persons = pd.DataFrame(
        {
            "hh": ["a", "b", "b", "c", "c", "c"],
            "age": [70, 70, 80, 65, 40, 20],
            "bezirk": ["X"] * 6,
        }
    )
    out = person_leaf_counts(persons, household_col="hh", age_col="age", geography_col="bezirk")
    got = dict(zip(out["category"], out["persons"], strict=True))
    assert got["SINGLE_SENIOR_HOUSEHOLD"] == 1
    assert got["TWO_PERSON_ALL_SENIOR_HOUSEHOLD"] == 2
    assert got["SENIOR_AND_YOUNGER_HOUSEHOLD"] == 3


def test_tvd_zero_for_equal_distributions() -> None:
    counts = {c: i + 1 for i, c in enumerate(LEAF_CATEGORIES)}
    assert total_variation_distance_from_counts(counts, counts) == 0.0


def test_tvd_known_extreme() -> None:
    syn = {c: 0 for c in LEAF_CATEGORIES}
    off = {c: 0 for c in LEAF_CATEGORIES}
    syn[LEAF_CATEGORIES[0]] = 10
    off[LEAF_CATEGORIES[1]] = 10
    assert total_variation_distance_from_counts(syn, off) == 1.0


def _counts_frame(values: dict[str, dict[str, int]]) -> pd.DataFrame:
    rows = []
    for bezirk, counts in values.items():
        for category in LEAF_CATEGORIES:
            rows.append({"bezirk": bezirk, "category": category, "persons": counts[category]})
    return pd.DataFrame(rows)


def test_weighted_bezirk_metric_uses_official_person_totals() -> None:
    a_off = {c: 0 for c in LEAF_CATEGORIES}
    a_syn = {c: 0 for c in LEAF_CATEGORIES}
    b_off = {c: 0 for c in LEAF_CATEGORIES}
    b_syn = {c: 0 for c in LEAF_CATEGORIES}
    a_off[LEAF_CATEGORIES[0]] = 90
    a_syn[LEAF_CATEGORIES[0]] = 90
    b_off[LEAF_CATEGORIES[0]] = 10
    b_syn[LEAF_CATEGORIES[1]] = 10
    m = evaluate_senior_holdout_counts(
        _counts_frame({"A": a_syn, "B": b_syn}),
        _counts_frame({"A": a_off, "B": b_off}),
        expected_geographies=["A", "B"],
    )
    assert m.bezirk_wtvd == pytest.approx(0.1)
    assert m.bezirk_max == pytest.approx(1.0)
    assert m.berlin_tvd == pytest.approx(0.1)


def test_incomplete_leaf_support_fails_closed() -> None:
    counts = {c: 1 for c in LEAF_CATEGORIES}
    counts.pop(LEAF_CATEGORIES[-1])
    with pytest.raises(ValueError):
        total_variation_distance_from_counts(counts, {c: 1 for c in LEAF_CATEGORIES})


def test_inconsistent_household_geography_fails() -> None:
    persons = pd.DataFrame({"hh": ["a", "a"], "age": [70, 72], "bezirk": ["X", "Y"]})
    with pytest.raises(ValueError):
        person_leaf_counts(persons, household_col="hh", age_col="age", geography_col="bezirk")


def test_preopen_config_keeps_holdout_sealed_and_blocked() -> None:
    cfg = yaml.safe_load(
        (ROOT / "configs/f1/f1_pconstr_g1_holdout_1000a_1035_preopen_v1.yaml").read_text()
    )
    assert cfg["required_parent_commit"] == "e2cd5e4445b3c75af865d4a1d43509a0b7953b48"
    assert cfg["frozen_upstream"]["selected_candidate"] == "P_CONSTR_RMIN_V2_HD_U"
    assert cfg["holdout_identity"]["source_values_status"] == "UNACQUIRED_UNREAD"
    assert cfg["holdout_identity"]["source_value_io_authorized"] is False
    assert cfg["validation_realization"]["scale_id"] == "M"
    assert cfg["validation_realization"]["candidate_master_seed"] == 20261005
    assert cfg["validation_realization"]["h6_master_seed"] == 20261004
    assert cfg["decision_threshold_status"]["blocker_id"] == "HOLD-THRESH-001"
    assert cfg["holdout_authorization"]["authorized"] is False


def test_authorization_template_is_negative_and_unbound() -> None:
    auth = json.loads(
        (ROOT / "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_AUTHORIZATION_TEMPLATE_v1.json").read_text()
    )
    assert auth["authorized"] is False
    assert auth["required_preholdout_commit"] is None
    assert auth["holdout_value_io_authorized"] is False
