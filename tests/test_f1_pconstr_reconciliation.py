from __future__ import annotations

from pathlib import Path

import pandas as pd

import simfleet_edg.population.reconciliation as reconciliation_module
from simfleet_edg.population.age_projection import AGE_ZENSUS_11_SOURCE_CODES
from simfleet_edg.population.reconciliation import reconcile_bezirk
from simfleet_edg.population.zensus_controls import HH_SIZE_CODES, SEX_CODES, NormalizedSource


def _source(table_id: str, rows: list[dict[str, object]]) -> NormalizedSource:
    return NormalizedSource(table_id, Path(f"/{table_id}.zip"), "0" * 64, pd.DataFrame(rows))


def test_reconciler_enforces_total_zeros_and_divisibility_deterministically() -> None:
    b = "11000000000001"
    detail_rows = []
    for age in AGE_ZENSUS_11_SOURCE_CODES:
        for sex in SEX_CODES:
            for hh in HH_SIZE_CODES:
                value = 0
                if age == AGE_ZENSUS_11_SOURCE_CODES[0] and sex == "GESM" and hh == "PERSON01":
                    value = 7
                if age == AGE_ZENSUS_11_SOURCE_CODES[1] and sex == "GESW" and hh == "PERSON02":
                    value = 4
                detail_rows.append({
                    "GEOBZ1_code": b, "GEOBZ1_label": "Mitte", "ALTKL2_code": age,
                    "GESCH1_code": sex, "HSHGR2_code": hh, "published_value": value,
                    "published_raw": str(value), "value_q": "e",
                })
    hh_rows = [
        {"GEOBZ1_code": b, "GEOBZ1_label": "Mitte", "HSHGR2_code": "", "published_value": 11},
    ]
    for hh, value in zip(HH_SIZE_CODES, [7, 4, 0, 0, 0, 0], strict=True):
        hh_rows.append({"GEOBZ1_code": b, "GEOBZ1_label": "Mitte", "HSHGR2_code": hh, "published_value": value})
    sex_rows = []
    for sex in SEX_CODES:
        for hh in HH_SIZE_CODES:
            value = 7 if (sex, hh) == ("GESM", "PERSON01") else 4 if (sex, hh) == ("GESW", "PERSON02") else 0
            sex_rows.append({
                "GEOBZ1_code": b, "GEOBZ1_label": "Mitte", "GESCH1_code": sex,
                "HSHGR2_code": hh, "published_value": value,
            })

    result1 = reconcile_bezirk(_source("1000A-3082", detail_rows), _source("1000A-1029", hh_rows), _source("1000A-2071", sex_rows), b)
    result2 = reconcile_bezirk(_source("1000A-3082", detail_rows), _source("1000A-1029", hh_rows), _source("1000A-2071", sex_rows), b)
    assert result1.audit.stage1_detail_l1_optimum == 0
    assert result1.audit.stage2_hhsize_margin_l1_optimum_given_stage1 == 0
    assert result1.audit.stage3_sex_hhsize_margin_l1_optimum_given_stage1_2 == 0
    assert int(result1.cube["fit_target_value"].sum()) == 11
    assert result1.cube["fit_target_value"].tolist() == result2.cube["fit_target_value"].tolist()
    for hh, size in zip(HH_SIZE_CODES[:5], range(1, 6), strict=True):
        margin = int(result1.cube.loc[result1.cube["household_size_code"] == hh, "fit_target_value"].sum())
        assert margin % size == 0
    zeros = result1.cube["published_value"] == 0
    assert bool((result1.cube.loc[zeros, "fit_target_value"] == 0).all())


def test_reconciler_uses_four_milp_solves_for_one_bezirk(monkeypatch) -> None:
    b = "11000000000001"
    detail_rows = []
    for age in AGE_ZENSUS_11_SOURCE_CODES:
        for sex in SEX_CODES:
            for hh in HH_SIZE_CODES:
                value = 0
                if (age, sex, hh) == (AGE_ZENSUS_11_SOURCE_CODES[0], "GESM", "PERSON01"):
                    value = 7
                if (age, sex, hh) == (AGE_ZENSUS_11_SOURCE_CODES[1], "GESW", "PERSON02"):
                    value = 4
                detail_rows.append(
                    {
                        "GEOBZ1_code": b,
                        "GEOBZ1_label": "Mitte",
                        "ALTKL2_code": age,
                        "GESCH1_code": sex,
                        "HSHGR2_code": hh,
                        "published_value": value,
                        "published_raw": str(value),
                        "value_q": "e",
                    }
                )
    hh_rows = [
        {
            "GEOBZ1_code": b,
            "GEOBZ1_label": "Mitte",
            "HSHGR2_code": "",
            "published_value": 11,
        },
    ]
    for hh, value in zip(HH_SIZE_CODES, [7, 4, 0, 0, 0, 0], strict=True):
        hh_rows.append(
            {
                "GEOBZ1_code": b,
                "GEOBZ1_label": "Mitte",
                "HSHGR2_code": hh,
                "published_value": value,
            }
        )
    sex_rows = []
    for sex in SEX_CODES:
        for hh in HH_SIZE_CODES:
            value = (
                7
                if (sex, hh) == ("GESM", "PERSON01")
                else 4
                if (sex, hh) == ("GESW", "PERSON02")
                else 0
            )
            sex_rows.append(
                {
                    "GEOBZ1_code": b,
                    "GEOBZ1_label": "Mitte",
                    "GESCH1_code": sex,
                    "HSHGR2_code": hh,
                    "published_value": value,
                }
            )

    original_milp = reconciliation_module.milp
    calls = 0

    def counting_milp(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_milp(*args, **kwargs)

    monkeypatch.setattr(reconciliation_module, "milp", counting_milp)
    reconcile_bezirk(
        _source("1000A-3082", detail_rows),
        _source("1000A-1029", hh_rows),
        _source("1000A-2071", sex_rows),
        b,
    )
    assert calls == 4
