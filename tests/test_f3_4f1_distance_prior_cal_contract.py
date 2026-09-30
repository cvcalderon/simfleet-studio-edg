import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4f1_distance_prior_cal_contract_freeze_v1.yaml"
REG = ROOT / "configs/f3/f3_4f1_distance_prior_candidate_registry_v1.json"


def test_candidate_universe():
    reg = json.loads(REG.read_text())
    assert reg["candidate_count"] == 5
    assert len({x["artifact_id"] for x in reg["candidates"]}) == 5


def test_contract_reads_zero_cal_rows():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["cal_physical_inputs"]["person_day_context_rows"] == 469
    assert cfg["cal_physical_inputs"]["distance_raw_rows"] == 1147
    assert cfg["cal_physical_inputs"]["distance_expanded_sensitivity_rows"] == 1257
    assert cfg["cal_physical_inputs"]["total_physical_rows"] == 2873
    assert cfg["boundaries"]["cal_rows_read"] == 0


def test_primary_and_margin():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["primary"]["id"] == "M2-DIST-01"
    assert cfg["primary"]["metric"] == "WEIGHTED_1D_WASSERSTEIN_DISTANCE_KM"
    assert cfg["primary"]["practical_margin_km"] == 0.25


def test_frozen_quantile_guardrails_and_mean_gap_resolution():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["summary_guardrails"]["p50_abs_error_worsening_km"]["tolerance"] == 0.50
    assert cfg["summary_guardrails"]["p90_abs_error_worsening_km"]["tolerance"] == 0.50
    assert cfg["summary_guardrails"]["p95_abs_error_worsening_km"]["tolerance"] == 0.50
    assert cfg["summary_guardrails"]["mean_abs_error"]["role"] == "MANDATORY_REPORT_ONLY_UNTHRESHOLDED"
    assert cfg["summary_guardrails"]["mean_abs_error"]["decision_driving"] is False


def test_isolated_semantics():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["isolated"]["target_rows"] == 1147
    assert cfg["isolated"]["no_silent_row_drop"] is True
    assert cfg["isolated"]["event_identity"] == "CONTEXT_ROW_ID_PLUS_SOURCE_TRIP_ID"


def test_propagated_upstream_and_role():
    cfg = yaml.safe_load(CFG.read_text())
    prop = cfg["propagated"]
    assert prop["upstream"]["participation"] == "DG_PARTICIPATION::PART_A::PA1"
    assert prop["upstream"]["trip_count"] == "DG_TRIP_COUNT::COUNT_REF::REFERENCE"
    assert prop["upstream"]["activity_chain"] == "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2"
    assert prop["upstream"]["time_schedule"] == "TIME_B_TB2"
    assert prop["role"] == "HARD_RUNTIME_ADMISSIBILITY_ONLY_AFTER_PROVISIONAL_SELECTION"
    assert prop["propagated_distribution_selection_metric"] == "NONE"
    assert prop["primary_redefined"] is False


def test_stochastic_and_bootstrap():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["stochastic"]["replicates"] == 32
    assert cfg["stochastic"]["crn"] is True
    assert cfg["bootstrap"]["replicates"] == 1000
    assert cfg["bootstrap"]["confidence_level"] == 0.95


def test_boundaries_and_runner():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["candidate_selection"] == "NONE"
    assert cfg["implementation"]["dedicated_runner_required"] is True
    assert cfg["implementation"]["generic_f3_3c_execute_candidate_direct_use"] is False
    assert cfg["boundaries"]["real_distance_prior_cal_open_authorized"] is False
    assert cfg["boundaries"]["test_open_authorized"] is False
    assert cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED"
