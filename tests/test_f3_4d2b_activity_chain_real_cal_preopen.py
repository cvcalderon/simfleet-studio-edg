from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from simfleet_edg.evaluation import activity_chain_cal_real as real

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f3/f3_4d2b_activity_chain_real_cal_preopen_v1.yaml"


def test_preopen_contract_is_closed() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert cfg["phase"] == "F3.4d-2b"
    assert cfg["component"] == "DG_ACTIVITY_CHAIN"
    assert cfg["required_parent_commit"] == "6ea9abcd7e720d62940933aee12534797440c996"
    assert cfg["cal_input"]["expected_physical_rows"] == 1853
    assert cfg["cal_input"]["expected_fixed_cohort_days"] == 319
    assert cfg["cal_input"]["expected_isolated_transition_rows"] == 1065
    assert cfg["evaluation"]["primary_metric"] == "WEIGHTED_NEXT_ACTIVITY_LOG_LOSS"
    assert cfg["evaluation"]["practical_margin"] == 0.01
    assert cfg["evaluation"]["stochastic_replicates"] == 32
    assert cfg["evaluation"]["household_bootstrap_replicates"] == 1000
    assert cfg["preopen"]["cal_rows_read"] == 0
    assert cfg["preopen"]["candidate_selection"] == "NONE"
    assert cfg["preopen"]["real_activity_chain_cal_open_authorized"] is False
    assert cfg["preopen"]["test_open_authorized"] is False
    assert cfg["preopen"]["next_component_authorized"] is False
    assert cfg["preopen"]["formal_g2"] == "NOT_EVALUATED"


def test_authorization_template_is_non_executable() -> None:
    payload = json.loads(
        (ROOT / "docs/F3_4D2B_EXECUTION_AUTHORIZATION_TEMPLATE_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["real_activity_chain_cal_open_authorized"] is False
    assert payload["candidate_artifacts"] == 6
    assert payload["candidate_selection_at_entry"] == "NONE"
    assert set(payload["allowed_cal_files"]) == {
        "person_day_context.csv",
        "chain_days.csv",
        "chain_transitions.csv",
    }
    assert payload["test_open_authorized"] is False
    assert payload["next_component_authorized"] is False
    assert payload["formal_g2"] == "NOT_EVALUATED"


def test_false_authorization_fails_before_git_or_cal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "phase": "F3.4d-2b",
                "component": "DG_ACTIVITY_CHAIN",
                "authorized_implementation_commit": "unused",
                "real_activity_chain_cal_open_authorized": False,
                "candidate_artifacts": 6,
                "candidate_selection_at_entry": "NONE",
                "allowed_cal_files": [
                    "person_day_context.csv",
                    "chain_days.csv",
                    "chain_transitions.csv",
                ],
                "test_open_authorized": False,
                "next_component_authorized": False,
                "formal_g2": "NOT_EVALUATED",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(real, "_git", lambda *_args: pytest.fail("git must not run"))
    with pytest.raises(PermissionError, match="real_activity_chain_cal_open_authorized"):
        real.load_authorization(auth, tmp_path)


def test_invalid_authorization_creates_no_partial_runbundle(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "phase": "F3.4d-2b",
                "component": "DG_ACTIVITY_CHAIN",
                "real_activity_chain_cal_open_authorized": False,
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "run"
    with pytest.raises(PermissionError):
        real.run_controlled_activity_chain_cal(
            ROOT,
            out,
            CONFIG,
            auth,
            write_stochastic_evidence=False,
        )
    assert not out.exists()
    assert not out.with_name("run.partial").exists()


class _FakeChainAdapter:
    def sample_initial_activity(self, *, seed: int) -> str:
        assert seed >= 0
        return "HOME"

    def sample_transition(self, frame: pd.DataFrame, *, seed: int) -> dict[str, object]:
        assert len(frame) == 1
        assert seed >= 0
        return {
            "next_activity": "WORK",
            "support": ["HOME", "WORK"],
            "probabilities": [0.0, 1.0],
        }


def _day() -> pd.Series:
    return pd.Series(
        {
            "context_row_id": "c1",
            "source_household_id_target": "h1",
            "source_person_id_target": "p1",
            "source_trip_count_analogue": 2,
            "first_origin_activity": "HOME",
            "final_destination_activity": "HOME",
            "target_return_home": 1,
            "day_weight_P_GEW": 2.0,
            "row_id": "c1",
            "source_household_id_context": "h1",
            "source_person_id_context": "p1",
            "fit_weight_P_GEW": 2.0,
            "age_infr_class": "A",
        }
    )


def _purpose_artifact() -> dict[str, object]:
    return {
        "primitive_id": "CHAIN_PURPOSE_ATTRIBUTION_V1",
        "levels": [],
        "global_return_eligible": {
            "p_return_previous": 0.0,
            "source_n": 30,
        },
    }


def test_generated_chain_has_exact_k_and_distinct_rng_slots() -> None:
    rows, final = real._generate_chain(
        _FakeChainAdapter(),
        _day(),
        trip_count=2,
        replicate=0,
        purpose_artifact=_purpose_artifact(),
    )
    assert len(rows) == 2
    assert final == "WORK"
    assert [row["trip_sequence_index"] for row in rows] == [1, 2]
    assert all(row["generated_purpose"] == "WORK_COMMUTE" for row in rows)
    assert rows[0]["transition_seed_u64"] != rows[0]["purpose_seed_u64"]
    assert rows[1]["transition_seed_u64"] != rows[1]["purpose_seed_u64"]


def test_generated_no_trip_has_zero_transitions() -> None:
    rows, final = real._generate_chain(
        _FakeChainAdapter(),
        _day(),
        trip_count=0,
        replicate=0,
        purpose_artifact=_purpose_artifact(),
    )
    assert rows == []
    assert final is None


def test_guardrail_worsening_tolerances_are_exact() -> None:
    incumbent = {
        "m2_purp_01_tvd_mean32": 0.10,
        "m2_trans_01_tvd_mean32": 0.20,
        "m2_ret_01_abs_error_mean32": 0.03,
    }
    challenger = {
        "m2_purp_01_tvd_mean32": 0.105,
        "m2_trans_01_tvd_mean32": 0.205,
        "m2_ret_01_abs_error_mean32": 0.04,
    }
    passed, row = real._compare_guardrails(incumbent, challenger)
    assert passed
    assert row["m2_purp_01_tvd_mean32_tolerance"] == 0.005
    assert row["m2_trans_01_tvd_mean32_tolerance"] == 0.005
    assert row["m2_ret_01_abs_error_mean32_tolerance"] == 0.01


def test_propagated_zero_mobile_denominator_hard_fails() -> None:
    observed = {
        "purpose_distribution": pd.Series({"WORK_COMMUTE": 1.0}),
        "transition_distribution": pd.Series({"HOME->WORK": 1.0}),
        "return_home_share": 1.0,
    }
    with pytest.raises(ValueError, match="Generated transition denominator is zero"):
        real._metrics_from_generated(
            observed,
            [],
            [
                {
                    "generated_trip_count": 0,
                    "generated_return_home": 0,
                    "weight": 1.0,
                }
            ],
        )
