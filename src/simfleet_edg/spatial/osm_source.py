from __future__ import annotations

import hashlib
import importlib
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen

USER_AGENT = "SimFleet-EDG-F4.1c-B/1.0"
FROZEN_PBF_URL = "https://download.geofabrik.de/europe/germany/berlin-261004.osm.pbf"
FROZEN_MD5_URL = "https://download.geofabrik.de/europe/germany/berlin-261004.osm.pbf.md5"
FROZEN_PROVIDER_FILENAME = "berlin-261004.osm.pbf"
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class HttpMetadata:
    requested_url: str
    final_url: str
    last_modified: str | None
    content_length_bytes: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    source_snapshot_id: str
    provider_filename: str
    provider_download_url: str
    provider_md5_url: str
    retrieved_at_utc: str
    provider_md5_expected: str
    provider_md5_observed: str
    local_sha256: str
    file_size_bytes: int
    raw_path: str
    md5_sidecar_path: str
    reused_existing_raw: bool
    http: HttpMetadata

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["http"] = self.http.to_dict()
        return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_provider_md5(text: str, expected_filename: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("Provider MD5 sidecar must contain exactly one non-empty line")
    parts = lines[0].split()
    if not parts:
        raise ValueError("Provider MD5 sidecar is empty")
    digest = parts[0].lower()
    if len(digest) != 32 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("Provider MD5 sidecar does not contain a valid MD5 digest")
    if len(parts) >= 2:
        named = parts[-1].lstrip("*")
        if Path(named).name != expected_filename:
            raise ValueError(
                f"Provider MD5 sidecar names {named!r}, expected {expected_filename!r}"
            )
    return digest


def validate_exact_dated_url(url: str, *, expected_url: str, expected_filename: str) -> None:
    if url != expected_url:
        raise ValueError(f"Source URL differs from frozen exact URL: {url}")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Frozen OSM source must use HTTPS")
    if Path(parsed.path).name != expected_filename:
        raise ValueError("Frozen OSM URL filename differs from provider_filename")
    lowered = url.lower()
    if "latest" in lowered:
        raise ValueError("Mutable latest aliases are forbidden")


def _http_metadata(requested_url: str, response: Any) -> HttpMetadata:
    headers = response.headers
    raw_length = headers.get("Content-Length")
    content_length = int(raw_length) if raw_length and raw_length.isdigit() else None
    return HttpMetadata(
        requested_url=requested_url,
        final_url=str(response.geturl()),
        last_modified=headers.get("Last-Modified"),
        content_length_bytes=content_length,
    )


def _fetch_text(url: str) -> tuple[str, HttpMetadata]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:  # noqa: S310 - frozen HTTPS URL validated upstream
        payload = response.read().decode("utf-8")
        metadata = _http_metadata(url, response)
    return payload, metadata


def _write_sidecar_immutably(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"Existing provider sidecar differs and will not be overwritten: {path}")
        return
    part = path.with_name(path.name + ".part")
    if part.exists():
        part.unlink()
    part.write_bytes(payload)
    os.replace(part, path)


def _stream_response_to_part(
    response: Any,
    part_path: Path,
) -> tuple[str, str, int]:
    md5_digest = hashlib.md5(usedforsecurity=False)
    sha_digest = hashlib.sha256()
    size = 0
    with part_path.open("wb") as handle:
        _copy_hashing(response, handle, md5_digest, sha_digest)
        size = handle.tell()
        handle.flush()
        os.fsync(handle.fileno())
    return md5_digest.hexdigest(), sha_digest.hexdigest(), size


def _copy_hashing(
    source: BinaryIO | Any,
    target: BinaryIO,
    md5_digest: Any,
    sha_digest: Any,
) -> None:
    while True:
        block = source.read(_CHUNK_SIZE)
        if not block:
            break
        target.write(block)
        md5_digest.update(block)
        sha_digest.update(block)


def _probe_exact_url(url: str) -> HttpMetadata:
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=120) as response:  # noqa: S310 - frozen HTTPS URL validated upstream
            return _http_metadata(url, response)
    except Exception:
        # Some static file hosts reject HEAD. A one-byte ranged GET retains exact URL semantics
        # while avoiding a second full transfer when existing raw bytes are reused.
        fallback = Request(
            url,
            headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
        )
        with urlopen(fallback, timeout=120) as response:  # noqa: S310 - frozen HTTPS URL validated upstream
            return _http_metadata(url, response)


