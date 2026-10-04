"""Fit-only age projection for the frozen Zensus ALTKL2 control taxonomy."""

from __future__ import annotations

AGE_ZENSUS_11_LABELS = (
    "01_LT3",
    "02_3_5",
    "03_6_14",
    "04_15_17",
    "05_18_24",
    "06_25_29",
    "07_30_39",
    "08_40_49",
    "09_50_64",
    "10_65_74",
    "11_75_PLUS",
)

AGE_ZENSUS_11_SOURCE_CODES = (
    "ALT000B002",
    "ALT003B005",
    "ALT006B014",
    "ALT015B017",
    "ALT018B024",
    "ALT025B029",
    "ALT030B039",
    "ALT040B049",
    "ALT050B064",
    "ALT065B074",
    "ALT075BXXX",
)

_LABEL_TO_SOURCE = dict(zip(AGE_ZENSUS_11_LABELS, AGE_ZENSUS_11_SOURCE_CODES, strict=True))
_SOURCE_TO_LABEL = {value: key for key, value in _LABEL_TO_SOURCE.items()}


def age_zensus_11_v1(age_years: int) -> str:
    """Project exact age to the frozen Zensus 11-class fit taxonomy.

    This is deliberately derived from ``age_years``. ``age_infr_class`` must not be
    used as a shortcut because ALTER_INFR and ALTKL2 have different cut points.
    """
    if isinstance(age_years, bool) or not isinstance(age_years, int):
        raise TypeError("age_years must be an integer")
    if age_years < 0:
        raise ValueError("age_years must be non-negative")
    if age_years < 3:
        return "01_LT3"
    if age_years <= 5:
        return "02_3_5"
    if age_years <= 14:
        return "03_6_14"
    if age_years <= 17:
        return "04_15_17"
    if age_years <= 24:
        return "05_18_24"
    if age_years <= 29:
        return "06_25_29"
    if age_years <= 39:
        return "07_30_39"
    if age_years <= 49:
        return "08_40_49"
    if age_years <= 64:
        return "09_50_64"
    if age_years <= 74:
        return "10_65_74"
    return "11_75_PLUS"


def age_zensus_source_code(age_years: int) -> str:
    """Return the official ALTKL2 source code for an exact age."""
    return _LABEL_TO_SOURCE[age_zensus_11_v1(age_years)]


def age_zensus_label_from_source(code: str) -> str:
    """Map an official ALTKL2 source code to the internal fit-only label."""
    try:
        return _SOURCE_TO_LABEL[code]
    except KeyError as exc:
        raise ValueError(f"Unsupported ALTKL2 source code: {code}") from exc
