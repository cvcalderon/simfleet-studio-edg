from pathlib import Path


def test_contract_freezes_expected_candidates_and_modes():
    text = Path("configs/f3/f3_4c1_trip_count_cal_contract_v1.yaml").read_text(
        encoding="utf-8"
    )
    assert "DG_TRIP_COUNT::COUNT_REF::REFERENCE" in text
    assert "DG_TRIP_COUNT::COUNT_A::CA1" in text
    assert "DG_TRIP_COUNT::COUNT_A::CA2" in text
    assert "DG_TRIP_COUNT::COUNT_A::CA3" in text
    assert "DG_TRIP_COUNT::COUNT_B::CB1" in text
    assert "selection_evaluation_mode: ISOLATED" in text
    assert "guardrail_only: true" in text


def test_contract_freezes_upstream_pa1():
    text = Path("configs/f3/f3_4c1_trip_count_cal_contract_v1.yaml").read_text(
        encoding="utf-8"
    )
    assert "DG_PARTICIPATION::PART_A::PA1" in text
    assert "state: MAIN_FROZEN" in text


def test_contract_keeps_test_and_real_cal_closed():
    text = Path("configs/f3/f3_4c1_trip_count_cal_contract_v1.yaml").read_text(
        encoding="utf-8"
    )
    assert "real_trip_count_cal_open_authorized: false" in text
    assert "test_open_authorized: false" in text
    assert "formal_g2: NOT_EVALUATED" in text


def test_expected_cal_counts_are_predeclared():
    text = Path("configs/f3/f3_4c1_trip_count_cal_contract_v1.yaml").read_text(
        encoding="utf-8"
    )
    assert "trip_count_expected_rows: 381" in text
    assert "participation_expected_rows: 460" in text
    assert "person_day_context_expected_rows: 469" in text
