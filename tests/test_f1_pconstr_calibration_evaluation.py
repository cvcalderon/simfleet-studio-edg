from __future__ import annotations

import pandas as pd

from simfleet_edg.population.calibration_evaluation import (
    FamilyResult,
    bike_ebike_family_error,
    bootstrap_materiality_threshold,
    conditional_tvd_family,
    select_constrained_variant,
    select_final_candidate,
    stock_category,
    tvd,
)


def test_tvd_exact() -> None:
    assert tvd({"A": 0.5, "B": 0.5}, {"A": 0.25, "B": 0.75}) == 0.25


def test_stock_categories_are_frozen() -> None:
    assert [stock_category(v, cap=3) for v in [0, 1, 2, 3, 8]] == [
        "ZERO", "ONE", "TWO", "THREE_PLUS", "THREE_PLUS"
    ]
    assert [stock_category(v, cap=10) for v in [0, 1, 2, 9, 10, 12]] == [
        "ZERO", "ONE", "TWO_TO_NINE", "TWO_TO_NINE", "TEN_PLUS", "TEN_PLUS"
    ]


def test_conditional_tvd_uses_reference_mass_and_excludes_low_n() -> None:
    ref = pd.DataFrame({
        "g": ["A"] * 30 + ["B"] * 29,
        "y": ["X"] * 15 + ["Y"] * 15 + ["X"] * 29,
        "w": [1.0] * 59,
    })
    syn = pd.DataFrame({"g": ["A", "A", "B"], "y": ["X", "X", "Y"], "w": [1.0, 1.0, 1.0]})
    out = conditional_tvd_family(
        ref, syn, family_id="F", condition_cols=["g"], outcome_col="y",
        reference_weight_col="w", synthetic_weight_col="w", low_n_threshold=30,
    )
    assert out.decision_cells == 1
    assert out.low_n_cells == 1
    assert out.error == 0.5


def test_bike_family_uses_worst_submetric() -> None:
    out = bike_ebike_family_error(FamilyResult("B", 0.1, 2, 0), FamilyResult("E", 0.3, 2, 0))
    assert out.error == 0.3


def test_bootstrap_threshold_is_deterministic() -> None:
    ids = ["H1", "H2", "H3"]
    def fn(sample: list[str]) -> float:
        return sample.count("H1") / len(sample)
    a = bootstrap_materiality_threshold(ids, fn, family_id="X", baseline_error=1/3, replicates=100)
    b = bootstrap_materiality_threshold(ids, fn, family_id="X", baseline_error=1/3, replicates=100)
    assert a == b
    assert a >= 0


def test_hd_w_promotes_only_with_material_gain_and_no_material_degradation() -> None:
    tau = {"A": 0.02, "B": 0.02}
    assert select_constrained_variant({"A": 0.20, "B": 0.10}, {"A": 0.15, "B": 0.11}, tau).endswith("HD_W")
    assert select_constrained_variant({"A": 0.20, "B": 0.10}, {"A": 0.15, "B": 0.14}, tau).endswith("HD_U")


def test_hd_u_retained_on_inconclusive_tie() -> None:
    tau = {"A": 0.02}
    assert select_constrained_variant({"A": 0.20}, {"A": 0.19}, tau).endswith("HD_U")


def test_constrained_promotes_only_with_fit_and_preservation_pass() -> None:
    tau = {"A": 0.02, "B": 0.03}
    winner = select_final_candidate(
        "P_CONSTR_RMIN_V2_HD_U", {"A": 0.11, "B": 0.12}, {"A": 0.10, "B": 0.10}, tau,
        constrained_fit_l1=350, constrained_fit_max_abs=4,
        ptrs_fit_l1=3968, ptrs_fit_max_abs=29, engineering_gate_pass=True,
    )
    assert winner == "P_CONSTR_RMIN_V2_HD_U"


def test_ptrs_retained_if_preservation_degrades_materially() -> None:
    tau = {"A": 0.02}
    winner = select_final_candidate(
        "P_CONSTR_RMIN_V2_HD_U", {"A": 0.14}, {"A": 0.10}, tau,
        constrained_fit_l1=350, constrained_fit_max_abs=4,
        ptrs_fit_l1=3968, ptrs_fit_max_abs=29, engineering_gate_pass=True,
    )
    assert winner == "P_TRS_V1_FINAL"


def test_ptrs_retained_if_fit_does_not_dominate() -> None:
    tau = {"A": 0.02}
    winner = select_final_candidate(
        "P_CONSTR_RMIN_V2_HD_U", {"A": 0.10}, {"A": 0.10}, tau,
        constrained_fit_l1=3968, constrained_fit_max_abs=29,
        ptrs_fit_l1=3968, ptrs_fit_max_abs=29, engineering_gate_pass=True,
    )
    assert winner == "P_TRS_V1_FINAL"
