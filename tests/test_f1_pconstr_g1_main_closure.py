import csv
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _cfg():
    return yaml.safe_load(
        (ROOT / "configs/f1/f1_pconstr_g1_main_closure_v1.yaml").read_text(encoding="utf-8")
    )


def _metrics():
    with (ROOT / "docs/F1_PCONSTR_G1_A1_R1_METRICS_SNAPSHOT_v1.csv").open(
        encoding="utf-8", newline=""
    ) as fh:
        return {row["metric_id"]: row for row in csv.DictReader(fh)}


def test_parent_and_candidate_are_exact():
    cfg = _cfg()
    assert cfg["required_parent_commit"] == "1aafadd95120c7875aac26f6504a6feb2aa5717a"
    assert cfg["selected_population"]["candidate_id"] == "P_CONSTR_RMIN_V2_HD_U"
    assert cfg["selected_population"]["scale_id"] == "M"


def test_g1_is_pass_and_closes_only_after_commit():
    cfg = _cfg()
    assert cfg["official_result"]["G1"] == "PASS"
    assert cfg["status_precommit"] == "G1_PASS_AUDITED_PENDING_MAIN_FREEZE"
    assert cfg["status_after_commit"] == "G1_PASS_CLOSED"


def test_decision_metrics_pass_exact_threshold():
    rows = _metrics()
    for metric_id in ("G1-HOLD-SEN-BERLIN-TVD", "G1-HOLD-SEN-BEZ-WTVD"):
        row = rows[metric_id]
        assert row["role"] == "DECISION"
        assert row["threshold"] == "0.0815667541845037"
        assert row["comparison"] == "LESS_THAN_OR_EQUAL"
        assert row["decision"] == "PASS"


def test_report_only_metric_is_not_promoted():
    row = _metrics()["G1-HOLD-SEN-BEZ-MAX"]
    assert row["role"] == "REPORT_ONLY"
    assert row["threshold"] == ""
    assert row["decision"] == "REPORT_ONLY"


def test_attempt_lineage_records_non_scientific_r1():
    decision = json.loads(
        (ROOT / "docs/F1_PCONSTR_G1_A1_R1_DECISION_SNAPSHOT_v1.json").read_text(encoding="utf-8")
    )
    assert decision["attempt_lineage"]["A1"] == "ABORTED_BEFORE_METRIC_EVALUATION"
    assert decision["attempt_lineage"]["A1_R1"] == "MECHANICAL_GEOGRAPHY_KEY_REMEDIATION"
    assert decision["remediation"]["scientific_change"] is False
    assert decision["remediation"]["metric_change"] is False
    assert decision["remediation"]["threshold_change"] is False
    assert decision["remediation"]["candidate_change"] is False
    assert decision["remediation"]["source_value_change"] is False


def test_runbundle_and_runner_hashes_are_frozen():
    cfg = _cfg()
    assert cfg["holdout"]["runbundle_zip_sha256"] == "8f37fb95d964ebd7c60d2ddf3befff10297b9e163438ac75d2caad9417877ea3"
    assert cfg["holdout"]["runner_sha256"] == "38fae45001fbd7adc73217915d20d3d06dbd8487d1201a4addc057a3e5cb3ecc"


def test_post_holdout_tuning_stays_forbidden():
    cfg = _cfg()
    state = cfg["controlled_state_after_commit"]
    assert state["candidate_selection_after_holdout"] == "FORBIDDEN"
    assert state["threshold_tuning_after_holdout"] == "FORBIDDEN"
    assert state["same_lineage_code_tuning_after_holdout"] == "FORBIDDEN"
    assert state["CAL"] == "CLOSED_DO_NOT_REOPEN"
    assert state["MiD_TEST"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"


def test_g2_remains_closed_and_no_plr_f3_change():
    state = _cfg()["controlled_state_after_commit"]
    assert state["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"
    assert state["spatial_plr_allocation"] is False
    assert state["f3_modified"] is False


def test_validation_snapshot_all_pass():
    with (ROOT / "docs/F1_PCONSTR_G1_A1_R1_VALIDATION_SNAPSHOT_v1.csv").open(
        encoding="utf-8", newline=""
    ) as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 15
    assert all(row["status"] == "PASS" for row in rows)


def test_main_audit_accepts_closure():
    audit = json.loads(
        (ROOT / "docs/F1_PCONSTR_G1_MAIN_AUDIT_v1.json").read_text(encoding="utf-8")
    )
    assert audit["audit_status"] == "ACCEPT_FOR_MAIN_G1_CLOSURE"
    assert audit["decision"] == "G1_PASS_CLOSE"
    assert audit["execution_integrity"]["failed_validation_rows"] == 0
