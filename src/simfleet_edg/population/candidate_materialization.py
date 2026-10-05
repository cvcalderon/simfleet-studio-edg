"""TRAIN-only candidate population materialization for F1-P_CONSTR-IMPL-03."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from simfleet_edg.common.population_materializer import (
    _recode_license,
    _recode_membership,
    _recode_person_access,
    _stock_quantity,
    age_infr_class,
    load_activity_recoding,
)
from simfleet_edg.common.population_split import normalize_source_id
from simfleet_edg.population.age_projection import age_zensus_11_v1, age_zensus_source_code
from simfleet_edg.population.equivalence import (
    CELL_ORDER,
    build_equivalence_catalog,
    donor_to_equivalence_map,
    fit_equivalence_plan,
)

MASTER_SEED: Final[int] = 20261005
H6_MASTER_SEED: Final[int] = 20261004
VARIANTS: Final[tuple[str, ...]] = (
    "P_TRS_V1_FINAL",
    "P_CONSTR_RMIN_V2_HD_U",
    "P_CONSTR_RMIN_V2_HD_W",
)

HOUSEHOLD_COLUMNS: Final[tuple[str, ...]] = (
    "household_id",
    "population_variant_id",
    "scale_id",
    "generation_seed",
    "draw_index",
    "bezirk_code",
    "bezirk_name",
    "household_size_code",
    "materialized_member_count",
    "household_size_topcoded",
    "household_size_generated",
    "six_plus_completion_policy",
    "source_household_id",
    "source_household_weight",
    "source_household_expansion_factor",
    "donor_split",
    "donor_eligibility",
    "equivalence_class_id",
    "donor_selection_policy",
    "home_zone_level",
    "home_zone_id",
    "provenance",
)

PERSON_COLUMNS: Final[tuple[str, ...]] = (
    "person_id",
    "household_id",
    "population_variant_id",
    "scale_id",
    "bezirk_code",
    "source_household_id",
    "source_person_id",
    "source_roster_slot",
    "person_enrichment_status",
    "sex",
    "sex_code",
    "age_years",
    "age_zensus_11_v1",
    "age_zensus_11_source_code",
    "age_infr_class",
    "age_topcoded",
    "primary_activity_status",
    "activity_observation_status",
    "employment_participation",
    "employment_intensity",
    "car_driver_license",
    "license_observation_status",
    "source_person_weight",
    "source_person_expansion_factor",
    "target_cell_assignment",
    "provenance",
)

RESOURCE_COLUMNS: Final[tuple[str, ...]] = (
    "household_id",
    "person_id",
    "population_variant_id",
    "resource_type",
    "scope",
    "relation_type",
    "quantity",
    "quantity_topcoded",
    "access_level",
    "membership_level",
    "observation_status",
    "source_role",
    "source_variable",
    "source_household_id",
    "source_person_id",
    "relation_id",
)

HOUSEHOLD_USECOLS: Final[tuple[str, ...]] = (
    "H_ID",
    "H_GEW",
    "H_HOCH",
    "H_ART",
    "H_GR",
    "H_ANZAUTO",
    "H_ANZMOTMOP",
    "H_ANZPED",
    "H_ANZRAD",
    "H_CS",
    "BLAND",
    "HP_SEX_1",
    "HP_SEX_2",
    "HP_SEX_3",
    "HP_SEX_4",
    "HP_SEX_5",
    "HP_SEX_6",
    "HP_ALTER_1",
    "HP_ALTER_2",
    "HP_ALTER_3",
    "HP_ALTER_4",
    "HP_ALTER_5",
    "HP_ALTER_6",
    "HP_TAET_1",
    "HP_TAET_2",
    "HP_TAET_3",
    "HP_TAET_4",
    "HP_TAET_5",
    "HP_TAET_6",
)

PERSON_USECOLS: Final[tuple[str, ...]] = (
    "HP_ID",
    "H_ID",
    "P_ID",
    "P_GEW",
    "P_HOCH",
    "HP_SEX",
    "HP_ALTER",
    "HP_TAET",
    "P_FS_PKW",
    "P_VAUTO",
    "P_VRAD",
    "P_VPED",
    "P_CS",
    "BLAND",
)


@dataclass(frozen=True)
class TrainCatalog:
    strict_households: pd.DataFrame
    six_plus_households: pd.DataFrame
    private_persons: pd.DataFrame
    person_lookup: dict[tuple[str, int], dict[str, object]]
    equivalence_catalog: pd.DataFrame
    donor_to_class: dict[str, str]
    split_by_household: dict[str, str]


@dataclass(frozen=True)
class VariantAudit:
    variant_id: str
    scale_id: str
    households: int
    persons: int
    resources: int
    strict_households: int
    six_plus_households: int
    donor_source_households: int
    equivalence_classes_used: int
    target_fit_l1: int
    target_fit_max_abs: int
    test_donor_violations: int
    calibration_donor_violations: int
    six_plus_target_violations: int


def _seed(master_seed: int, *parts: str) -> int:
    payload = "|".join([str(master_seed), *map(str, parts)]).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def _normalize_id_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_source_id).astype(str)


def _infer_person_slot(household_id: str, person_id: object) -> int | None:
    person_text = normalize_source_id(person_id)
    try:
        pid = int(person_text)
        hid = int(household_id)
    except ValueError:
        return None
    delta = pid - hid
    if 1 <= delta <= 6:
        return delta
    if 1 <= pid <= 6:
        return pid
    return None


def load_train_catalog(
    households_path: Path,
    persons_path: Path,
    split_manifest_path: Path,
    *,
    berlin_code: int = 11,
) -> TrainCatalog:
    """Load only static donor fields and retain only TRAIN private records for fitting."""
    split = pd.read_csv(
        split_manifest_path,
        usecols=[
            "source_household_id",
            "split",
            "class",
            "is_private_household",
            "joint_rmin_donor_eligible",
        ],
    )
    split["source_household_id"] = _normalize_id_series(split["source_household_id"])
    split_by_household = dict(
        zip(split["source_household_id"], split["split"].astype(str), strict=True)
    )

    strict_ids = set(
        split.loc[
            (split["split"] == "TRAIN") & split["joint_rmin_donor_eligible"],
            "source_household_id",
        ]
    )
    six_ids = set(
        split.loc[
            (split["split"] == "TRAIN") & (split["class"] == "HH_PRIVATE_6_PLUS"),
            "source_household_id",
        ]
    )
    private_train_ids = set(
        split.loc[
            (split["split"] == "TRAIN") & split["is_private_household"],
            "source_household_id",
        ]
    )

    households = pd.read_csv(
        households_path,
        usecols=list(HOUSEHOLD_USECOLS),
        low_memory=False,
    )
    households = households[households["BLAND"] == berlin_code].copy()
    households["H_ID"] = _normalize_id_series(households["H_ID"])
    strict = households[households["H_ID"].isin(strict_ids)].copy()
    six = households[households["H_ID"].isin(six_ids)].copy()
    strict = strict.sort_values("H_ID", key=lambda series: series.astype(int)).reset_index(drop=True)
    six = six.sort_values("H_ID", key=lambda series: series.astype(int)).reset_index(drop=True)
    if len(strict) != 1219:
        raise ValueError(f"Expected 1219 strict TRAIN households, observed {len(strict)}")
    if len(six) != 8:
        raise ValueError(f"Expected 8 TRAIN private 6+ templates, observed {len(six)}")

    persons = pd.read_csv(persons_path, usecols=list(PERSON_USECOLS), low_memory=False)
    persons = persons[persons["BLAND"] == berlin_code].copy()
    persons["H_ID"] = _normalize_id_series(persons["H_ID"])
    persons = persons[persons["H_ID"].isin(private_train_ids)].copy()
    persons = persons[
        persons["HP_SEX"].isin([1, 2]) & persons["HP_ALTER"].between(0, 85)
    ].copy()
    persons["HP_ID"] = _normalize_id_series(persons["HP_ID"])
    persons["P_ID"] = _normalize_id_series(persons["P_ID"])
    persons["age_zensus_11_source_code"] = persons["HP_ALTER"].astype(int).map(
        age_zensus_source_code
    )
    persons["sex_code"] = persons["HP_SEX"].astype(int).map({1: "GESM", 2: "GESW"})
    persons = persons.sort_values("HP_ID", key=lambda series: series.astype(int)).reset_index(
        drop=True
    )

    person_lookup: dict[tuple[str, int], dict[str, object]] = {}
    for row in persons.to_dict("records"):
        household_id = str(row["H_ID"])
        slot = _infer_person_slot(household_id, row["P_ID"])
        if slot is not None:
            person_lookup[(household_id, slot)] = row

    equivalence_catalog = build_equivalence_catalog(strict)
    return TrainCatalog(
        strict_households=strict,
        six_plus_households=six,
        private_persons=persons,
        person_lookup=person_lookup,
        equivalence_catalog=equivalence_catalog,
        donor_to_class=donor_to_equivalence_map(equivalence_catalog),
        split_by_household=split_by_household,
    )


def _weighted_exact_household_draw(
    strict_households: pd.DataFrame,
    target_persons: int,
    *,
    seed: int,
) -> list[str]:
    sizes = strict_households["H_GR"].to_numpy(dtype=np.int64)
    weights = strict_households["H_GEW"].to_numpy(dtype=float)
    probabilities = weights / weights.sum()
    rng = np.random.default_rng(seed)
    selected: list[str] = []
    materialized = 0
    while target_persons - materialized > 5:
        index = int(rng.choice(len(strict_households), p=probabilities))
        selected.append(str(strict_households.iloc[index]["H_ID"]))
        materialized += int(sizes[index])
    residual = target_persons - materialized
    if residual:
        candidates = np.flatnonzero(sizes == residual)
        candidate_weights = weights[candidates]
        choice = int(rng.choice(candidates, p=candidate_weights / candidate_weights.sum()))
        selected.append(str(strict_households.iloc[choice]["H_ID"]))
        materialized += residual
    if materialized != target_persons:
        raise AssertionError("P_TRS exact residual draw failed")
    return selected


def build_ptrs_selection(
    projected_cube: pd.DataFrame,
    catalog: TrainCatalog,
    *,
    scale_id: str,
    master_seed: int = MASTER_SEED,
) -> pd.DataFrame:
    """Draw TRAIN strict households without R_min composition fitting, by Bezirk total only."""
    rows: list[dict[str, object]] = []
    strict_lookup = catalog.strict_households.set_index("H_ID", drop=False)
    for bezirk_code in sorted(projected_cube["bezirk_code"].astype(str).unique()):
        frame = projected_cube[projected_cube["bezirk_code"].astype(str) == bezirk_code]
        bezirk_name = str(frame["bezirk_name"].iloc[0])
        strict_target = int(
            frame.loc[frame["household_size_code"] != "PERSON06UM", "projected_persons"].sum()
        )
        selected = _weighted_exact_household_draw(
            catalog.strict_households,
            strict_target,
            seed=_seed(master_seed, "PTRS_STRICT_DRAW", scale_id, bezirk_code),
        )
        for local_index, source_id in enumerate(selected, start=1):
            raw = strict_lookup.loc[source_id]
            rows.append(
                {
                    "bezirk_code": bezirk_code,
                    "bezirk_name": bezirk_name,
                    "local_household_index": local_index,
                    "source_household_id": source_id,
                    "household_size": int(raw["H_GR"]),
                    "household_size_code": f"PERSON0{int(raw['H_GR'])}",
                    "equivalence_class_id": catalog.donor_to_class[source_id],
                    "donor_selection_policy": "H_GEW_GLOBAL_TRAIN_WITH_REPLACEMENT",
                }
            )
    return pd.DataFrame(rows)


def build_pconstr_selection(
    plan: pd.DataFrame,
    catalog: TrainCatalog,
    *,
    scale_id: str,
    variant_id: str,
    master_seed: int = MASTER_SEED,
) -> pd.DataFrame:
    """Materialize fitted equivalence-class counts using U or H_GEW-weighted donors."""
    if variant_id not in {"P_CONSTR_RMIN_V2_HD_U", "P_CONSTR_RMIN_V2_HD_W"}:
        raise ValueError(f"Unsupported constrained variant: {variant_id}")
    weighted = variant_id.endswith("HD_W")
    strict_lookup = catalog.strict_households.set_index("H_ID", drop=False)
    class_to_ids = {
        str(row.equivalence_class_id): tuple(str(value) for value in row.donor_ids)
        for row in catalog.equivalence_catalog.itertuples(index=False)
    }

    prepared: list[dict[str, object]] = []
    for row in plan.itertuples(index=False):
        class_id = str(row.equivalence_class_id)
        donor_ids = class_to_ids[class_id]
        donor_weights = np.asarray(
            [float(strict_lookup.loc[source_id]["H_GEW"]) for source_id in donor_ids],
            dtype=float,
        )
        probabilities = donor_weights / donor_weights.sum() if weighted else None
        rng = np.random.default_rng(
            _seed(master_seed, variant_id, scale_id, str(row.bezirk_code), class_id)
        )
        if weighted:
            choices = rng.choice(donor_ids, size=int(row.n_households), replace=True, p=probabilities)
        else:
            choices = rng.choice(donor_ids, size=int(row.n_households), replace=True)
        for replica_round, source_id in enumerate(choices.tolist(), start=1):
            prepared.append(
                {
                    "bezirk_code": str(row.bezirk_code),
                    "bezirk_name": str(row.bezirk_name),
                    "household_size": int(row.household_size),
                    "household_size_code": str(row.household_size_code),
                    "equivalence_class_id": class_id,
                    "replica_round": replica_round,
                    "source_household_id": str(source_id),
                    "donor_selection_policy": (
                        "H_GEW_WITHIN_EQUIVALENCE_CLASS"
                        if weighted
                        else "UNIFORM_WITHIN_EQUIVALENCE_CLASS"
                    ),
                }
            )
    frame = pd.DataFrame(prepared)
    frame = frame.sort_values(
        ["bezirk_code", "replica_round", "equivalence_class_id", "source_household_id"]
    ).reset_index(drop=True)
    frame["local_household_index"] = frame.groupby("bezirk_code").cumcount() + 1
    return frame.drop(columns="replica_round")


def build_six_plus_blueprint(
    projected_cube: pd.DataFrame,
    h6_households: pd.DataFrame,
    catalog: TrainCatalog,
    *,
    scale_id: str,
    master_seed: int = H6_MASTER_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the common TRAIN-only 6+ household-template/person-donor blueprint."""
    templates = catalog.six_plus_households.set_index("H_ID", drop=False)
    template_ids = templates.index.astype(str).tolist()
    template_weights = templates["H_GEW"].to_numpy(dtype=float)
    template_probabilities = template_weights / template_weights.sum()

    person_groups: dict[tuple[str, str], pd.DataFrame] = {}
    for cell in CELL_ORDER:
        frame = catalog.private_persons[
            (catalog.private_persons["age_zensus_11_source_code"] == cell[0])
            & (catalog.private_persons["sex_code"] == cell[1])
        ].copy()
        if frame.empty:
            raise ValueError(f"No TRAIN private-person support for 6+ target cell {cell}")
        person_groups[cell] = frame.reset_index(drop=True)

    household_rows: list[dict[str, object]] = []
    person_rows: list[dict[str, object]] = []
    for bezirk_code in sorted(projected_cube["bezirk_code"].astype(str).unique()):
        cube = projected_cube[
            (projected_cube["bezirk_code"].astype(str) == bezirk_code)
            & (projected_cube["household_size_code"] == "PERSON06UM")
        ]
        bezirk_name = str(cube["bezirk_name"].iloc[0])
        h6 = h6_households[h6_households["bezirk_code"].astype(str) == bezirk_code].copy()
        h6 = h6.sort_values("h6_household_id").reset_index(drop=True)
        if int(h6["generated_household_size"].sum()) != int(cube["projected_persons"].sum()):
            raise ValueError(f"6+ size/person mismatch before donor materialization: {bezirk_code}")

        template_rng = np.random.default_rng(
            _seed(master_seed, "H6_TEMPLATE", scale_id, bezirk_code)
        )
        template_choices = template_rng.choice(
            template_ids, size=len(h6), replace=True, p=template_probabilities
        )

        target_cells: list[tuple[str, str]] = []
        target_lookup = {
            (str(row.age_zensus_11_source_code), str(row.sex_code)): int(row.projected_persons)
            for row in cube.itertuples(index=False)
        }
        for cell in CELL_ORDER:
            target_cells.extend([cell] * int(target_lookup.get(cell, 0)))
        target_rng = np.random.default_rng(
            _seed(master_seed, "H6_TARGET_SLOT_ASSIGNMENT", scale_id, bezirk_code)
        )
        target_array = np.asarray(target_cells, dtype=object)
        target_rng.shuffle(target_array)
        target_cells = [tuple(value) for value in target_array.tolist()]

        donor_rng = np.random.default_rng(
            _seed(master_seed, "H6_PERSON_DONOR", scale_id, bezirk_code)
        )
        cursor = 0
        for local_index, (h6_row, template_id) in enumerate(
            zip(h6.itertuples(index=False), template_choices, strict=True), start=1
        ):
            latent_size = int(h6_row.generated_household_size)
            household_rows.append(
                {
                    "bezirk_code": bezirk_code,
                    "bezirk_name": bezirk_name,
                    "local_h6_index": local_index,
                    "h6_household_id": str(h6_row.h6_household_id),
                    "materialized_member_count": latent_size,
                    "source_template_household_id": str(template_id),
                }
            )
            for slot in range(1, latent_size + 1):
                age_code, sex_code = target_cells[cursor]
                cursor += 1
                group = person_groups[(age_code, sex_code)]
                weights = group["P_GEW"].to_numpy(dtype=float)
                if np.all(np.isfinite(weights)) and np.all(weights > 0) and float(weights.sum()) > 0:
                    probabilities = weights / weights.sum()
                    weighting = "P_GEW"
                else:
                    probabilities = None
                    weighting = "UNIFORM_FALLBACK"
                donor_index = int(donor_rng.choice(len(group), p=probabilities))
                donor = group.iloc[donor_index]
                person_rows.append(
                    {
                        "bezirk_code": bezirk_code,
                        "local_h6_index": local_index,
                        "slot": slot,
                        "target_age_zensus_11_source_code": age_code,
                        "target_sex_code": sex_code,
                        "source_person_id": str(donor["HP_ID"]),
                        "source_person_household_id": str(donor["H_ID"]),
                        "person_donor_weighting": weighting,
                    }
                )
        if cursor != len(target_cells):
            raise AssertionError("6+ target-cell assignment did not consume all slots")

    return pd.DataFrame(household_rows), pd.DataFrame(person_rows)


