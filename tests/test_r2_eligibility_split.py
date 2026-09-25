from simfleet_edg.common.population_split import (
    age_infr_class,
    largest_remainder_counts,
    normalize_source_id,
    split_hash,
)


def test_split_hash_matches_frozen_example() -> None:
    assert split_hash(20260912, "1861280") == (
        "f2f612b05b004f921cfc5f4d97fe450dd19dcec8458e6443ca1da8fc09174135"
    )


def test_largest_remainder_matches_frozen_strata() -> None:
    fractions = {"TRAIN": 0.70, "CALIBRATION": 0.15, "TEST": 0.15}
    assert largest_remainder_counts(584, fractions) == {
        "TRAIN": 409,
        "CALIBRATION": 88,
        "TEST": 87,
    }
    assert largest_remainder_counts(749, fractions) == {
        "TRAIN": 524,
        "CALIBRATION": 113,
        "TEST": 112,
    }


def test_source_id_normalization_handles_scientific_notation() -> None:
    assert normalize_source_id("1.861280E+6") == "1861280"
    assert normalize_source_id("0") == "0"


def test_age_infr_boundaries() -> None:
    assert age_infr_class(2) == "LT3"
    assert age_infr_class(3) == "3_5"
    assert age_infr_class(18) == "16_18"
    assert age_infr_class(19) == "19_24"
    assert age_infr_class(74) == "67_74"
    assert age_infr_class(75) == "75_PLUS"
    assert age_infr_class(85) == "75_PLUS"
