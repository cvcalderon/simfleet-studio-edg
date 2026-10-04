"""Normalization of frozen Zensus 2022 flat exports for F1 P_CONSTR."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd

from simfleet_edg.population.age_projection import AGE_ZENSUS_11_SOURCE_CODES

BERLIN_BEZIRK_CODES: Final[tuple[str, ...]] = tuple(f"110000000000{i:02d}" for i in range(1, 13))
SEX_CODES: Final[tuple[str, ...]] = ("GESM", "GESW")
HH_SIZE_CODES: Final[tuple[str, ...]] = (
    "PERSON01",
    "PERSON02",
    "PERSON03",
    "PERSON04",
    "PERSON05",
    "PERSON06UM",
)

TABLE_DIMENSIONS: Final[dict[str, tuple[str, ...]]] = {
    "1000A-1029": ("GEOBZ1", "HSHGR2"),
    "1000A-2070": ("GEOBZ1", "ALTGR2", "HSHGR2"),
    "1000A-2071": ("GEOBZ1", "GESCH1", "HSHGR2"),
    "1000A-3082": ("GEOBZ1", "ALTKL2", "GESCH1", "HSHGR2"),
    "5000H-1001": ("GEOBZ1", "HSHGR2"),
}


@dataclass(frozen=True)
class NormalizedSource:
    """Normalized count rows plus immutable source identity."""

    table_id: str
    source_path: Path
    source_sha256: str
    frame: pd.DataFrame


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_single_csv_flat_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"Corrupt ZIP member: {bad}")
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"Expected exactly one CSV in {path.name}, found {len(members)}")
        raw = archive.read(members[0])
    return pd.read_csv(
        io.BytesIO(raw),
        sep=";",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )


def _parse_published_value(raw: str) -> tuple[int | None, str]:
    text = str(raw).strip()
    if text == "-":
        return 0, "PUBLISHED_ZERO"
    if text == ".":
        return None, "UNPUBLISHED_UNKNOWN_OR_CONFIDENTIAL"
    if text == "/":
        return None, "UNPUBLISHED_QUALITY_UNCERTAIN"
    if text == "":
        return None, "MISSING_EMPTY"
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError(f"Expected integer count or frozen special symbol, got {text!r}") from exc
    return value, "PUBLISHED_COUNT"


def normalize_flat_count_zip(
    path: Path,
    *,
    table_id: str,
    expected_sha256: str | None = None,
) -> NormalizedSource:
    """Normalize a frozen flat export to canonical count rows for the 12 Berlin Bezirke."""
    if table_id not in TABLE_DIMENSIONS:
        raise ValueError(f"Unsupported table_id: {table_id}")
    actual_hash = sha256_file(path)
    if expected_sha256 is not None and actual_hash != expected_sha256:
        raise ValueError(
            f"SHA256 mismatch for {path.name}: expected={expected_sha256} actual={actual_hash}"
        )

    raw = _read_single_csv_flat_zip(path)
    required_common = {
        "statistics_code",
        "time",
        "value",
        "value_unit",
        "value_variable_code",
        "value_variable_label",
        "value_q",
    }
    missing = required_common.difference(raw.columns)
    if missing:
        raise ValueError(f"{table_id} missing required columns: {sorted(missing)}")

    dim_positions: dict[str, int] = {}
    for index in range(1, 6):
        col = f"{index}_variable_code"
        if col not in raw.columns:
            continue
        values = {value for value in raw[col].unique() if value}
        for dim in TABLE_DIMENSIONS[table_id]:
            if dim in values:
                dim_positions[dim] = index
    if set(dim_positions) != set(TABLE_DIMENSIONS[table_id]):
        raise ValueError(
            f"{table_id} dimension mismatch: expected={TABLE_DIMENSIONS[table_id]} "
            f"observed={sorted(dim_positions)}"
        )

    counts = raw[raw["value_unit"] == "Anzahl"].copy()
    rows: list[dict[str, object]] = []
    for source_row, row in counts.iterrows():
        out: dict[str, object] = {
            "table_id": table_id,
            "source_row": int(source_row),
            "reference_date": row["time"],
            "published_raw": row["value"],
            "value_q": row["value_q"],
            "value_variable_code": row["value_variable_code"],
            "value_variable_label": row["value_variable_label"],
            "source_sha256": actual_hash,
        }
        published, status = _parse_published_value(row["value"])
        out["published_value"] = published
        out["published_status"] = status
        for dim, index in dim_positions.items():
            out[f"{dim}_code"] = row[f"{index}_variable_attribute_code"]
            out[f"{dim}_label"] = row[f"{index}_variable_attribute_label"]
        rows.append(out)

    frame = pd.DataFrame(rows)
    frame = frame[frame["GEOBZ1_code"].isin(BERLIN_BEZIRK_CODES)].copy()
    observed_bezirke = tuple(sorted(frame["GEOBZ1_code"].unique()))
    if observed_bezirke != BERLIN_BEZIRK_CODES:
        raise ValueError(
            f"{table_id} Berlin coverage mismatch: expected 12 Bezirke, got {observed_bezirke}"
        )
    if set(frame["reference_date"].unique()) != {"2022-05-15"}:
        raise ValueError(f"{table_id} has unexpected reference date")
    if frame["published_status"].isin(
        {"UNPUBLISHED_UNKNOWN_OR_CONFIDENTIAL", "UNPUBLISHED_QUALITY_UNCERTAIN", "MISSING_EMPTY"}
    ).any():
        bad_rows = frame[
            frame["published_status"].isin(
                {
                    "UNPUBLISHED_UNKNOWN_OR_CONFIDENTIAL",
                    "UNPUBLISHED_QUALITY_UNCERTAIN",
                    "MISSING_EMPTY",
                }
            )
        ]
        raise ValueError(
            f"{table_id} contains unsupported non-published count rows: {len(bad_rows)}"
        )
    frame["published_value"] = frame["published_value"].astype(int)
    return NormalizedSource(table_id, path, actual_hash, frame.reset_index(drop=True))


def validate_fit_source_categories(sources: dict[str, NormalizedSource]) -> None:
    """Validate frozen category support for the three person-domain fit sources."""
    detail = sources["1000A-3082"].frame
    ages = tuple(
        code
        for code in AGE_ZENSUS_11_SOURCE_CODES
        if code in set(detail["ALTKL2_code"].unique())
    )
    if ages != AGE_ZENSUS_11_SOURCE_CODES:
        raise ValueError(f"1000A-3082 ALTKL2 order/support mismatch: {ages}")
    if not set(SEX_CODES).issubset(set(detail["GESCH1_code"].unique())):
        raise ValueError("1000A-3082 missing frozen sex categories")
    if not set(HH_SIZE_CODES).issubset(set(detail["HSHGR2_code"].unique())):
        raise ValueError("1000A-3082 missing frozen household-size categories")


def concatenate_normalized_sources(sources: dict[str, NormalizedSource]) -> pd.DataFrame:
    """Return all normalized rows with a stable superset schema for RunBundle evidence."""
    frames = [sources[key].frame for key in sorted(sources)]
    return pd.concat(frames, ignore_index=True, sort=False)
