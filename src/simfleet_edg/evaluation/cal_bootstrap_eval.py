"""Paired household-bootstrap evaluation over standardized F3.3c evidence."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from simfleet_edg.evaluation.cal_bootstrap import (
    BootstrapInterval,
    household_bootstrap_multipliers,
    percentile_interval,
)

MetricFunction = Callable[[pd.DataFrame, np.ndarray], float]


def mean_metric_over_replicates(
    evidence: pd.DataFrame,
    row_multiplier: np.ndarray,
    metric_fn: MetricFunction,
    *,
    expected_replicates: int = 32,
) -> float:
    if len(evidence) != len(row_multiplier):
        raise ValueError("evidence/multiplier length mismatch")
    values: list[float] = []
    replicate_ids = sorted(int(x) for x in evidence["replicate_id"].unique())
    if replicate_ids != list(range(expected_replicates)):
        raise ValueError("replicate coverage must be exactly 0..31")
    for replicate_id in replicate_ids:
        mask = evidence["replicate_id"].to_numpy(dtype=int) == replicate_id
        mult = row_multiplier[mask]
        frame = evidence.loc[mask].reset_index(drop=True)
        if mult.sum() == 0:
            raise ValueError("bootstrap replicate removed all rows")
        values.append(float(metric_fn(frame, mult)))
    return float(np.mean(values))


def paired_household_bootstrap_difference(
    incumbent: pd.DataFrame,
    challenger: pd.DataFrame,
    metric_fn: MetricFunction,
    *,
    bootstrap_replicates: int,
    seed: int,
    confidence_level: float = 0.95,
    expected_stochastic_replicates: int = 32,
) -> tuple[np.ndarray, BootstrapInterval]:
    if bootstrap_replicates != 1000:
        raise ValueError("F3.1c freezes household bootstrap replicates to 1000")
    pair_key = [
        "component",
        "evaluation_mode",
        "replicate_id",
        "evaluation_person_id",
        "source_household_id",
        "event_index",
        "draw_index",
    ]
    left = incumbent.sort_values(pair_key).reset_index(drop=True)
    right = challenger.sort_values(pair_key).reset_index(drop=True)
    if not left[pair_key].equals(right[pair_key]):
        raise ValueError("incumbent/challenger evidence is not paired")
    if not left["seed_u64"].equals(right["seed_u64"]):
        raise ValueError("CRN seeds differ across candidates")

    households = left["source_household_id"].astype(str).to_numpy()
    multipliers = household_bootstrap_multipliers(
        households,
        replicates=bootstrap_replicates,
        seed=seed,
    )
    differences = np.empty(bootstrap_replicates, dtype=float)
    for index, multiplier in enumerate(multipliers):
        incumbent_metric = mean_metric_over_replicates(
            left,
            multiplier,
            metric_fn,
            expected_replicates=expected_stochastic_replicates,
        )
        challenger_metric = mean_metric_over_replicates(
            right,
            multiplier,
            metric_fn,
            expected_replicates=expected_stochastic_replicates,
        )
        differences[index] = incumbent_metric - challenger_metric

    interval = percentile_interval(differences, confidence_level=confidence_level)
    return differences, interval
