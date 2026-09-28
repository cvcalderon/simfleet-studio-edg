import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4e1_time_schedule_cal_contract_freeze_v1.yaml"
REG = ROOT / "configs/f3/f3_4e1_time_schedule_candidate_registry_v1.json"


def test_candidate_universe():
    reg = json.loads(REG.read_text())
    assert reg["candidate_count"] == 7
    assert len({x["artifact_id"] for x in reg["candidates"]}) == 7


def test_cal_contract_closed():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["cal_physical_inputs"]["person_day_context_rows"] == 469
    assert cfg["cal_physical_inputs"]["time_trips_rows"] == 1243
    assert cfg["cal_physical_inputs"]["total_rows"] == 1712
    assert cfg["boundaries"]["cal_rows_read"] == 0


def test_primary_and_invariant():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["primary"]["id"] == "M2-TIME-01"
    assert cfg["primary"]["practical_margin"] == 0.005
    assert cfg["hard_guardrail"]["required"] == 0


def test_isolated_semantics():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["isolated"]["target_rows"] == 1243
    assert cfg["isolated"]["previous_time_prefix"] == "TEACHER_FORCED_EMPIRICAL"


def test_propagated_upstream():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["propagated"]["upstream"]["participation"] == "DG_PARTICIPATION::PART_A::PA1"
    assert cfg["propagated"]["upstream"]["trip_count"] == "DG_TRIP_COUNT::COUNT_REF::REFERENCE"
    assert cfg["propagated"]["upstream"]["activity_chain"] == "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2"
    assert cfg["propagated"]["primary_redefined"] is False


def test_stochastic_and_bootstrap():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["stochastic"]["replicates"] == 32
    assert cfg["stochastic"]["crn"] is True
    assert cfg["bootstrap"]["replicates"] == 1000
    assert cfg["bootstrap"]["confidence_level"] == 0.95


def test_boundaries():
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg["candidate_selection"] == "NONE"
    assert cfg["boundaries"]["distance_prior_real_cal_authorized"] is False
    assert cfg["boundaries"]["test_open_authorized"] is False
    assert cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED"
