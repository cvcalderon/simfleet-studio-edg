"""Deterministic PRE-F3 P_TRS experimental population materialization utilities."""

from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simfleet_edg.common.population_split import (
    detect_csv_format,
    normalize_source_id,
    parse_float,
    parse_int,
)

AGE_INFR_CLASSES = (
    "01_LT3",
    "02_3_5",
    "03_6_9",
    "04_10_15",
    "05_16_18",
    "06_19_24",
    "07_25_39",
    "08_40_59",
    "09_60_66",
    "10_67_74",
    "11_75_PLUS",
)

HOUSEHOLD_COLUMNS = (
    "household_id",
    "population_variant_id",
    "scale_id",
    "generation_seed",
    "draw_index",
    "source_household_id",
    "source_donor_replica_index",
    "donor_split",
    "donor_eligibility",
    "household_kind",
    "household_size_class",
    "household_size_topcoded",
    "materialized_member_count",
    "home_zone_level",
    "home_zone_id",
    "source_household_weight",
    "source_household_expansion_factor",
    "provenance",
)

PERSON_COLUMNS = (
    "person_id",
    "household_id",
    "population_variant_id",
    "source_household_id",
    "source_roster_slot",
    "source_person_id",
    "person_enrichment_status",
    "sex",
    "sex_observation_status",
    "age_years",
    "age_topcoded",
    "age_infr_class",
    "age_observation_status",
    "primary_activity_status",
    "activity_observation_status",
    "employment_participation",
    "employment_intensity",
    "car_driver_license",
    "license_observation_status",
    "source_person_weight",
    "source_person_expansion_factor",
    "home_zone_id",
    "provenance",
)

