"""
Live integration test for S3 storage backend.
Requires real AWS credentials in .env (S3_ACCESS_KEY, S3_SECRET_KEY).

Run with:
    python -m pytest test/test_s3_live.py -v -s -m live
"""

from __future__ import annotations

import io
import sys
from importlib import import_module
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

config_module = import_module("app.core.config")
storage_module = import_module("app.services.storage")

settings = config_module.settings
S3Storage = storage_module.S3Storage

TEST_KEY = "test/healthcheck/live_test.txt"
TEST_PAYLOAD = b"pipeline-production-hub live test"

_has_s3_creds = bool(
    getattr(settings, "s3_access_key", None)
    and getattr(settings, "s3_secret_key", None)
    and getattr(settings, "s3_bucket", None)
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not _has_s3_creds, reason="S3 credentials not configured"),
]


@pytest.fixture(scope="module")
def s3() -> S3Storage:
    return S3Storage(
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )


@pytest.mark.asyncio
async def test_s3_upload_live(s3: S3Storage) -> None:
    result = await s3.upload(TEST_KEY, io.BytesIO(TEST_PAYLOAD))
    print(f"\n  uploaded -> {result}")
    assert result == f"s3://{settings.s3_bucket}/{TEST_KEY}"


@pytest.mark.asyncio
async def test_s3_exists_live(s3: S3Storage) -> None:
    exists = await s3.exists(TEST_KEY)
    print(f"\n  exists({TEST_KEY}) -> {exists}")
    assert exists is True


@pytest.mark.asyncio
async def test_s3_download_live(s3: S3Storage) -> None:
    stream = await s3.download(TEST_KEY)
    content = stream.read()
    print(f"\n  downloaded {len(content)} bytes")
    assert content == TEST_PAYLOAD


@pytest.mark.asyncio
async def test_s3_presigned_url_live(s3: S3Storage) -> None:
    url = await s3.get_url(TEST_KEY, expires=300)
    print(f"\n  presigned URL -> {url[:80]}...")
    assert "pipeline-production-hub" in url
    assert TEST_KEY in url


@pytest.mark.asyncio
async def test_s3_delete_live(s3: S3Storage) -> None:
    deleted = await s3.delete(TEST_KEY)
    print(f"\n  delete({TEST_KEY}) -> {deleted}")
    assert deleted is True

    still_exists = await s3.exists(TEST_KEY)
    assert still_exists is False
