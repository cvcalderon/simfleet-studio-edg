"""Utilities for PRE-F3 R1 source-byte and structure auditing."""

from __future__ import annotations

import csv
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_header(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw, 0, 1, "unable to decode CSV header")


def inspect_csv(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        first = handle.readline()
    header_text, encoding = _decode_header(first)
    delimiter = ";" if header_text.count(";") >= header_text.count(",") else ","
    header = next(csv.reader([header_text], delimiter=delimiter))

    # Counting binary newlines is safe for the MiD CSV package and avoids loading large files.
    with path.open("rb") as handle:
        line_count = sum(chunk.count(b"\n") for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""))
        if path.stat().st_size:
            handle.seek(-1, 2)
            last_byte = handle.read(1)
            if last_byte != b"\n":
                line_count += 1
    rows = max(0, line_count - 1)
    return {
        "rows": rows,
        "columns": len(header),
        "header": header,
        "encoding": encoding,
        "delimiter": delimiter,
    }


def inspect_xlsx(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        workbook_xml = archive.read("xl/workbook.xml")
    root = ET.fromstring(workbook_xml)
    sheets = root.find("main:sheets", XLSX_NS)
    names = [] if sheets is None else [node.attrib.get("name", "") for node in sheets]
    return {"sheets": len(names), "sheet_names": names}


def inspect_geojson(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        obj = json.load(handle)
    features = obj.get("features") if isinstance(obj, dict) else None
    return {
        "type": obj.get("type") if isinstance(obj, dict) else None,
        "features": len(features) if isinstance(features, list) else None,
    }


def inspect_zip(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        names = archive.namelist()
    return {"members": len(names), "zip_integrity": bad is None, "first_bad_member": bad}


def inspect_source(path: Path, kind: str) -> dict[str, Any]:
    if kind == "csv":
        return inspect_csv(path)
    if kind == "xlsx":
        return inspect_xlsx(path)
    if kind == "geojson":
        return inspect_geojson(path)
    if kind == "zip":
        return inspect_zip(path)
    return {}
