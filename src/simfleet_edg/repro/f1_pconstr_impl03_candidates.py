"""PREOPEN orchestration for TRAIN-only F1 P_CONSTR candidate materialization."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from simfleet_edg.population.candidate_materialization import (
    build_scale_candidates,
    load_train_catalog,
)
from simfleet_edg.population.equivalence import fit_equivalence_plan
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


def build_upstream_scale(
    root: Path,
    config: dict[str, Any],
    scale_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recompute a scale and frozen H6 sizes from IMPL-01/02 source-controlled code."""
    impl01_config = yaml.safe_load(
        (root / config["upstream"]["impl01_config"]).read_text(encoding="utf-8")
    )
    sources = {
        table_id: normalize_flat_count_zip(
            root / spec["path"], table_id=table_id, expected_sha256=spec["sha256"]
        )
        for table_id, spec in impl01_config["sources"].items()
    }
    validate_fit_source_categories(sources)
    full_cube, _ = reconcile_all_bezirke(
        sources["1000A-3082"], sources["1000A-1029"], sources["1000A-2071"]
    )
    projected, _ = project_reconciled_cube(full_cube, scale_id=scale_id)
    full_h6 = derive_full_scale_h6_prior(sources["5000H-1001"], full_cube)
    h6_prior = scale_h6_prior(full_h6, projected, scale_id=scale_id)
    h6_households, _ = materialize_h6_household_sizes(
        projected, h6_prior, scale_id=scale_id
    )
    return projected, h6_households


def load_catalog_from_config(root: Path, config: dict[str, Any]):
    source = config["sources"]
    return load_train_catalog(
        root / source["mid_households"]["path"],
        root / source["mid_persons"]["path"],
        root / source["r2_split_manifest"]["path"],
        berlin_code=int(config["berlin"]["BLAND"]),
    )


def build_impl03_preopen_summary(root: Path, config_path: Path) -> dict[str, Any]:
    """Build S candidates and M constrained plan without CAL/TEST/holdout access."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    catalog = load_catalog_from_config(root, config)
    projected_s, h6_s = build_upstream_scale(root, config, "S")
    outputs, audits, plan_s, _ = build_scale_candidates(
        projected_s,
        h6_s,
        catalog,
        root / config["sources"]["activity_recoding"]["path"],
        scale_id="S",
    )

    projected_m, _ = build_upstream_scale(root, config, "M")
    plan_m, _, fit_m = fit_equivalence_plan(projected_m, catalog.equivalence_catalog)

    variant_rows = audits.sort_values("variant_id").to_dict("records")
    variant_by_id = {str(row["variant_id"]): row for row in variant_rows}

    # Verify that the common 6+ branch uses the same source selections across candidates.
    h6_signatures: dict[str, tuple[tuple[object, ...], ...]] = {}
    for variant_id, (households, persons, _) in outputs.items():
        h6_households = households[households["household_size_code"] == "PERSON06UM"].copy()
        h6_households = h6_households.sort_values(["bezirk_code", "draw_index"]).reset_index(
            drop=True
        )
        ordinal = {
            household_id: (str(code), int(index))
            for code, household_id, index in zip(
                h6_households["bezirk_code"],
                h6_households["household_id"],
                h6_households.groupby("bezirk_code").cumcount() + 1,
                strict=True,
            )
        }
        h6_persons = persons[persons["household_id"].isin(set(h6_households["household_id"]))].copy()
        h6_persons["common_household_key"] = h6_persons["household_id"].map(ordinal)
        h6_persons["common_slot"] = h6_persons.groupby("household_id").cumcount() + 1
        signature_rows = []
        for row in h6_persons.sort_values(["common_household_key", "common_slot"]).itertuples(
            index=False
        ):
            signature_rows.append(
                (
                    row.common_household_key,
                    int(row.common_slot),
                    str(row.source_person_id),
                    str(row.age_zensus_11_source_code),
                    str(row.sex_code),
                    int(row.age_years),
                    str(row.primary_activity_status),
                )
            )
        h6_signatures[variant_id] = tuple(signature_rows)
    common_h6 = len(set(h6_signatures.values())) == 1

    return {
        "phase": config["phase_id"],
        "catalog": {
            "strict_train_households": int(len(catalog.strict_households)),
            "train_six_plus_templates": int(len(catalog.six_plus_households)),
            "train_private_person_donors": int(len(catalog.private_persons)),
            "equivalence_classes": int(len(catalog.equivalence_catalog)),
            "person_donor_support_cells": int(
                catalog.private_persons[
                    ["age_zensus_11_source_code", "sex_code"]
                ].drop_duplicates().shape[0]
            ),
        },
        "S": {
            "plan_rows": int(len(plan_s)),
            "variants": variant_by_id,
            "common_six_plus_branch": bool(common_h6),
        },
        "M_plan": {
            **asdict(fit_m),
            "plan_rows": int(len(plan_m)),
            "positive_equivalence_classes": int(plan_m["equivalence_class_id"].nunique()),
        },
        "boundaries": dict(config["boundaries"]),
    }
