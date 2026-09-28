from pathlib import Path

import yaml

CFG = Path("configs/f3/f3_4d1_activity_chain_cal_contract_v1.yaml")


def _cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_candidate_universe_exact():
    cfg = _cfg()
    assert [x["artifact_id"] for x in cfg["candidate_universe"]] == [
        "DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE",
        "DG_ACTIVITY_CHAIN::CHAIN_A::CHA1",
        "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "DG_ACTIVITY_CHAIN::CHAIN_B::CHB1",
        "DG_ACTIVITY_CHAIN::CHAIN_B::CHB2",
        "DG_ACTIVITY_CHAIN::CHAIN_B::CHB3",
    ]


def test_primary_and_margin_are_frozen():
    cfg = _cfg()
    p = cfg["evaluation"]["primary"]
    assert p["metric"] == "WEIGHTED_NEXT_ACTIVITY_LOG_LOSS"
    assert p["direction"] == "LOWER_IS_BETTER"
    assert p["isolated_rows"] == 1065
    assert p["practical_margin"] == 0.01


def test_guardrails_are_exact():
    cfg = _cfg()
    assert [
        (x["metric"], x["worsening_tolerance"])
        for x in cfg["guardrails"]
    ] == [
        ("M2-PURP-01", 0.005),
        ("M2-TRANS-01", 0.005),
        ("M2-RET-01", 0.01),
    ]


def test_cal_cardinalities_and_hashes_are_frozen():
    cfg = _cfg()
    assert cfg["cal_input"]["chain_days"] == {
        "filename": "chain_days.csv",
        "expected_rows": 319,
        "sha256": (
            "c82fae3ba7b37e059e57bc07b0b9deae23f705dfff964afa173714f8342a838f"
        ),
    }
    assert cfg["cal_input"]["chain_transitions"] == {
        "filename": "chain_transitions.csv",
        "expected_rows": 1065,
        "sha256": (
            "b397a381b9d2d86ce7771d0de4ac5a7e45d65897c2caea59832eb139493ed7d0"
        ),
    }


def test_upstream_is_main_frozen_and_test_is_sealed():
    cfg = _cfg()
    assert cfg["upstream"]["participation"]["state"] == "MAIN_FROZEN"
    assert cfg["upstream"]["trip_count"]["state"] == "MAIN_FROZEN"
    assert cfg["boundaries"]["real_cal_open_authorized"] is False
    assert cfg["boundaries"]["cal_rows_read_by_this_phase"] == 0
    assert cfg["boundaries"]["test_open_authorized"] is False
    assert cfg["boundaries"]["test_rows_read"] == 0
    assert cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED"


def test_stochastic_protocol_is_frozen():
    cfg = _cfg()
    s = cfg["stochastic_protocol"]
    assert s["master_seed"] == 20260926
    assert s["replicates"] == 32
    assert s["common_random_numbers"] is True
    assert s["bootstrap"]["unit"] == "HOUSEHOLD"
    assert s["bootstrap"]["replicates"] == 1000
    assert s["bootstrap"]["confidence_level"] == 0.95
