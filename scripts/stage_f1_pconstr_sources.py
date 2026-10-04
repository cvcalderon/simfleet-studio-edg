"""Stage frozen F1 P_CONSTR flat source ZIPs from the two downloaded outer bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

EXPECTED = {
    "1000A-1029_de_flat.zip": "57a2b0e9fad9122a9acfd96c8dcaff074505f2e3e8f65a7716815e540c6891fe",
    "1000A-2070_de_flat.zip": "0f81311bbc550371332f57e45a48916d1ee642624e9d2b275ec7efc1deabb152",
    "1000A-2071_de_flat.zip": "cf819cd0082aa35e167308cf1afaa39ffccffc458f594d0cde21980bfe8a53ca",
    "1000A-3082_de_flat.zip": "aa5696af6b59ffd26a529eaffc759b1d4f7a6ba4cc198572b51e3aa82efc3c14",
    "5000H-1001_de_flat.zip": "6d9905f880814c4469703966823a3c27f7a1180b5c57d41e5f30146f023c484b",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_by_basename(bundle: Path, names: set[str]) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    with zipfile.ZipFile(bundle) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"Corrupt outer bundle member: {bad}")
        for member in archive.namelist():
            basename = Path(member).name
            if basename in names:
                found[basename] = archive.read(member)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phh-bundle", type=Path, required=True)
    parser.add_argument("--hh-bundle", type=Path, required=True)
    parser.add_argument(
        "--dest", type=Path, default=Path("data/raw/zensus/f1_pconstr")
    )
    args = parser.parse_args()

    phh_names = {name for name in EXPECTED if name.startswith("1000A-")}
    hh_names = {"5000H-1001_de_flat.zip"}
    payload = extract_by_basename(args.phh_bundle.expanduser().resolve(), phh_names)
    payload.update(extract_by_basename(args.hh_bundle.expanduser().resolve(), hh_names))
    missing = sorted(set(EXPECTED).difference(payload))
    if missing:
        raise SystemExit(f"Missing expected flat ZIPs in supplied bundles: {missing}")

    dest = args.dest.expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, expected in EXPECTED.items():
        data = payload[name]
        actual = digest(data)
        if actual != expected:
            raise SystemExit(f"SHA mismatch for {name}: expected={expected} actual={actual}")
        target = dest / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"Refusing to overwrite non-matching local source: {target}")
        target.write_bytes(data)
        manifest.append({"file": name, "sha256": expected, "size_bytes": len(data)})
        print(f"PASS {name} {expected}")
    (dest / "source_stage_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"STAGED {len(manifest)}/{len(EXPECTED)} -> {dest}")


if __name__ == "__main__":
    main()
