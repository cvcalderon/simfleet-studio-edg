"""Deterministic PRE-F3 R2 household eligibility and split utilities."""

from __future__ import annotations

import csv
import hashlib
import math
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SPLIT_ORDER = ("TRAIN", "CALIBRATION", "TEST")
AGE_INFR_LABELS = (
    "LT3",
    "3_5",
    "6_9",
    "10_15",
    "16_18",
    "19_24",
    "25_39",
    "40_59",
    "60_66",
    "67_74",
    "75_PLUS",
)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_csv_format(path: Path) -> tuple[str, str]:
    with path.open("rb") as handle:
        raw = handle.readline()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            delimiter = ";" if text.count(";") > text.count(",") else ","
            return encoding, delimiter
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to decode CSV header: {path}")


def normalize_source_id(value: str) -> str:
    text = str(value).strip().strip('"')
    if not text:
        return ""
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    integral = number.to_integral_value()
    if number == integral:
        return str(int(integral))
    return format(number.normalize(), "f")


def parse_int(value: str) -> int:
    return int(Decimal(str(value).strip()))


def parse_float(value: str) -> float:
    return float(str(value).strip())


def age_infr_class(age: int) -> str:
    if age < 3:
        return "LT3"
    if age <= 5:
        return "3_5"
    if age <= 9:
        return "6_9"
    if age <= 15:
        return "10_15"
    if age <= 18:
        return "16_18"
    if age <= 24:
        return "19_24"
    if age <= 39:
        return "25_39"
    if age <= 59:
        return "40_59"
    if age <= 66:
        return "60_66"
    if age <= 74:
        return "67_74"
    if age <= 85:
        return "75_PLUS"
    raise ValueError(f"Age outside R_min range: {age}")


def split_hash(seed: int, household_id: str) -> str:
    payload = f"{seed}|{normalize_source_id(household_id)}".encode()
    return hashlib.sha256(payload).hexdigest()


def largest_remainder_counts(
    n: int,
    fractions: dict[str, float],
    tie_break: Iterable[str] = SPLIT_ORDER,
) -> dict[str, int]:
    names = list(tie_break)
    raw = {name: n * float(fractions[name]) for name in names}
    base = {name: math.floor(raw[name]) for name in names}
    remainder = n - sum(base.values())
    priority = {name: i for i, name in enumerate(names)}
    ranked = sorted(
        names,
        key=lambda name: (-(raw[name] - base[name]), priority[name]),
    )
    for name in ranked[:remainder]:
        base[name] += 1
    return base


def _missing_value(field: str, value: str) -> str:
    try:
        return f"{field}={float(value)}"
    except ValueError:
        return f"{field}={value}"