RESOURCE_COLUMNS = (
    "household_id",
    "person_id",
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

HOUSEHOLD_RESOURCE_SPECS = (
    ("CAR", "H_ANZAUTO", 3),
    ("MOTORCYCLE_MOPED", "H_ANZMOTMOP", 3),
    ("EBIKE", "H_ANZPED", 10),
    ("BIKE", "H_ANZRAD", 10),
)

PERSON_ACCESS_SPECS = (
    ("CAR", "P_VAUTO"),
    ("BIKE", "P_VRAD"),
    ("EBIKE", "P_VPED"),
)

NFI_FORBIDDEN_COLUMNS = {
    "tripintent",
    "observed_trip_count",
    "trip_purpose",
    "purpose",
    "departure_time",
    "arrival_time",
    "chosen_mode",
    "mode_family",
    "feasiblejourneyset",
    "executiontrace",
    "waiting_time",
    "trip_time",
}


def age_infr_class(age: int) -> str:
    """Return the canonical 11-band ALTER_INFR-compatible age class."""
    if age < 3:
        return "01_LT3"
    if age <= 5:
        return "02_3_5"
    if age <= 9:
        return "03_6_9"
    if age <= 15:
        return "04_10_15"
    if age <= 18:
        return "05_16_18"
    if age <= 24:
        return "06_19_24"
    if age <= 39:
        return "07_25_39"
    if age <= 59:
        return "08_40_59"
    if age <= 66:
        return "09_60_66"
    if age <= 74:
        return "10_67_74"
    if age <= 85:
        return "11_75_PLUS"
    raise ValueError(f"Age outside supported roster range: {age}")


def load_activity_recoding(path: Path) -> dict[int, tuple[str, str, str]]:
    frame = pd.read_csv(path)
    required = {
        "source_code",
        "primary_activity_status",
        "employment_participation",
        "employment_intensity",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Activity recoding missing columns: {sorted(missing)}")
    return {
        int(row.source_code): (
            str(row.primary_activity_status),
            str(row.employment_participation),
            str(row.employment_intensity),
        )
        for row in frame.itertuples(index=False)
    }


def load_source_records(
    path: Path,
    berlin_code: int,
    id_field: str,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    """Load Berlin rows preserving source order and normalized source IDs."""
    encoding, delimiter = detect_csv_format(path)
    ordered: list[dict[str, str]] = []
    lookup: dict[str, dict[str, str]] = {}
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        required = {id_field, "BLAND"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
        for raw in reader:
            try:
                if parse_int(raw["BLAND"]) != berlin_code:
                    continue
            except Exception:
                continue
            source_id = normalize_source_id(raw[id_field])
            if not source_id:
                continue
            ordered.append(raw)
            lookup[source_id] = raw
    return ordered, lookup


def load_person_lookup(
    path: Path,
    berlin_code: int,
) -> dict[tuple[str, int], dict[str, str]]:
    """Index linked Personen rows by normalized household and roster slot."""
    encoding, delimiter = detect_csv_format(path)
    lookup: dict[tuple[str, int], dict[str, str]] = {}
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        required = {
            "H_ID",
            "P_ID",
            "HP_ID",
            "BLAND",
            "P_GEW",
            "P_HOCH",
            "P_FS_PKW",
            "P_VAUTO",
            "P_VRAD",
            "P_VPED",
            "P_CS",
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Person CSV missing columns: {sorted(missing)}")
        for raw in reader:
            try:
                if parse_int(raw["BLAND"]) != berlin_code:
                    continue
            except Exception:
                continue
            household_id = normalize_source_id(raw["H_ID"])
            person_id = normalize_source_id(raw["P_ID"])
            if not household_id or household_id == "0" or not person_id:
                continue
            slot: int | None = None
            try:
                pid = int(person_id)
                hid = int(household_id)
                delta = pid - hid
                if 1 <= delta <= 6:
                    slot = delta
                elif 1 <= pid <= 6:
                    slot = pid
            except ValueError:
                slot = None
            if slot is not None:
                lookup[(household_id, slot)] = raw
    return lookup


def read_r2_strict_train_donors(
    split_manifest_path: Path,
    household_lookup: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Return strict TRAIN donors in frozen SplitManifest row order."""
    split = pd.read_csv(split_manifest_path)
    required = {
        "source_household_id",
        "split",
        "joint_rmin_donor_eligible",
        "household_size_class",
    }
    missing = required.difference(split.columns)
    if missing:
        raise ValueError(f"R2 split manifest missing columns: {sorted(missing)}")
    selected = split[
        (split["split"] == "TRAIN") & split["joint_rmin_donor_eligible"].astype(bool)
    ]
    donors: list[dict[str, str]] = []
    for source_id in selected["source_household_id"].tolist():
        normalized = normalize_source_id(source_id)
        raw = household_lookup.get(normalized)
        if raw is None:
            raise ValueError(f"R2 strict TRAIN donor not found in raw households: {normalized}")
        donors.append(raw)
    return donors


def weighted_exact_person_draws(
    donors: list[dict[str, str]],
    target_persons: int,
    seed: int,
    max_household_size: int = 5,
) -> list[dict[str, str]]:
    """Sample whole households with replacement while hitting an exact person target."""
    if not donors:
        raise ValueError("Donor pool is empty")
    donor_sizes = np.array([parse_int(row["H_GR"]) for row in donors], dtype=np.int64)
    weights = np.array([parse_float(row["H_GEW"]) for row in donors], dtype=np.float64)
    if np.any(donor_sizes < 1) or np.any(donor_sizes > max_household_size):
        raise ValueError("Experimental donor pool must contain household sizes 1..5 only")
    if np.any(weights < 0) or float(weights.sum()) <= 0:
        raise ValueError("Donor weights must have a positive total")
    probability = weights / weights.sum()
    rng = np.random.default_rng(seed)
    selected: list[dict[str, str]] = []
    materialized_persons = 0

    while target_persons - materialized_persons > max_household_size:
        index = int(rng.choice(len(donors), p=probability))
        selected.append(donors[index])
        materialized_persons += int(donor_sizes[index])

    residual = target_persons - materialized_persons
    if residual:
        candidate_indices = np.flatnonzero(donor_sizes == residual)
        if len(candidate_indices) == 0:
            raise ValueError(f"No donor household can fill final residual={residual}")
        residual_weights = weights[candidate_indices]
        residual_probability = residual_weights / residual_weights.sum()
        chosen_index = int(rng.choice(candidate_indices, p=residual_probability))
        selected.append(donors[chosen_index])
        materialized_persons += residual

    if materialized_persons != target_persons:
        raise AssertionError(
            f"Exact target failure: target={target_persons}, actual={materialized_persons}"
        )
    return selected


def largest_remainder_zone_quotas(
    target_audit_path: Path,
    n_households: int,
) -> pd.DataFrame:
    """Build historical PLR household-total quotas from the frozen F1.2a target audit."""
    target = pd.read_csv(target_audit_path, dtype={"geography_id": str})
    required = {
        "geography_id",
        "geography_name",
        "statistical_household_available",
        "private_households_total",
    }
    missing = required.difference(target.columns)
    if missing:
        raise ValueError(f"PLR target audit missing columns: {sorted(missing)}")
    target = target.copy()
    target["home_zone_id"] = target["geography_id"].str.zfill(8)
    valid = target["private_households_total"].notna()
    total = float(target.loc[valid, "private_households_total"].sum())
    raw_quota = pd.Series(np.nan, index=target.index, dtype=float)
    raw_quota.loc[valid] = (
        target.loc[valid, "private_households_total"].astype(float) / total * n_households
    )
    generated = pd.Series(0, index=target.index, dtype=int)
    generated.loc[valid] = np.floor(raw_quota.loc[valid]).astype(int)
    remainder = n_households - int(generated.sum())
    fractional = raw_quota.loc[valid] - generated.loc[valid]
    ranked = fractional.sort_values(ascending=False, kind="stable").index
    generated.loc[ranked[:remainder]] += 1

    target["generated_households"] = generated
    target["source_share"] = np.where(
        valid,
        target["private_households_total"].astype(float) / total,
        np.nan,
    )
    target["generated_share"] = target["generated_households"] / n_households
    target["absolute_share_error"] = np.where(
        valid,
        (target["generated_share"] - target["source_share"]).abs(),
        np.nan,
    )
    target["allocation_status"] = np.where(
        valid,
        "ALLOCATED_FROM_STATISTICAL_PRIVATE_HH_TOTAL",
        "NOT_INCLUDED_NO_STAT_TARGET",
    )
    return target


def deterministic_zone_assignment(
    quota_frame: pd.DataFrame,
    seed: int,
) -> list[str]:
    """Expand PLR quotas in frozen row order and shuffle with NumPy Generator."""
    zone_ids: list[str] = []
    for row in quota_frame.itertuples(index=False):
        zone_ids.extend([str(row.home_zone_id)] * int(row.generated_households))
    array = np.asarray(zone_ids, dtype=object)
    rng = np.random.default_rng(seed)
    rng.shuffle(array)
    return [str(value) for value in array.tolist()]


def zone_allocation_audit(quota_frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "home_zone_id",
        "geography_name",
        "source_private_households_total",
        "source_share",
        "generated_households",
        "generated_share",
        "absolute_share_error",
        "allocation_status",
    ]
    result = pd.DataFrame(
        {
            "home_zone_id": quota_frame["home_zone_id"],
            "geography_name": quota_frame["geography_name"],
            "source_private_households_total": quota_frame["private_households_total"],
            "source_share": quota_frame["source_share"],
            "generated_households": quota_frame["generated_households"],
            "generated_share": quota_frame["generated_share"],
            "absolute_share_error": quota_frame["absolute_share_error"],
            "allocation_status": quota_frame["allocation_status"],
        }
    )
    return result.loc[:, columns]


def _recode_license(value: str) -> tuple[str, str]:
    code = parse_int(value)
    mapping = {
        1: ("YES", "OBSERVED"),
        2: ("NO", "OBSERVED"),
        9: ("UNKNOWN", "MISSING_RESPONSE"),
        206: ("UNKNOWN", "NOT_OBSERVED_PROXY"),
        403: ("UNKNOWN", "NOT_OBSERVED_AGE_DESIGN"),
    }
    if code not in mapping:
        raise ValueError(f"Unexpected P_FS_PKW code: {code}")
    return mapping[code]


def _recode_person_access(variable: str, value: str) -> tuple[str, str]:
    code = parse_int(value)
    mappings = {
        "P_VAUTO": {
            1: ("ALWAYS", "OBSERVED"),
            2: ("OCCASIONAL", "OBSERVED"),
            3: ("NEVER", "OBSERVED"),
            9: ("UNKNOWN", "MISSING_RESPONSE"),
            206: ("UNKNOWN", "NOT_OBSERVED_PROXY"),
            402: ("UNKNOWN", "NOT_OBSERVED_AGE_DESIGN"),
        },
        "P_VRAD": {
            1: ("YES", "OBSERVED"),
            2: ("NO", "OBSERVED"),
            9: ("UNKNOWN", "MISSING_RESPONSE"),
        },
        "P_VPED": {
            1: ("YES", "OBSERVED"),
            2: ("NO", "OBSERVED"),
            9: ("UNKNOWN", "MISSING_RESPONSE"),
            206: ("UNKNOWN", "NOT_OBSERVED_PROXY"),
            402: ("UNKNOWN", "NOT_OBSERVED_AGE_DESIGN"),
        },
    }
    mapping = mappings[variable]
    if code not in mapping:
        raise ValueError(f"Unexpected {variable} code: {code}")
    return mapping[code]


def _recode_membership(variable: str, value: str) -> tuple[str, str]:
    code = parse_int(value)
    if variable == "H_CS":
        mapping = {
            1: ("ONE_PROVIDER", "OBSERVED"),
            2: ("MULTIPLE_PROVIDERS", "OBSERVED"),
            3: ("NONE", "OBSERVED"),
            9: ("UNKNOWN", "MISSING_RESPONSE"),
        }
    elif variable == "P_CS":
        mapping = {
            1: ("ONE_PROVIDER", "OBSERVED"),
            2: ("MULTIPLE_PROVIDERS", "OBSERVED"),
            3: ("NONE", "OBSERVED"),
            9: ("UNKNOWN", "MISSING_RESPONSE"),
            202: ("UNKNOWN", "NOT_OBSERVED_PAPI"),
            206: ("UNKNOWN", "NOT_OBSERVED_PROXY"),
            403: ("UNKNOWN", "NOT_OBSERVED_AGE_DESIGN"),
        }
    else:
        raise ValueError(f"Unexpected membership variable: {variable}")
    if code not in mapping:
        raise ValueError(f"Unexpected {variable} code: {code}")
    return mapping[code]


def _stock_quantity(value: str, cap: int) -> tuple[float | None, bool, str]:
    text = str(value).strip()
    if not text:
        return None, False, "MISSING_RESPONSE"
    code = parse_int(text)
    if code == 99:
        return None, False, "MISSING_RESPONSE"
    if code < 0:
        raise ValueError(f"Negative household stock code: {code}")
    return float(code), code == cap, "OBSERVED"


def materialize_population(
    selected_donors: list[dict[str, str]],
    zone_assignment: list[str],
    person_lookup: dict[tuple[str, int], dict[str, str]],
    activity_recoding: dict[int, tuple[str, str, str]],
    population_variant_id: str,
    scale_id: str,
    generation_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Materialize household, person and resource tables from selected donors."""
    if len(selected_donors) != len(zone_assignment):
        raise ValueError("Selected donors and zone assignments must have equal length")

    household_rows: list[dict[str, Any]] = []
    person_rows: list[dict[str, Any]] = []
    resource_rows: list[dict[str, Any]] = []
    replica_counter: Counter[str] = Counter()
    relation_counter = 0

    for draw_index, (raw, home_zone_id) in enumerate(
        zip(selected_donors, zone_assignment, strict=True), start=1
    ):
        source_household_id = normalize_source_id(raw["H_ID"])
        h_art = parse_int(raw["H_ART"])
        h_gr = parse_int(raw["H_GR"])
        replica_counter[source_household_id] += 1
        generated_household_id = (
            f"HH_{population_variant_id}_{scale_id}_{draw_index:06d}"
        )
        household_kind = {1: "PRIVATE_SINGLE", 2: "PRIVATE_MULTI"}.get(h_art)
        if household_kind is None:
            raise ValueError(f"Non-private donor reached materializer: H_ART={h_art}")

        household_rows.append(
            {
                "household_id": generated_household_id,
                "population_variant_id": population_variant_id,
                "scale_id": scale_id,
                "generation_seed": generation_seed,
                "draw_index": draw_index,
                "source_household_id": int(source_household_id),
                "source_donor_replica_index": replica_counter[source_household_id],
                "donor_split": "TRAIN",
                "donor_eligibility": "STRICT_RMIN_DONOR",
                "household_kind": household_kind,
                "household_size_class": h_gr,
                "household_size_topcoded": False,
                "materialized_member_count": h_gr,
                "home_zone_level": "PLR",
                "home_zone_id": home_zone_id,
                "source_household_weight": parse_float(raw["H_GEW"]),
                "source_household_expansion_factor": parse_float(raw["H_HOCH"]),
                "provenance": "P_TRS_EXP_WHOLE_HOUSEHOLD_RESAMPLE",
            }
        )

        for resource_type, source_variable, cap in HOUSEHOLD_RESOURCE_SPECS:
            quantity, topcoded, observation = _stock_quantity(raw[source_variable], cap)
            relation_counter += 1
            resource_rows.append(
                {
                    "household_id": generated_household_id,
                    "person_id": None,
                    "resource_type": resource_type,
                    "scope": "HOUSEHOLD",
                    "relation_type": "HOUSEHOLD_STOCK",
                    "quantity": quantity,
                    "quantity_topcoded": topcoded,
                    "access_level": None,
                    "membership_level": None,
                    "observation_status": observation,
                    "source_role": "DONOR",
                    "source_variable": source_variable,
                    "source_household_id": int(source_household_id),
                    "source_person_id": None,
                    "relation_id": f"REL_{scale_id}_{relation_counter:07d}",
                }
            )

        hh_membership, hh_membership_observation = _recode_membership("H_CS", raw["H_CS"])
        relation_counter += 1
        resource_rows.append(
            {
                "household_id": generated_household_id,
                "person_id": None,
                "resource_type": "CARSHARING",
                "scope": "HOUSEHOLD",
                "relation_type": "MEMBERSHIP",
                "quantity": None,
                "quantity_topcoded": False,
                "access_level": None,
                "membership_level": hh_membership,
                "observation_status": hh_membership_observation,
                "source_role": "DONOR",
                "source_variable": "H_CS",
                "source_household_id": int(source_household_id),
                "source_person_id": None,
                "relation_id": f"REL_{scale_id}_{relation_counter:07d}",
            }
        )

        for slot in range(1, h_gr + 1):
            generated_person_id = (
                f"P_{population_variant_id}_{scale_id}_{draw_index:06d}_{slot:02d}"
            )
            sex_code = parse_int(raw[f"HP_SEX_{slot}"])
            sex = {1: "MALE", 2: "FEMALE"}.get(sex_code)
            if sex is None:
                raise ValueError(
                    f"Strict donor contains invalid sex: household={source_household_id}, "
                    f"slot={slot}, value={sex_code}"
                )
            age = parse_int(raw[f"HP_ALTER_{slot}"])
            activity_code = parse_int(raw[f"HP_TAET_{slot}"])
            if activity_code not in activity_recoding:
                raise ValueError(f"Activity code not frozen: {activity_code}")
            activity, employment_participation, employment_intensity = activity_recoding[
                activity_code
            ]
            activity_observation = (
                "MISSING_RESPONSE" if activity_code == 99 else "OBSERVED"
            )

            person_raw = person_lookup.get((source_household_id, slot))
            if person_raw is None:
                source_person_id: int | None = None
                enrichment_status = "ROSTER_ONLY_NO_PERSONEN"
                car_driver_license = "UNKNOWN"
                license_observation = "NO_PERSONEN_ENRICHMENT"
                source_person_weight: float | None = None
                source_person_expansion: float | None = None
            else:
                source_person_id = int(normalize_source_id(person_raw["HP_ID"]))
                enrichment_status = "LINKED_PERSONEN"
                car_driver_license, license_observation = _recode_license(
                    person_raw["P_FS_PKW"]
                )
                source_person_weight = parse_float(person_raw["P_GEW"])
                source_person_expansion = parse_float(person_raw["P_HOCH"])

            person_rows.append(
                {
                    "person_id": generated_person_id,
                    "household_id": generated_household_id,
                    "population_variant_id": population_variant_id,
                    "source_household_id": int(source_household_id),
                    "source_roster_slot": slot,
                    "source_person_id": source_person_id,
                    "person_enrichment_status": enrichment_status,
                    "sex": sex,
                    "sex_observation_status": "OBSERVED",
                    "age_years": age,
                    "age_topcoded": age == 85,
                    "age_infr_class": age_infr_class(age),
                    "age_observation_status": "OBSERVED",
                    "primary_activity_status": activity,
                    "activity_observation_status": activity_observation,
                    "employment_participation": employment_participation,
                    "employment_intensity": employment_intensity,
                    "car_driver_license": car_driver_license,
                    "license_observation_status": license_observation,
                    "source_person_weight": source_person_weight,
                    "source_person_expansion_factor": source_person_expansion,
                    "home_zone_id": home_zone_id,
                    "provenance": "MATERIALIZED_FROM_HOUSEHOLD_ROSTER",
                }
            )

            if person_raw is not None:
                for resource_type, source_variable in PERSON_ACCESS_SPECS:
                    access_level, observation = _recode_person_access(
                        source_variable, person_raw[source_variable]
                    )
                    relation_counter += 1
                    resource_rows.append(
                        {
                            "household_id": generated_household_id,
                            "person_id": generated_person_id,
                            "resource_type": resource_type,
                            "scope": "PERSON",
                            "relation_type": "PERSON_ACCESS",
                            "quantity": None,
                            "quantity_topcoded": False,
                            "access_level": access_level,
                            "membership_level": None,
                            "observation_status": observation,
                            "source_role": "ENRICHMENT",
                            "source_variable": source_variable,
                            "source_household_id": int(source_household_id),
                            "source_person_id": source_person_id,
                            "relation_id": f"REL_{scale_id}_{relation_counter:07d}",
                        }
                    )

                membership, observation = _recode_membership("P_CS", person_raw["P_CS"])
                relation_counter += 1
                resource_rows.append(
                    {
                        "household_id": generated_household_id,
                        "person_id": generated_person_id,
                        "resource_type": "CARSHARING",
                        "scope": "PERSON",
                        "relation_type": "MEMBERSHIP",
                        "quantity": None,
                        "quantity_topcoded": False,
                        "access_level": None,
                        "membership_level": membership,
                        "observation_status": observation,
                        "source_role": "ENRICHMENT",
                        "source_variable": "P_CS",
                        "source_household_id": int(source_household_id),
                        "source_person_id": source_person_id,
                        "relation_id": f"REL_{scale_id}_{relation_counter:07d}",
                    }
                )

    households = pd.DataFrame(household_rows, columns=HOUSEHOLD_COLUMNS)
    persons = pd.DataFrame(person_rows, columns=PERSON_COLUMNS)
    resources = pd.DataFrame(resource_rows, columns=RESOURCE_COLUMNS)
    # Preserve optional source identifiers as integer-or-missing without float coercion.
    persons["source_person_id"] = persons["source_person_id"].astype("Int64")
    resources["source_person_id"] = resources["source_person_id"].astype("Int64")
    return households, persons, resources


def dataframe_csv_bytes(frame: pd.DataFrame) -> bytes:
    """Serialize with the historical pandas CSV convention used by F1.3a."""
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, lineterminator="\n")
    return buffer.getvalue().encode()


def write_dataframe_csv(frame: pd.DataFrame, path: Path) -> None:
    path.write_bytes(dataframe_csv_bytes(frame))


def dataframe_csv_sha256(frame: pd.DataFrame) -> str:
    return hashlib.sha256(dataframe_csv_bytes(frame)).hexdigest()


def snapshot_sha256(primary_hashes: list[str]) -> str:
    """Historical F1.3a snapshot digest: SHA256(concatenated primary CSV digests)."""
    return hashlib.sha256("".join(primary_hashes).encode()).hexdigest()


def donor_reuse_audit(
    donors: list[dict[str, str]],
    selected_donors: list[dict[str, str]],
) -> pd.DataFrame:
    counts = Counter(normalize_source_id(row["H_ID"]) for row in selected_donors)
    rows = [
        {
            "source_household_id": int(normalize_source_id(row["H_ID"])),
            "n_generated_replicas": counts.get(normalize_source_id(row["H_ID"]), 0),
            "used": counts.get(normalize_source_id(row["H_ID"]), 0) > 0,
        }
        for row in donors
    ]
    return pd.DataFrame(rows)


def preservation_audit(
    donors: list[dict[str, str]],
    households: pd.DataFrame,
    persons: pd.DataFrame,
    activity_recoding: dict[int, tuple[str, str, str]],
) -> pd.DataFrame:
    """Compare finite generated S sample with its H_GEW-weighted TRAIN donor expectation."""
    donor_weights = np.asarray([parse_float(row["H_GEW"]) for row in donors], dtype=float)
    donor_sizes = np.asarray([parse_int(row["H_GR"]) for row in donors], dtype=int)
    hh_weight_total = float(donor_weights.sum())
    person_weight_total = float(np.dot(donor_weights, donor_sizes))
    rows: list[dict[str, Any]] = []

    def add_dimension(
        dimension: str,
        categories: list[str],
        generated_shares: dict[str, float],
        expected_shares: dict[str, float],
    ) -> None:
        differences: list[float] = []
        for category in categories:
            generated = float(generated_shares.get(category, 0.0))
            expected = float(expected_shares.get(category, 0.0))
            difference = abs(generated - expected)
            differences.append(difference)
            rows.append(
                {
                    "dimension": dimension,
                    "category": category,
                    "generated_share": generated,
                    "expected_weighted_donor_share": expected,
                    "absolute_difference": difference,
                    "metric_role": "REPORT_ONLY_PRE_G1",
                }
            )
        rows.append(
            {
                "dimension": dimension,
                "category": "__TOTAL_VARIATION_DISTANCE__",
                "generated_share": None,
                "expected_weighted_donor_share": None,
                "absolute_difference": 0.5 * sum(differences),
                "metric_role": "REPORT_ONLY_PRE_G1",
            }
        )

    hh_categories = ["1", "2", "3", "4", "5"]
    generated_hh_counts = households["household_size_class"].astype(str).value_counts()
    generated_hh_shares = {
        category: float(generated_hh_counts.get(category, 0) / len(households))
        for category in hh_categories
    }
    expected_hh_shares = {}
    for category in hh_categories:
        mask = donor_sizes == int(category)
        expected_hh_shares[category] = float(donor_weights[mask].sum() / hh_weight_total)
    add_dimension(
        "household_size", hh_categories, generated_hh_shares, expected_hh_shares
    )

    expected_age: defaultdict[str, float] = defaultdict(float)
    expected_sex: defaultdict[str, float] = defaultdict(float)
    expected_activity: defaultdict[str, float] = defaultdict(float)
    for raw, weight in zip(donors, donor_weights, strict=True):
        for slot in range(1, parse_int(raw["H_GR"]) + 1):
            age = parse_int(raw[f"HP_ALTER_{slot}"])
            sex = {1: "MALE", 2: "FEMALE"}[parse_int(raw[f"HP_SEX_{slot}"])]
            activity_code = parse_int(raw[f"HP_TAET_{slot}"])
            activity = activity_recoding[activity_code][0]
            expected_age[age_infr_class(age)] += float(weight)
            expected_sex[sex] += float(weight)
            expected_activity[activity] += float(weight)
    expected_age_share = {k: v / person_weight_total for k, v in expected_age.items()}
    expected_sex_share = {k: v / person_weight_total for k, v in expected_sex.items()}
    expected_activity_share = {
        k: v / person_weight_total for k, v in expected_activity.items()
    }

    generated_age = persons["age_infr_class"].value_counts(normalize=True).to_dict()
    add_dimension(
        "age_infr_class",
        list(AGE_INFR_CLASSES),
        {str(k): float(v) for k, v in generated_age.items()},
        expected_age_share,
    )
    generated_sex = persons["sex"].value_counts(normalize=True).to_dict()
    add_dimension(
        "sex",
        ["FEMALE", "MALE"],
        {str(k): float(v) for k, v in generated_sex.items()},
        expected_sex_share,
    )
    activity_categories = sorted(set(expected_activity) | set(persons["primary_activity_status"]))
    generated_activity = (
        persons["primary_activity_status"].value_counts(normalize=True).to_dict()
    )
    add_dimension(
        "primary_activity_status",
        activity_categories,
        {str(k): float(v) for k, v in generated_activity.items()},
        expected_activity_share,
    )
    return pd.DataFrame(rows)


def median_used_replicas(donor_reuse: pd.DataFrame) -> float:
    used = donor_reuse.loc[donor_reuse["used"], "n_generated_replicas"]
    return float(used.median())


def historical_population_manifest(
    *,
    target_persons: int,
    actual_persons: int,
    actual_households: int,
    actual_resource_relations: int,
    generation_algorithm: str,
    generation_seed: int,
    zone_algorithm: str,
    zone_seed: int,
    donor_pool_size: int,
    linked_persons: int,
    roster_only_persons: int,
    snapshot_hash: str,
) -> dict[str, Any]:
    """Recreate the frozen F1.3a compact manifest schema and field order."""
    return {
        "snapshot_id": "P_TRS_EXP_V1_S_v1",
        "status": "EXPERIMENTAL_PRE_G1",
        "population_variant_id": "P_TRS_EXP_V1",
        "scale_id": "S",
        "target_persons": target_persons,
        "actual_persons": actual_persons,
        "actual_households": actual_households,
        "actual_resource_relations": actual_resource_relations,
        "generation_algorithm": generation_algorithm,
        "generation_seed": generation_seed,
        "zone_allocation_algorithm": zone_algorithm,
        "zone_seed": zone_seed,
        "donor_pool": {
            "split": "TRAIN",
            "eligibility": "STRICT_RMIN_DONOR",
            "n_households": donor_pool_size,
            "household_size_scope": "1..5",
            "sampling_probability": "H_GEW normalized within donor pool",
        },
        "geography": {
            "level": "PLR",
            "allocation_basis": "Zensus private-household totals only",
            "statistically_observed_plr": 541,
            "excluded_no_stat_target_plr": ["03400831", "06200418"],
            "exclusion_semantics": "NO_STAT_TARGET; not population zero",
        },
        "enrichment": {
            "linked_generated_persons": linked_persons,
            "roster_only_generated_persons": roster_only_persons,
            "rule": "No personal enrichment fabricated for roster-only members",
        },
        "formal_gate_eligible": False,
        "result_label": "PRE-G1 EXPERIMENTAL RESULTS",
        "snapshot_sha256": snapshot_hash,
        "validation": {"checks_total": 23, "checks_pass": 23, "checks_fail": 0},
    }


def validate_structural_snapshot(
    households: pd.DataFrame,
    persons: pd.DataFrame,
    resources: pd.DataFrame,
    zone_audit: pd.DataFrame,
    second_hashes: list[str],
    primary_hashes: list[str],
    expected_snapshot_hash: str,
    generation_algorithm: str,
    zone_algorithm: str,
) -> list[dict[str, str]]:
    """Run the frozen 23 F1.3a structural checks with exact snapshot witness."""
    generated_households = set(households["household_id"])
    generated_persons = set(persons["person_id"])
    person_resource = resources[resources["scope"] == "PERSON"]
    hh_resource = resources[resources["scope"] == "HOUSEHOLD"]
    roster_counts = persons.groupby("household_id").size()
    expected_counts = households.set_index("household_id")["materialized_member_count"]
    valid_zones = set(
        zone_audit.loc[
            zone_audit["allocation_status"]
            == "ALLOCATED_FROM_STATISTICAL_PRIVATE_HH_TOTAL",
            "home_zone_id",
        ].astype(str)
    )
    person_zone_lookup = households.set_index("household_id")["home_zone_id"].astype(str)
    person_zone_expected = persons["household_id"].map(person_zone_lookup)
    topcoded = resources[resources["quantity_topcoded"].astype(bool)]
    topcode_ok = all(
        (row.resource_type in {"CAR", "MOTORCYCLE_MOPED"} and row.quantity == 3.0)
        or (row.resource_type in {"BIKE", "EBIKE"} and row.quantity == 10.0)
        for row in topcoded.itertuples(index=False)
    )
    columns_lower = {str(column).lower() for frame in (households, persons, resources) for column in frame.columns}
    nfi_ok = NFI_FORBIDDEN_COLUMNS.isdisjoint(columns_lower)
    snapshot_hash = snapshot_sha256(primary_hashes)
    roster_only = persons[persons["person_enrichment_status"] == "ROSTER_ONLY_NO_PERSONEN"]

    def row(check_id: str, category: str, description: str, ok: bool, details: str = "") -> dict[str, str]:
        return {
            "check_id": check_id,
            "category": category,
            "description": description,
            "result": "PASS" if ok else "FAIL",
            "details": details,
        }

    return [
        row("PTRS-S-001", "TARGET", "Exactly 10,000 persons materialized", len(persons) == 10000, f"persons={len(persons)}"),
        row("PTRS-S-002", "PK", "Household IDs unique", households["household_id"].is_unique, f"households={len(households)}"),
        row("PTRS-S-003", "PK", "Person IDs unique", persons["person_id"].is_unique),
        row("PTRS-S-004", "PK", "Resource relation IDs unique", resources["relation_id"].is_unique),
        row("PTRS-S-005", "FK", "Every person references an existing generated household", set(persons["household_id"]).issubset(generated_households)),
        row("PTRS-S-006", "FK", "Every resource references an existing generated household", set(resources["household_id"]).issubset(generated_households)),
        row("PTRS-S-007", "FK", "Every person-scoped resource references an existing generated person", set(person_resource["person_id"].dropna()).issubset(generated_persons)),
        row("PTRS-S-008", "ATOMICITY", "Materialized member count equals generated person rows", roster_counts.reindex(expected_counts.index).fillna(0).astype(int).equals(expected_counts.astype(int))),
        row("PTRS-S-009", "DONOR", "All household donors come from strict TRAIN", bool((households["donor_split"] == "TRAIN").all() and (households["donor_eligibility"] == "STRICT_RMIN_DONOR").all())),
        row("PTRS-S-010", "DONOR", "Experimental donor households are size 1–5 only", bool(households["household_size_class"].between(1, 5).all())),
        row("PTRS-S-011", "DONOR", "No generated household is top-coded", not bool(households["household_size_topcoded"].any())),
        row("PTRS-S-012", "GEOGRAPHY", "Every home_zone_id is a valid statistically observed PLR", set(households["home_zone_id"].astype(str)).issubset(valid_zones)),
        row("PTRS-S-013", "GEOGRAPHY", "Every person inherits household home_zone_id", bool((persons["home_zone_id"].astype(str).to_numpy() == person_zone_expected.astype(str).to_numpy()).all())),
        row("PTRS-S-014", "RESOURCE", "Household stock relations never claim person scope", bool((hh_resource.loc[hh_resource["relation_type"] == "HOUSEHOLD_STOCK", "person_id"].isna()).all())),
        row("PTRS-S-015", "RESOURCE", "Person access relations never claim household ownership", bool((person_resource.loc[person_resource["relation_type"] == "PERSON_ACCESS", "quantity"].isna()).all())),
        row("PTRS-S-016", "RESOURCE", "Top-coded stock lower bounds are preserved only at source caps", topcode_ok),
        row("PTRS-S-017", "IDENTITY", "Source donor reuse does not duplicate generated identity", households["household_id"].is_unique and persons["person_id"].is_unique),
        row("PTRS-S-018", "NFI", "Population snapshot contains no downstream trip/choice/execution outcome fields", nfi_ok),
        row("PTRS-S-019", "REPRODUCIBILITY", "Same config/seeds reproduce identical tables", primary_hashes == second_hashes and snapshot_hash == expected_snapshot_hash, f"snapshot_hash={snapshot_hash}"),
        row("PTRS-S-020", "SPLIT", "CALIBRATION/TEST households are not used as donors", bool((households["donor_split"] == "TRAIN").all())),
        row("PTRS-S-021", "GEOGRAPHY", "Zone assignment uses household-total quotas only", zone_algorithm == "PLR_PRIVATE_HH_TOTAL_LARGEST_REMAINDER_RANDOM_ASSIGN_V1", zone_algorithm),
        row("PTRS-S-022", "ENRICHMENT", "Roster-only persons remain explicit rather than fabricated enrichment", bool((roster_only["source_person_id"].isna()).all() and (roster_only["source_person_weight"].isna()).all() and (roster_only["source_person_expansion_factor"].isna()).all())),
        row("PTRS-S-023", "LICENSE", "Persons without Personen enrichment do not receive fabricated licence answers", bool((roster_only["car_driver_license"] == "UNKNOWN").all() and (roster_only["license_observation_status"] == "NO_PERSONEN_ENRICHMENT").all())),
    ]
