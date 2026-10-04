from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

from simfleet_edg.population.zensus_controls import normalize_flat_count_zip


def _write_zip(path: Path, rows: list[list[str]]) -> None:
    header = [
        "statistics_code", "statistics_label", "time_code", "time_label", "time",
        "1_variable_code", "1_variable_label", "1_variable_attribute_code", "1_variable_attribute_label",
        "2_variable_code", "2_variable_label", "2_variable_attribute_code", "2_variable_attribute_label",
        "value", "value_unit", "value_variable_code", "value_variable_label", "value_q",
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("1000A-1029_de_flat.csv", buffer.getvalue().encode("utf-8"))


def _rows(value: str = "12") -> list[list[str]]:
    output = []
    for index in range(1, 13):
        output.append([
            "1000A", "Population", "STAG", "Stichtag", "2022-05-15",
            "GEOBZ1", "Bezirke (Hamburg und Berlin)", f"110000000000{index:02d}", f"B{index}",
            "HSHGR2", "Größe des privaten Haushalts", "PERSON01", "1 Person",
            value if index == 1 else "1", "Anzahl", "PRS002", "Personen", "e",
        ])
    return output


def test_dash_is_published_zero_and_percent_rows_are_not_used(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    rows = _rows("-")
    rows.append([
        "1000A", "Population", "STAG", "Stichtag", "2022-05-15",
        "GEOBZ1", "Bezirke (Hamburg und Berlin)", "11000000000001", "B1",
        "HSHGR2", "Größe des privaten Haushalts", "PERSON01", "1 Person",
        "12,3", "%", "PRS002", "Personen", "e",
    ])
    _write_zip(path, rows)
    source = normalize_flat_count_zip(path, table_id="1000A-1029")
    assert len(source.frame) == 12
    first = source.frame.iloc[0]
    assert first["published_value"] == 0
    assert first["published_status"] == "PUBLISHED_ZERO"
    assert first["published_raw"] == "-"


@pytest.mark.parametrize("symbol", [".", "/", ""])
def test_unpublished_or_missing_count_is_rejected(tmp_path: Path, symbol: str) -> None:
    path = tmp_path / "source.zip"
    _write_zip(path, _rows(symbol))
    with pytest.raises(ValueError):
        normalize_flat_count_zip(path, table_id="1000A-1029")