def _household_resource_rows(
    household_id: str,
    variant_id: str,
    raw: pd.Series,
    *,
    relation_counter: list[int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    source_household_id = str(raw["H_ID"])
    for resource_type, source_variable, cap in (
        ("CAR", "H_ANZAUTO", 3),
        ("MOTORCYCLE_MOPED", "H_ANZMOTMOP", 3),
        ("EBIKE", "H_ANZPED", 10),
        ("BIKE", "H_ANZRAD", 10),
    ):
        quantity, topcoded, observation = _stock_quantity(str(raw[source_variable]), cap)
        relation_counter[0] += 1
        rows.append(
            {
                "household_id": household_id,
                "person_id": None,
                "population_variant_id": variant_id,
                "resource_type": resource_type,
                "scope": "HOUSEHOLD",
                "relation_type": "HOUSEHOLD_STOCK",
                "quantity": quantity,
                "quantity_topcoded": topcoded,
                "access_level": None,
                "membership_level": None,
                "observation_status": observation,
                "source_role": "DONOR_TEMPLATE",
                "source_variable": source_variable,
                "source_household_id": source_household_id,
                "source_person_id": None,
                "relation_id": f"REL_{variant_id}_{relation_counter[0]:08d}",
            }
        )
    membership, observation = _recode_membership("H_CS", str(raw["H_CS"]))
    relation_counter[0] += 1
    rows.append(
        {
            "household_id": household_id,
            "person_id": None,
            "population_variant_id": variant_id,
            "resource_type": "CARSHARING",
            "scope": "HOUSEHOLD",
            "relation_type": "MEMBERSHIP",
            "quantity": None,
            "quantity_topcoded": False,
            "access_level": None,
            "membership_level": membership,
            "observation_status": observation,
            "source_role": "DONOR_TEMPLATE",
            "source_variable": "H_CS",
            "source_household_id": source_household_id,
            "source_person_id": None,
            "relation_id": f"REL_{variant_id}_{relation_counter[0]:08d}",
        }
    )
    return rows


def _person_resource_rows(
    household_id: str,
    person_id: str,
    variant_id: str,
    raw: dict[str, object],
    *,
    relation_counter: list[int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    source_household_id = str(raw["H_ID"])
    source_person_id = str(raw["HP_ID"])
    for resource_type, source_variable in (("CAR", "P_VAUTO"), ("BIKE", "P_VRAD"), ("EBIKE", "P_VPED")):
        access, observation = _recode_person_access(source_variable, str(raw[source_variable]))
        relation_counter[0] += 1
        rows.append(
            {
                "household_id": household_id,
                "person_id": person_id,
                "population_variant_id": variant_id,
                "resource_type": resource_type,
                "scope": "PERSON",
                "relation_type": "PERSON_ACCESS",
                "quantity": None,
                "quantity_topcoded": False,
                "access_level": access,
                "membership_level": None,
                "observation_status": observation,
                "source_role": "PERSON_DONOR",
                "source_variable": source_variable,
                "source_household_id": source_household_id,
                "source_person_id": source_person_id,
                "relation_id": f"REL_{variant_id}_{relation_counter[0]:08d}",
            }
        )
    membership, observation = _recode_membership("P_CS", str(raw["P_CS"]))
    relation_counter[0] += 1
    rows.append(
        {
            "household_id": household_id,
            "person_id": person_id,
            "population_variant_id": variant_id,
            "resource_type": "CARSHARING",
            "scope": "PERSON",
            "relation_type": "MEMBERSHIP",
            "quantity": None,
            "quantity_topcoded": False,
            "access_level": None,
            "membership_level": membership,
            "observation_status": observation,
            "source_role": "PERSON_DONOR",
            "source_variable": "P_CS",
            "source_household_id": source_household_id,
            "source_person_id": source_person_id,
            "relation_id": f"REL_{variant_id}_{relation_counter[0]:08d}",
        }
    )
    return rows


def _person_row_from_static(
    *,
    person_id: str,
    household_id: str,
    variant_id: str,
    scale_id: str,
    bezirk_code: str,
    source_household_id: str,
    source_person_id: str | None,
    source_roster_slot: int | None,
    sex_code: str,
    age: int,
    activity_code: int,
    person_raw: dict[str, object] | None,
    activity_recoding: dict[int, tuple[str, str, str]],
    target_cell_assignment: str,
    provenance: str,
) -> dict[str, object]:
    sex = {"GESM": "MALE", "GESW": "FEMALE"}[sex_code]
    activity, employment_participation, employment_intensity = activity_recoding[activity_code]
    activity_observation = "MISSING_RESPONSE" if activity_code == 99 else "OBSERVED"
    if person_raw is None:
        license_value = "UNKNOWN"
        license_observation = "NO_PERSONEN_ENRICHMENT"
        weight = None
        expansion = None
        enrichment = "ROSTER_ONLY_NO_PERSONEN"
    else:
        license_value, license_observation = _recode_license(str(person_raw["P_FS_PKW"]))
        weight = float(person_raw["P_GEW"])
        expansion = float(person_raw["P_HOCH"])
        enrichment = "LINKED_PERSONEN"
    return {
        "person_id": person_id,
        "household_id": household_id,
        "population_variant_id": variant_id,
        "scale_id": scale_id,
        "bezirk_code": bezirk_code,
        "source_household_id": source_household_id,
        "source_person_id": source_person_id,
        "source_roster_slot": source_roster_slot,
        "person_enrichment_status": enrichment,
        "sex": sex,
        "sex_code": sex_code,
        "age_years": age,
        "age_zensus_11_v1": age_zensus_11_v1(age),
        "age_zensus_11_source_code": age_zensus_source_code(age),
        "age_infr_class": age_infr_class(age),
        "age_topcoded": age == 85,
        "primary_activity_status": activity,
        "activity_observation_status": activity_observation,
        "employment_participation": employment_participation,
        "employment_intensity": employment_intensity,
        "car_driver_license": license_value,
        "license_observation_status": license_observation,
        "source_person_weight": weight,
        "source_person_expansion_factor": expansion,
        "target_cell_assignment": target_cell_assignment,
        "provenance": provenance,
    }


def materialize_variant(
    selection_1_to_5: pd.DataFrame,
    h6_household_blueprint: pd.DataFrame,
    h6_person_blueprint: pd.DataFrame,
    catalog: TrainCatalog,
    activity_recoding: dict[int, tuple[str, str, str]],
    *,
    variant_id: str,
    scale_id: str,
    master_seed: int = MASTER_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Materialize one PREOPEN candidate at Bezirk level; PLR remains deferred."""
    strict_lookup = catalog.strict_households.set_index("H_ID", drop=False)
    six_lookup = catalog.six_plus_households.set_index("H_ID", drop=False)
    person_lookup_by_id = catalog.private_persons.set_index("HP_ID", drop=False)

    household_rows: list[dict[str, object]] = []
    person_rows: list[dict[str, object]] = []
    resource_rows: list[dict[str, object]] = []
    relation_counter = [0]
    global_household_index = 0

    # Exact-size 1..5 branch.
    for row in selection_1_to_5.sort_values(
        ["bezirk_code", "local_household_index"]
    ).itertuples(index=False):
        global_household_index += 1
        source_id = str(row.source_household_id)
        raw = strict_lookup.loc[source_id]
        household_id = f"HH_{variant_id}_{scale_id}_{global_household_index:07d}"
        household_size = int(raw["H_GR"])
        household_rows.append(
            {
                "household_id": household_id,
                "population_variant_id": variant_id,
                "scale_id": scale_id,
                "generation_seed": master_seed,
                "draw_index": global_household_index,
                "bezirk_code": str(row.bezirk_code),
                "bezirk_name": str(row.bezirk_name),
                "household_size_code": f"PERSON0{household_size}",
                "materialized_member_count": household_size,
                "household_size_topcoded": False,
                "household_size_generated": False,
                "six_plus_completion_policy": None,
                "source_household_id": source_id,
                "source_household_weight": float(raw["H_GEW"]),
                "source_household_expansion_factor": float(raw["H_HOCH"]),
                "donor_split": "TRAIN",
                "donor_eligibility": "STRICT_RMIN_DONOR",
                "equivalence_class_id": str(row.equivalence_class_id),
                "donor_selection_policy": str(row.donor_selection_policy),
                "home_zone_level": "BEZIRK",
                "home_zone_id": str(row.bezirk_code),
                "provenance": "TRAIN_WHOLE_HOUSEHOLD_DONOR",
            }
        )
        resource_rows.extend(
            _household_resource_rows(
                household_id, variant_id, raw, relation_counter=relation_counter
            )
        )
        for slot in range(1, household_size + 1):
            person_id = f"P_{variant_id}_{scale_id}_{global_household_index:07d}_{slot:02d}"
            sex_value = int(raw[f"HP_SEX_{slot}"])
            sex_code = {1: "GESM", 2: "GESW"}[sex_value]
            age = int(raw[f"HP_ALTER_{slot}"])
            activity_code = int(raw[f"HP_TAET_{slot}"])
            person_raw = catalog.person_lookup.get((source_id, slot))
            source_person_id = str(person_raw["HP_ID"]) if person_raw is not None else None
            person_rows.append(
                _person_row_from_static(
                    person_id=person_id,
                    household_id=household_id,
                    variant_id=variant_id,
                    scale_id=scale_id,
                    bezirk_code=str(row.bezirk_code),
                    source_household_id=source_id,
                    source_person_id=source_person_id,
                    source_roster_slot=slot,
                    sex_code=sex_code,
                    age=age,
                    activity_code=activity_code,
                    person_raw=person_raw,
                    activity_recoding=activity_recoding,
                    target_cell_assignment="DONOR_CONTRIBUTION",
                    provenance="TRAIN_HOUSEHOLD_ROSTER_STATIC",
                )
            )
            if person_raw is not None:
                resource_rows.extend(
                    _person_resource_rows(
                        household_id,
                        person_id,
                        variant_id,
                        person_raw,
                        relation_counter=relation_counter,
                    )
                )

    # Common 6+ branch. Blueprint source selections are variant-independent.
    h6_people_by_household = {
        (str(code), int(index)): frame.sort_values("slot")
        for (code, index), frame in h6_person_blueprint.groupby(
            ["bezirk_code", "local_h6_index"], sort=True
        )
    }
    for row in h6_household_blueprint.sort_values(
        ["bezirk_code", "local_h6_index"]
    ).itertuples(index=False):
        global_household_index += 1
        template_id = str(row.source_template_household_id)
        raw = six_lookup.loc[template_id]
        household_id = f"HH_{variant_id}_{scale_id}_{global_household_index:07d}"
        latent_size = int(row.materialized_member_count)
        household_rows.append(
            {
                "household_id": household_id,
                "population_variant_id": variant_id,
                "scale_id": scale_id,
                "generation_seed": H6_MASTER_SEED,
                "draw_index": global_household_index,
                "bezirk_code": str(row.bezirk_code),
                "bezirk_name": str(row.bezirk_name),
                "household_size_code": "PERSON06UM",
                "materialized_member_count": latent_size,
                "household_size_topcoded": True,
                "household_size_generated": True,
                "six_plus_completion_policy": "H6_COMPLETION_V1",
                "source_household_id": template_id,
                "source_household_weight": float(raw["H_GEW"]),
                "source_household_expansion_factor": float(raw["H_HOCH"]),
                "donor_split": "TRAIN",
                "donor_eligibility": "PARTIAL_6_PLUS_TEMPLATE",
                "equivalence_class_id": None,
                "donor_selection_policy": "H_GEW_6PLUS_TEMPLATE_COMMON_BRANCH",
                "home_zone_level": "BEZIRK",
                "home_zone_id": str(row.bezirk_code),
                "provenance": "H6_COMPLETION_V1_MODELLED_SIZE_TEMPLATE_DONOR",
            }
        )
        resource_rows.extend(
            _household_resource_rows(
                household_id, variant_id, raw, relation_counter=relation_counter
            )
        )
        people = h6_people_by_household[(str(row.bezirk_code), int(row.local_h6_index))]
        if len(people) != latent_size:
            raise AssertionError("6+ blueprint member count mismatch")
        for assignment in people.itertuples(index=False):
            slot = int(assignment.slot)
            person_id = f"P_{variant_id}_{scale_id}_{global_household_index:07d}_{slot:02d}"
            person_raw_series = person_lookup_by_id.loc[str(assignment.source_person_id)]
            person_raw = person_raw_series.to_dict()
            age = int(person_raw["HP_ALTER"])
            sex_code = str(assignment.target_sex_code)
            if age_zensus_source_code(age) != str(assignment.target_age_zensus_11_source_code):
                raise AssertionError("6+ person donor age cell differs from assigned target")
            if str(person_raw["sex_code"]) != sex_code:
                raise AssertionError("6+ person donor sex differs from assigned target")
            person_rows.append(
                _person_row_from_static(
                    person_id=person_id,
                    household_id=household_id,
                    variant_id=variant_id,
                    scale_id=scale_id,
                    bezirk_code=str(row.bezirk_code),
                    source_household_id=str(person_raw["H_ID"]),
                    source_person_id=str(person_raw["HP_ID"]),
                    source_roster_slot=None,
                    sex_code=sex_code,
                    age=age,
                    activity_code=int(person_raw["HP_TAET"]),
                    person_raw=person_raw,
                    activity_recoding=activity_recoding,
                    target_cell_assignment=(
                        f"{assignment.target_age_zensus_11_source_code}|{assignment.target_sex_code}"
                    ),
                    provenance="H6_SYNTHETIC_MEMBER_TRAIN_PERSON_DONOR",
                )
            )
            resource_rows.extend(
                _person_resource_rows(
                    household_id,
                    person_id,
                    variant_id,
                    person_raw,
                    relation_counter=relation_counter,
                )
            )

    households = pd.DataFrame(household_rows, columns=HOUSEHOLD_COLUMNS)
    persons = pd.DataFrame(person_rows, columns=PERSON_COLUMNS)
    resources = pd.DataFrame(resource_rows, columns=RESOURCE_COLUMNS)
    return households, persons, resources


def candidate_fit_audit(
    projected_cube: pd.DataFrame,
    households: pd.DataFrame,
    persons: pd.DataFrame,
) -> tuple[pd.DataFrame, int, int]:
    """Compare generated person cells against the frozen projected joint cube."""
    hh_code = households.set_index("household_id")["household_size_code"].to_dict()
    generated = persons.copy()
    generated["household_size_code"] = generated["household_id"].map(hh_code)
    counts = (
        generated.groupby(
            [
                "bezirk_code",
                "age_zensus_11_source_code",
                "sex_code",
                "household_size_code",
            ],
            sort=True,
        )
        .size()
        .rename("generated_persons")
        .reset_index()
    )
    target = projected_cube[
        [
            "bezirk_code",
            "bezirk_name",
            "age_zensus_11_source_code",
            "sex_code",
            "household_size_code",
            "projected_persons",
        ]
    ].copy()
    target["bezirk_code"] = target["bezirk_code"].astype(str)
    audit = target.merge(
        counts,
        on=["bezirk_code", "age_zensus_11_source_code", "sex_code", "household_size_code"],
        how="left",
    )
    audit["generated_persons"] = audit["generated_persons"].fillna(0).astype(int)
    audit["signed_error"] = audit["generated_persons"] - audit["projected_persons"].astype(int)
    audit["absolute_error"] = audit["signed_error"].abs()
    return audit, int(audit["absolute_error"].sum()), int(audit["absolute_error"].max())


def validate_variant(
    variant_id: str,
    scale_id: str,
    projected_cube: pd.DataFrame,
    households: pd.DataFrame,
    persons: pd.DataFrame,
    resources: pd.DataFrame,
    catalog: TrainCatalog,
) -> VariantAudit:
    if int(households["materialized_member_count"].sum()) != len(persons):
        raise AssertionError("Household/person cardinality mismatch")
    if persons["person_id"].duplicated().any() or households["household_id"].duplicated().any():
        raise AssertionError("Generated entity IDs are not unique")
    if not persons["household_id"].isin(set(households["household_id"])).all():
        raise AssertionError("Orphan generated person")

    source_household_ids = set(households["source_household_id"].astype(str)) | set(
        persons["source_household_id"].astype(str)
    )
    test_violations = sum(
        catalog.split_by_household.get(source_id) == "TEST" for source_id in source_household_ids
    )
    calibration_violations = sum(
        catalog.split_by_household.get(source_id) == "CALIBRATION"
        for source_id in source_household_ids
    )

    six_households = households[households["household_size_code"] == "PERSON06UM"]
    six_persons = persons[persons["household_id"].isin(set(six_households["household_id"]))]
    six_target = projected_cube[projected_cube["household_size_code"] == "PERSON06UM"]
    six_counts = (
        six_persons.groupby(
            ["bezirk_code", "age_zensus_11_source_code", "sex_code"], sort=True
        )
        .size()
        .rename("generated")
        .reset_index()
    )
    six_compare = six_target[
        ["bezirk_code", "age_zensus_11_source_code", "sex_code", "projected_persons"]
    ].merge(
        six_counts,
        on=["bezirk_code", "age_zensus_11_source_code", "sex_code"],
        how="left",
    )
    six_compare["generated"] = six_compare["generated"].fillna(0).astype(int)
    six_violations = int(
        (six_compare["generated"] != six_compare["projected_persons"].astype(int)).sum()
    )
    if (six_households["materialized_member_count"] < 6).any():
        six_violations += int((six_households["materialized_member_count"] < 6).sum())

    _, fit_l1, fit_max = candidate_fit_audit(projected_cube, households, persons)
    equivalence_classes_used = int(
        households["equivalence_class_id"].dropna().astype(str).nunique()
    )
    return VariantAudit(
        variant_id=variant_id,
        scale_id=scale_id,
        households=int(len(households)),
        persons=int(len(persons)),
        resources=int(len(resources)),
        strict_households=int((households["household_size_code"] != "PERSON06UM").sum()),
        six_plus_households=int((households["household_size_code"] == "PERSON06UM").sum()),
        donor_source_households=len(source_household_ids),
        equivalence_classes_used=equivalence_classes_used,
        target_fit_l1=fit_l1,
        target_fit_max_abs=fit_max,
        test_donor_violations=int(test_violations),
        calibration_donor_violations=int(calibration_violations),
        six_plus_target_violations=int(six_violations),
    )


def build_scale_candidates(
    projected_cube: pd.DataFrame,
    h6_households: pd.DataFrame,
    catalog: TrainCatalog,
    activity_recoding_path: Path,
    *,
    scale_id: str,
) -> tuple[
    dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]],
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Build P_TRS + HD_U + HD_W PREOPEN candidates for one frozen scale."""
    activity_recoding = load_activity_recoding(activity_recoding_path)
    plan, class_fit, fit_audit = fit_equivalence_plan(projected_cube, catalog.equivalence_catalog)
    if fit_audit.target_persons != fit_audit.generated_persons:
        raise AssertionError("Constrained equivalence plan changed target person total")

    h6_household_blueprint, h6_person_blueprint = build_six_plus_blueprint(
        projected_cube, h6_households, catalog, scale_id=scale_id
    )

    selections = {
        "P_TRS_V1_FINAL": build_ptrs_selection(
            projected_cube, catalog, scale_id=scale_id
        ),
        "P_CONSTR_RMIN_V2_HD_U": build_pconstr_selection(
            plan,
            catalog,
            scale_id=scale_id,
            variant_id="P_CONSTR_RMIN_V2_HD_U",
        ),
        "P_CONSTR_RMIN_V2_HD_W": build_pconstr_selection(
            plan,
            catalog,
            scale_id=scale_id,
            variant_id="P_CONSTR_RMIN_V2_HD_W",
        ),
    }
    outputs: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]] = {}
    audits: list[dict[str, object]] = []
    for variant_id in VARIANTS:
        tables = materialize_variant(
            selections[variant_id],
            h6_household_blueprint,
            h6_person_blueprint,
            catalog,
            activity_recoding,
            variant_id=variant_id,
            scale_id=scale_id,
        )
        outputs[variant_id] = tables
        audit = validate_variant(
            variant_id,
            scale_id,
            projected_cube,
            *tables,
            catalog,
        )
        audits.append(audit.__dict__)

    audit_frame = pd.DataFrame(audits)
    return outputs, audit_frame, plan, class_fit
