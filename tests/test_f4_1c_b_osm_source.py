import hashlib
from pathlib import Path
from typing import Any

import pytest

from simfleet_edg.spatial import osm_source


class FakeResponse:
    def __init__(self, payload: bytes, url: str, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self._offset = 0
        self._url = url
        self.headers = headers or {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            out = self._payload[self._offset :]
            self._offset = len(self._payload)
            return out
        out = self._payload[self._offset : self._offset + size]
        self._offset += len(out)
        return out

    def geturl(self) -> str:
        return self._url


def test_exact_dated_url_rejects_latest_and_other_snapshot() -> None:
    osm_source.validate_exact_dated_url(
        osm_source.FROZEN_PBF_URL,
        expected_url=osm_source.FROZEN_PBF_URL,
        expected_filename=osm_source.FROZEN_PROVIDER_FILENAME,
    )
    with pytest.raises(ValueError):
        osm_source.validate_exact_dated_url(
            "https://download.geofabrik.de/europe/germany/berlin-latest.osm.pbf",
            expected_url=osm_source.FROZEN_PBF_URL,
            expected_filename=osm_source.FROZEN_PROVIDER_FILENAME,
        )
    with pytest.raises(ValueError):
        osm_source.validate_exact_dated_url(
            "https://download.geofabrik.de/europe/germany/berlin-261003.osm.pbf",
            expected_url=osm_source.FROZEN_PBF_URL,
            expected_filename=osm_source.FROZEN_PROVIDER_FILENAME,
        )


def test_atomic_download_md5_and_sha256(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = b"fake-pbf-bytes-for-unit-test"
    md5 = hashlib.md5(payload, usedforsecurity=False).hexdigest()
    sidecar = f"{md5}  {osm_source.FROZEN_PROVIDER_FILENAME}\n".encode()
    responses = iter(
        [
            FakeResponse(sidecar, osm_source.FROZEN_MD5_URL),
            FakeResponse(
                payload,
                osm_source.FROZEN_PBF_URL,
                {"Content-Length": str(len(payload)), "Last-Modified": "x"},
            ),
        ]
    )

    def fake_urlopen(*_args: Any, **_kwargs: Any) -> FakeResponse:
        return next(responses)

    monkeypatch.setattr(osm_source, "urlopen", fake_urlopen)
    target = tmp_path / osm_source.FROZEN_PROVIDER_FILENAME
    result = osm_source.acquire_exact_snapshot(
        source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
        pbf_url=osm_source.FROZEN_PBF_URL,
        md5_url=osm_source.FROZEN_MD5_URL,
        provider_filename=osm_source.FROZEN_PROVIDER_FILENAME,
        raw_target=target,
    )
    assert target.read_bytes() == payload
    assert not target.with_name(target.name + ".part").exists()
    assert result.provider_md5_expected == md5
    assert result.provider_md5_observed == md5
    assert result.local_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.reused_existing_raw is False


def test_md5_mismatch_aborts_without_final_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b"corrupt-transfer"
    sidecar = f"{'0' * 32}  {osm_source.FROZEN_PROVIDER_FILENAME}\n".encode()
    responses = iter(
        [
            FakeResponse(sidecar, osm_source.FROZEN_MD5_URL),
            FakeResponse(payload, osm_source.FROZEN_PBF_URL),
        ]
    )
    monkeypatch.setattr(osm_source, "urlopen", lambda *_a, **_k: next(responses))
    target = tmp_path / osm_source.FROZEN_PROVIDER_FILENAME
    with pytest.raises(ValueError, match="MD5 mismatch"):
        osm_source.acquire_exact_snapshot(
            source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
            pbf_url=osm_source.FROZEN_PBF_URL,
            md5_url=osm_source.FROZEN_MD5_URL,
            provider_filename=osm_source.FROZEN_PROVIDER_FILENAME,
            raw_target=target,
        )
    assert not target.exists()
    assert not target.with_name(target.name + ".part").exists()


def test_existing_mismatching_raw_is_never_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected_payload = b"provider-version"
    md5 = hashlib.md5(expected_payload, usedforsecurity=False).hexdigest()
    sidecar = f"{md5}  {osm_source.FROZEN_PROVIDER_FILENAME}\n".encode()
    monkeypatch.setattr(
        osm_source,
        "urlopen",
        lambda *_a, **_k: FakeResponse(sidecar, osm_source.FROZEN_MD5_URL),
    )
    target = tmp_path / osm_source.FROZEN_PROVIDER_FILENAME
    target.write_bytes(b"different-existing-bytes")
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        osm_source.acquire_exact_snapshot(
            source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
            pbf_url=osm_source.FROZEN_PBF_URL,
            md5_url=osm_source.FROZEN_MD5_URL,
            provider_filename=osm_source.FROZEN_PROVIDER_FILENAME,
            raw_target=target,
        )
    assert target.read_bytes() == before
