from pathlib import Path

import yaml


def test_impl02_config_freezes_scope_and_algorithms() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(
        (root / "configs/f1/f1_pconstr_impl02_scale_h6_v1.yaml").read_text(encoding="utf-8")
    )
    assert config["required_parent_commit"] == "6ca6a2fd1f577433237fce3cca8763c84d8f68fe"
    assert config["scale_projection"]["algorithm_id"] == "EXACT_L1_MODULAR_ROUNDING_V1"
    assert config["scale_projection"]["tie_break_id"] == "CANONICAL_WEIGHTED_INCREMENT_V1"
    assert config["six_plus"]["policy_id"] == "H6_COMPLETION_V1"
    assert config["six_plus"]["donor_materialization"] == "DEFERRED_TO_IMPL_03"
    assert config["boundaries"]["calibration_read"] is False
    assert config["boundaries"]["mid_test_read_by_impl02"] is False
    assert config["boundaries"]["holdout_1000A_1035_read"] is False
    assert config["boundaries"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"