def acquire_exact_snapshot(
    *,
    source_snapshot_id: str,
    pbf_url: str,
    md5_url: str,
    provider_filename: str,
    raw_target: Path,
) -> AcquisitionResult:
    if provider_filename != FROZEN_PROVIDER_FILENAME:
        raise ValueError("Provider filename differs from the frozen F4.1c-B source")
    validate_exact_dated_url(
        pbf_url,
        expected_url=FROZEN_PBF_URL,
        expected_filename=FROZEN_PROVIDER_FILENAME,
    )
    validate_exact_dated_url(
        md5_url,
        expected_url=FROZEN_MD5_URL,
        expected_filename=FROZEN_PROVIDER_FILENAME + ".md5",
    )

    md5_text, _ = _fetch_text(md5_url)
    provider_md5 = parse_provider_md5(md5_text, provider_filename)
    md5_path = raw_target.with_name(provider_filename + ".md5")
    _write_sidecar_immutably(md5_path, md5_text.encode("utf-8"))

    raw_target.parent.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(UTC).isoformat()

    if raw_target.exists():
        observed_md5 = md5_file(raw_target)
        if observed_md5 != provider_md5:
            raise FileExistsError(
                "Existing raw OSM file differs from provider MD5 and will not be overwritten"
            )
        http = _probe_exact_url(pbf_url)
        return AcquisitionResult(
            source_snapshot_id=source_snapshot_id,
            provider_filename=provider_filename,
            provider_download_url=pbf_url,
            provider_md5_url=md5_url,
            retrieved_at_utc=retrieved_at,
            provider_md5_expected=provider_md5,
            provider_md5_observed=observed_md5,
            local_sha256=sha256_file(raw_target),
            file_size_bytes=raw_target.stat().st_size,
            raw_path=str(raw_target),
            md5_sidecar_path=str(md5_path),
            reused_existing_raw=True,
            http=http,
        )

    part = raw_target.with_name(raw_target.name + ".part")
    if part.exists():
        part.unlink()

    request = Request(pbf_url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=120) as response:  # noqa: S310 - frozen HTTPS URL validated upstream
            http = _http_metadata(pbf_url, response)
            observed_md5, local_sha256, size = _stream_response_to_part(response, part)
        if http.final_url != pbf_url:
            raise ValueError(f"Unexpected redirect for frozen OSM source: {http.final_url}")
        if observed_md5 != provider_md5:
            raise ValueError(
                f"Provider MD5 mismatch: expected {provider_md5}, observed {observed_md5}"
            )
        if http.content_length_bytes is not None and size != http.content_length_bytes:
            raise ValueError(
                f"Content-Length mismatch: header={http.content_length_bytes}, bytes={size}"
            )
        os.replace(part, raw_target)
    except Exception:
        if part.exists():
            part.unlink()
        raise

    return AcquisitionResult(
        source_snapshot_id=source_snapshot_id,
        provider_filename=provider_filename,
        provider_download_url=pbf_url,
        provider_md5_url=md5_url,
        retrieved_at_utc=retrieved_at,
        provider_md5_expected=provider_md5,
        provider_md5_observed=observed_md5,
        local_sha256=local_sha256,
        file_size_bytes=size,
        raw_path=str(raw_target),
        md5_sidecar_path=str(md5_path),
        reused_existing_raw=False,
        http=http,
    )


def read_pbf_header(path: Path) -> dict[str, Any]:
    try:
        osmium: Any = importlib.import_module("osmium")
    except ImportError as exc:
        raise RuntimeError(
            "F4.1c-B PBF support requires the 'osm' extra: "
            "python -m pip install -e '.[osm]'"
        ) from exc

    processor = osmium.FileProcessor(str(path))
    header = processor.header
    box = header.box()
    bbox: list[float] | None = None
    if box.valid():
        bbox = [
            float(box.bottom_left.lon),
            float(box.bottom_left.lat),
            float(box.top_right.lon),
            float(box.top_right.lat),
        ]
    timestamp = header.get("osmosis_replication_timestamp", "") or None
    return {
        "pbf_open_read_check": True,
        "pbf_header_timestamp": timestamp,
        "pbf_bbox": bbox,
        "header_bbox_present": bbox is not None,
        "header_timestamp_present": timestamp is not None,
        "generator": header.get("generator", "") or None,
    }