def build_berlin_household_eligibility(
    path: Path,
    berlin_code: int = 11,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    encoding, delimiter = detect_csv_format(path)
    rows: list[dict[str, Any]] = []
    source_records: dict[str, dict[str, str]] = {}
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        required = {
            "H_ID",
            "H_GEW",
            "H_ART",
            "H_GR",
            "BLAND",
            *(f"HP_SEX_{i}" for i in range(1, 7)),
            *(f"HP_ALTER_{i}" for i in range(1, 7)),
        }
        missing_columns = required.difference(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"Household CSV missing columns: {sorted(missing_columns)}")

        for raw in reader:
            if parse_int(raw["BLAND"]) != berlin_code:
                continue
            household_id = normalize_source_id(raw["H_ID"])
            h_art = parse_int(raw["H_ART"])
            h_gr = parse_int(raw["H_GR"])
            is_private = h_art in {1, 2}
            household_size_class = "6_PLUS" if h_gr == 6 else str(h_gr)
            missing_detail: list[str] = []
            roster_complete = True
            for slot in range(1, min(h_gr, 6) + 1):
                sex_field = f"HP_SEX_{slot}"
                age_field = f"HP_ALTER_{slot}"
                sex = parse_float(raw[sex_field])
                age = parse_float(raw[age_field])
                if sex not in {1.0, 2.0}:
                    roster_complete = False
                    missing_detail.append(_missing_value(sex_field, raw[sex_field]))
                if not 0.0 <= age <= 85.0:
                    roster_complete = False
                    missing_detail.append(_missing_value(age_field, raw[age_field]))

            if not is_private:
                class_name = "HH_NON_PRIVATE"
                source_role = "DIAGNOSTIC"
                eligibility_status = "INELIGIBLE"
                hh_size_fit = False
                person_margins_fit = False
                joint_rmin = False
                reason_code = "NON_PRIVATE_HOUSEHOLD_SCOPE_MISMATCH"
                roster_complete_out = False
            elif h_gr == 6:
                class_name = "HH_PRIVATE_6_PLUS"
                source_role = "DONOR"
                eligibility_status = "PARTIAL"
                hh_size_fit = True
                person_margins_fit = False
                joint_rmin = False
                reason_code = "SIX_PLUS_COMPOSITION_TOPCODED"
                roster_complete_out = roster_complete
            elif h_gr in {1, 2, 3, 4, 5} and roster_complete:
                class_name = "HH_PRIVATE_1_5_COMPLETE"
                source_role = "DONOR"
                eligibility_status = "ELIGIBLE"
                hh_size_fit = True
                person_margins_fit = True
                joint_rmin = True
                reason_code = "STRICT_RMIN_DONOR"
                roster_complete_out = True
            elif h_gr in {1, 2, 3, 4, 5}:
                class_name = "HH_PRIVATE_1_5_RMIN_MISSING"
                source_role = "DONOR"
                eligibility_status = "PARTIAL"
                hh_size_fit = True
                person_margins_fit = False
                joint_rmin = False
                reason_code = "RMIN_ROSTER_ATTRIBUTE_MISSING"
                roster_complete_out = False
            else:
                raise ValueError(f"Unexpected H_GR={h_gr} for household {household_id}")

            row = {
                "source_household_id": int(household_id),
                "H_ART": h_art,
                "H_GR": h_gr,
                "household_size_class": household_size_class,
                "is_private_household": is_private,
                "class": class_name,
                "source_role": source_role,
                "eligibility_status": eligibility_status,
                "eligibility_context": "RMIN_FIT",
                "hh_size_fit_eligible": hh_size_fit,
                "person_margins_fit_eligible": person_margins_fit,
                "joint_rmin_donor_eligible": joint_rmin,
                "reason_code": reason_code,
                "missing_detail": "|".join(missing_detail),
                "roster_member_slots_observed": h_gr,
                "roster_rmin_complete": roster_complete_out,
                "provenance": "MiD2017_B1_v1.1:Haushalte",
            }
            rows.append(row)
            source_records[household_id] = raw
    return rows, source_records


def split_stratum(row: dict[str, Any]) -> str:
    class_name = row["class"]
    if class_name == "HH_PRIVATE_1_5_COMPLETE":
        return f"STRICT_RMIN_DONOR|HH_SIZE_{row['household_size_class']}"
    if class_name == "HH_PRIVATE_6_PLUS":
        return "PARTIAL_6_PLUS"
    if class_name == "HH_PRIVATE_1_5_RMIN_MISSING":
        return "PARTIAL_RMIN_MISSING"
    if class_name == "HH_NON_PRIVATE":
        return "NON_PRIVATE"
    raise ValueError(f"Unknown eligibility class: {class_name}")


def build_split_manifest(
    eligibility_rows: list[dict[str, Any]],
    seed: int,
    fractions: dict[str, float],
    manifest_version: str,
    tie_break: Iterable[str] = SPLIT_ORDER,
) -> list[dict[str, Any]]:
    staged: list[dict[str, Any]] = []
    for source in eligibility_rows:
        row = dict(source)
        row["split_stratum"] = split_stratum(source)
        row["split_hash"] = split_hash(seed, str(source["source_household_id"]))
        staged.append(row)

    by_stratum: dict[str, list[int]] = {}
    for index, row in enumerate(staged):
        by_stratum.setdefault(row["split_stratum"], []).append(index)

    assignments: dict[int, str] = {}
    split_names = list(tie_break)
    for indices in by_stratum.values():
        ordered = sorted(
            indices,
            key=lambda i: (staged[i]["split_hash"], staged[i]["source_household_id"]),
        )
        counts = largest_remainder_counts(len(ordered), fractions, split_names)
        cursor = 0
        for split_name in split_names:
            end = cursor + counts[split_name]
            for index in ordered[cursor:end]:
                assignments[index] = split_name
            cursor = end

    policy = {
        "PARTIAL_6_PLUS": "PARTIAL_6_PLUS_RESEARCH_ONLY",
        "PARTIAL_RMIN_MISSING": "PARTIAL_RMIN_MISSING_RESEARCH_ONLY",
        "NON_PRIVATE": "DIAGNOSTIC_NON_PRIVATE",
    }
    output: list[dict[str, Any]] = []
    for index, source in enumerate(staged):
        stratum = source["split_stratum"]
        output.append(
            {
                "split_manifest_version": manifest_version,
                "source_household_id": source["source_household_id"],
                "split": assignments[index],
                "split_unit": "HOUSEHOLD",
                "split_stratum": stratum,
                "split_hash": source["split_hash"],
                "split_seed": seed,
                "class": source["class"],
                "household_size_class": source["household_size_class"],
                "H_ART": source["H_ART"],
                "H_GR": source["H_GR"],
                "is_private_household": source["is_private_household"],
                "eligibility_status": source["eligibility_status"],
                "joint_rmin_donor_eligible": source["joint_rmin_donor_eligible"],
                "hh_size_fit_eligible": source["hh_size_fit_eligible"],
                "person_margins_fit_eligible": source["person_margins_fit_eligible"],
                "roster_rmin_complete": source["roster_rmin_complete"],
                "fit_use_policy": policy.get(stratum, "STRICT_RMIN_DONOR"),
                "descendant_policy": "INHERIT_HOUSEHOLD_SPLIT",
                "provenance": "MiD2017_B1_v1.1:Haushalte",
            }
        )
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def descendant_split_counts(
    path: Path,
    split_lookup: dict[str, str],
    berlin_code: int = 11,
) -> Counter[str]:
    encoding, delimiter = detect_csv_format(path)
    counts: Counter[str] = Counter()
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader)
        try:
            h_index = header.index("H_ID")
            bland_index = header.index("BLAND")
        except ValueError as exc:
            raise ValueError(f"Descendant CSV missing H_ID/BLAND: {path}") from exc
        for row in reader:
            if parse_int(row[bland_index]) != berlin_code:
                continue
            household_id = normalize_source_id(row[h_index])
            if household_id == "0":
                counts["UNLINKED_EXCLUDED"] += 1
                continue
            split_name = split_lookup.get(household_id)
            if split_name is None:
                counts["HOUSEHOLD_NOT_FOUND"] += 1
            else:
                counts[split_name] += 1
    return counts


def strict_support_counts(
    eligibility_rows: list[dict[str, Any]],
    source_records: dict[str, dict[str, str]],
    split_lookup: dict[str, str],
) -> Counter[tuple[str, str, int]]:
    counts: Counter[tuple[str, str, int]] = Counter()
    for eligibility in eligibility_rows:
        if not eligibility["joint_rmin_donor_eligible"]:
            continue
        household_id = str(eligibility["source_household_id"])
        raw = source_records[household_id]
        split_name = split_lookup[household_id]
        for slot in range(1, int(eligibility["H_GR"]) + 1):
            sex = int(parse_float(raw[f"HP_SEX_{slot}"]))
            age = int(parse_float(raw[f"HP_ALTER_{slot}"]))
            counts[(split_name, age_infr_class(age), sex)] += 1
    return counts
