import csv
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_g1_hold_thresh01_preopen_v1.yaml"
CSV = ROOT / "docs/F1_PCONSTR_G1_HOLDOUT_THRESHOLDS_v1.csv"
T = Decimal("0.0815667541845037")


def config():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def rows():
    with CSV.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_transfer_rule_is_max_of_frozen_taus():
    cfg = config()
    taus = [Decimal(value) for value in cfg["frozen_cal_materiality_taus"].values()]
    assert max(taus) == T
    assert Decimal(cfg["threshold_transfer_rule"]["numeric_value"]) == T


def test_two_decision_metrics_use_same_frozen_threshold():
    by_id = {row["metric_id"]: row for row in rows()}
    for metric in ("G1-HOLD-SEN-BERLIN-TVD", "G1-HOLD-SEN-BEZ-WTVD"):
        assert by_id[metric]["role"] == "DECISION"
        assert Decimal(by_id[metric]["threshold"]) == T
        assert by_id[metric]["comparison"] == "LESS_THAN_OR_EQUAL"


def test_bezirk_max_remains_report_only():
    by_id = {row["metric_id"]: row for row in rows()}
    assert by_id["G1-HOLD-SEN-BEZ-MAX"]["role"] == "REPORT_ONLY"
    assert by_id["G1-HOLD-SEN-BEZ-MAX"]["threshold"] == ""


def test_no_composite_score_and_both_decision_metrics_required():
    cfg = config()
    assert cfg["decision_rule"]["no_composite_score"] is True
    assert cfg["decision_rule"]["pass_requires_all_decision_metrics"] is True


def test_holdout_stays_sealed():
    b = config()["boundaries"]
    assert b["holdout_1000A_1035_acquired"] is False
    assert b["holdout_1000A_1035_values_read"] is False
    assert b["holdout_1000A_1035_authorized"] is False
    assert b["holdout_metric_evaluation"] is False


def test_no_cal_or_test_reopen():
    b = config()["boundaries"]
    assert b["cal_reopened"] is False
    assert b["mid_test_reopened"] is False
    assert b["mid_test_global_state"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"


def test_next_step_is_separate_authorization_preopen():
    cfg = config()
    assert cfg["next_step_if_committed"] == "F1-P-CONSTR-G1-HOLDOUT-1000A-1035-AUTH-PREOPEN"
