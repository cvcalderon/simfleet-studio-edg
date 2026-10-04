import pytest

from simfleet_edg.population.age_projection import age_zensus_11_v1, age_zensus_source_code


@pytest.mark.parametrize(
    ("age", "label", "source"),
    [
        (0, "01_LT3", "ALT000B002"),
        (2, "01_LT3", "ALT000B002"),
        (3, "02_3_5", "ALT003B005"),
        (5, "02_3_5", "ALT003B005"),
        (6, "03_6_14", "ALT006B014"),
        (14, "03_6_14", "ALT006B014"),
        (15, "04_15_17", "ALT015B017"),
        (17, "04_15_17", "ALT015B017"),
        (18, "05_18_24", "ALT018B024"),
        (24, "05_18_24", "ALT018B024"),
        (25, "06_25_29", "ALT025B029"),
        (29, "06_25_29", "ALT025B029"),
        (30, "07_30_39", "ALT030B039"),
        (39, "07_30_39", "ALT030B039"),
        (40, "08_40_49", "ALT040B049"),
        (49, "08_40_49", "ALT040B049"),
        (50, "09_50_64", "ALT050B064"),
        (64, "09_50_64", "ALT050B064"),
        (65, "10_65_74", "ALT065B074"),
        (74, "10_65_74", "ALT065B074"),
        (75, "11_75_PLUS", "ALT075BXXX"),
        (101, "11_75_PLUS", "ALT075BXXX"),
    ],
)
def test_age_zensus_projection_boundaries(age: int, label: str, source: str) -> None:
    assert age_zensus_11_v1(age) == label
    assert age_zensus_source_code(age) == source


def test_age_projection_rejects_negative_and_non_integer() -> None:
    with pytest.raises(ValueError):
        age_zensus_11_v1(-1)
    with pytest.raises(TypeError):
        age_zensus_11_v1(18.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        age_zensus_11_v1(True)  # type: ignore[arg-type]
