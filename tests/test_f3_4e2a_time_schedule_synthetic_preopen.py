from pathlib import Path

import yaml

from simfleet_edg.demand.time_schedule import validate_temporal_row

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4e2a_time_schedule_synthetic_preopen_v1.yaml"


def test_synthetic_preopen_never_opens_cal_or_test():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["boundaries"]["cal_rows_read"] == 0
    assert cfg["boundaries"]["cal_files_read"] == []
    assert cfg["boundaries"]["test_rows_read"] == 0
    assert cfg["boundaries"]["test_open_authorized"] is False


def test_candidate_selection_remains_none():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["candidate_registry"]["expected_candidates"] == 7
    assert cfg["boundaries"]["candidate_selection"] == "NONE"
    assert cfg["synthetic_metric_smoke"]["selection_authorized"] is False


def test_crn_contract_is_candidate_independent():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["synthetic_protocol"]["stochastic_replicates"] == 32
    assert cfg["synthetic_protocol"]["candidate_identity_in_rng_key"] is False
    assert cfg["synthetic_protocol"]["rng_namespace"] == "DG_TIME_SCHEDULE::TRIP::1"


def test_valid_temporal_row_is_accepted():
    ok, out = validate_temporal_row(
        480,
        30,
        previous_arrival_absolute_minute=None,
        trips_remaining_after_current=1,
    )
    assert ok is True
    assert out["arrival_absolute_minute"] == 510.0


def test_departure_before_previous_arrival_is_rejected():
    ok, _ = validate_temporal_row(
        100,
        10,
        previous_arrival_absolute_minute=120,
        trips_remaining_after_current=0,
    )
    assert ok is False


def test_nonfinal_midnight_crossing_is_rejected():
    ok, _ = validate_temporal_row(
        1430,
        20,
        previous_arrival_absolute_minute=None,
        trips_remaining_after_current=1,
    )
    assert ok is False


def test_final_midnight_crossing_can_be_valid():
    ok, out = validate_temporal_row(
        1430,
        20,
        previous_arrival_absolute_minute=None,
        trips_remaining_after_current=0,
    )
    assert ok is True
    assert out["arrival_day_offset"] == 1


def test_downstream_boundaries_remain_closed():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["boundaries"]["real_time_schedule_cal_open_authorized"] is False
    assert cfg["boundaries"]["distance_prior_real_cal_authorized"] is False
    assert cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED"
