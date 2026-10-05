from pathlib import Path

import yaml


def test_impl03_config_freezes_boundaries_and_parent():
    config = yaml.safe_load(
        Path("configs/f1/f1_pconstr_impl03_candidates_v1.yaml").read_text(encoding="utf-8")
    )
    assert config["required_parent_commit"] == "2f547ec53501245af1d605a866e19febfc5089b8"
    assert config["boundaries"]["calibration_read"] is False
    assert config["boundaries"]["mid_test_read_by_impl03"] is False
    assert config["boundaries"]["holdout_1000A_1035_read"] is False
    assert config["boundaries"]["donor_partition"] == "TRAIN_ONLY"
    assert config["boundaries"]["G1"] == "OPEN"
    assert config["boundaries"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"


def test_impl03_variants_are_exactly_preregistered_three():
    config = yaml.safe_load(
        Path("configs/f1/f1_pconstr_impl03_candidates_v1.yaml").read_text(encoding="utf-8")
    )
    assert [item["id"] for item in config["variants"]] == [
        "P_TRS_V1_FINAL",
        "P_CONSTR_RMIN_V2_HD_U",
        "P_CONSTR_RMIN_V2_HD_W",
    ]
