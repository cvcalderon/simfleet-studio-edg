"""PREOPEN execution core for F1 P_CONSTR IMPL-02 scale projection and 6+ structure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from simfleet_edg.population.reconciliation import reconcile_all_bezirke
from simfleet_edg.population.scale_projection import project_reconciled_cube
from simfleet_edg.population.six_plus import (
    derive_full_scale_h6_prior,
    materialize_h6_household_sizes,
    scale_h6_prior,
)
from simfleet_edg.population.zensus_controls import (
    normalize_flat_count_zip,
    validate_fit_source_categories,
)


def build_impl02_summary(root: Path, config_path: Path) -> dict[str, Any]:
    """Recompute IMPL-01 controls and derive all frozen IMPL-02 PREOPEN anchors."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    source_config = yaml.safe_load(
        (root / config["upstream"]["impl01_config"]).read_text(encoding="utf-8")
    )
    sources = {
        table_id: normalize_flat_count_zip(
            root / spec["path"], table_id=table_id, expected_sha256=spec["sha256"]
        )
        for table_id, spec in source_config["sources"].items()
    }
    validate_fit_source_categories(sources)
    full_cube, _ = reconcile_all_bezirke(
        sources["1000A-3082"], sources["1000A-1029"], sources["1000A-2071"]
    )
    full_h6 = derive_full_scale_h6_prior(sources["5000H-1001"], full_cube)

    scales: dict[str, Any] = {}
    for scale_id in config["scale_projection"]["scale_order"]:
        projected, projection_audit = project_reconciled_cube(full_cube, scale_id=scale_id)
        h6_prior = scale_h6_prior(full_h6, projected, scale_id=scale_id)
        h6_households, h6_audit = materialize_h6_household_sizes(
            projected, h6_prior, scale_id=scale_id
        )
        p6_by_bezirk = (
            projected[projected["household_size_code"] == "PERSON06UM"]
            .groupby("bezirk_code", sort=True)["projected_persons"]
            .sum()
            .astype(int)
            .tolist()
        )
        bezirk_targets = (
            projected.groupby("bezirk_code", sort=True)["projected_persons"]
            .sum()
            .astype(int)
            .tolist()
        )
        scales[scale_id] = {
            "target_persons": projection_audit.target_persons,
            "bezirk_targets": bezirk_targets,
            "projection_l1_scaled_numerator": projection_audit.l1_scaled_numerator,
            "structural_zero_violations": projection_audit.structural_zero_violations,
            "divisibility_violations_sizes_1_to_5": (
                projection_audit.divisibility_violations_sizes_1_to_5
            ),
            "all_bezirk_targets_exact": projection_audit.all_bezirk_targets_exact,
            "p6_persons_by_bezirk": p6_by_bezirk,
            "p6_persons_berlin": int(sum(p6_by_bezirk)),
            "h6_households_by_bezirk": h6_prior["scale_h6_households"].astype(int).tolist(),
            "h6_households_berlin": int(h6_audit.household_count),
            "h6_persons_materialized": int(h6_audit.person_count),
            "h6_min_size": int(h6_audit.minimum_household_size),
            "h6_max_size": int(h6_audit.maximum_household_size),
            "h6_size6_count": int((h6_households["generated_household_size"] == 6).sum()),
            "h6_gt10_count": int((h6_households["generated_household_size"] > 10).sum()),
            "h6_household_count_exact": h6_audit.household_count_exact,
            "h6_person_count_exact": h6_audit.person_count_exact,
            "h6_all_at_least_six": h6_audit.all_households_at_least_six,
        }

    return {
        "phase": config["phase_id"],
        "reference_persons": int(full_cube["fit_target_value"].sum()),
        "full_h6_households_by_bezirk": full_h6["full_scale_h6_prior"].astype(int).tolist(),
        "full_h6_households_berlin": int(full_h6["full_scale_h6_prior"].sum()),
        "scales": scales,
        "boundaries": dict(config["boundaries"]),
    }
