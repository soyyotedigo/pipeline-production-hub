from __future__ import annotations

import io
import sys
from importlib import import_module
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

config_module = import_module("app.core.config")
storage_module = import_module("app.services.storage")

settings = config_module.settings
LocalStorage = storage_module.LocalStorage
S3Storage = storage_module.S3Storage
get_storage_backend = storage_module.get_storage_backend


# ---------------------------------------------------------------------------
# Local storage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_storage_roundtrip(tmp_path: Path) -> None:
    storage = LocalStorage(root=str(tmp_path))
    payload = io.BytesIO(b"vfx-hub")

    uploaded = await storage.upload("project_a/shot_001/plate.exr", payload)
    assert Path(uploaded).exists()

    assert await storage.exists("project_a/shot_001/plate.exr") is True

    downloaded = await storage.download("project_a/shot_001/plate.exr")
    try:
        assert downloaded.read() == b"vfx-hub"
    finally:
        downloaded.close()


@pytest.mark.asyncio
async def test_local_storage_delete_and_url(tmp_path: Path) -> None:
    storage = LocalStorage(root=str(tmp_path))
    await storage.upload("project_b/asset/robot.ma", io.BytesIO(b"maya"))

    assert await storage.delete("project_b/asset/robot.ma") is True
    assert await storage.exists("project_b/asset/robot.ma") is False
    assert await storage.delete("project_b/asset/robot.ma") is False

    url = await storage.get_url("project_b/asset/robot.ma")
    assert url == "local://project_b/asset/robot.ma"


@pytest.mark.asyncio
async def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(root=str(tmp_path))

    with pytest.raises(ValueError):
        await storage.upload("../escape.txt", io.BytesIO(b"blocked"))


# ---------------------------------------------------------------------------
# S3 storage tests (mocked)
# ---------------------------------------------------------------------------


def _make_s3_storage() -> S3Storage:
    return S3Storage(
        bucket="test-bucket",
        region="us-east-1",
        endpoint_url="",
        access_key="AKIATEST",
        secret_key="secret",
    )


@pytest.mark.asyncio
async def test_s3_upload() -> None:
    storage = _make_s3_storage()
    mock_client = AsyncMock()

    with patch.object(storage, "_client") as ctx_mock:
        ctx_mock.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        ctx_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await storage.upload("shots/sh010/comp.exr", io.BytesIO(b"payload"))

    assert result == "s3://test-bucket/shots/sh010/comp.exr"
    mock_client.put_object.assert_awaited_once()
    call_kwargs = mock_client.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "test-bucket"
    assert call_kwargs["Key"] == "shots/sh010/comp.exr"
    assert call_kwargs["Body"] == b"payload"


@pytest.mark.asyncio
async def test_s3_download() -> None:
    storage = _make_s3_storage()
    mock_client = AsyncMock()

    mock_body = AsyncMock()
    mock_body.read = AsyncMock(return_value=b"file-content")
    mock_body.__aenter__ = AsyncMock(return_value=mock_body)
    mock_body.__aexit__ = AsyncMock(return_value=False)
    mock_client.get_object = AsyncMock(return_value={"Body": mock_body})

    with patch.object(storage, "_client") as ctx_mock:
        ctx_mock.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        ctx_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await storage.download("shots/sh010/comp.exr")

    assert result.read() == b"file-content"


@pytest.mark.asyncio
async def test_s3_exists_true() -> None:
    storage = _make_s3_storage()
    mock_client = AsyncMock()
    mock_client.head_object = AsyncMock(return_value={})

    with patch.object(storage, "_client") as ctx_mock:
        ctx_mock.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        ctx_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        assert await storage.exists("shots/sh010/comp.exr") is True


@pytest.mark.asyncio
async def test_s3_exists_false() -> None:
    storage = _make_s3_storage()
    mock_client = AsyncMock()

    error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
    mock_client.head_object = AsyncMock(
        side_effect=mock_client.exceptions.ClientError(error_response, "HeadObject")
    )
    # Wire up ClientError from botocore
    from botocore.exceptions import ClientError

    mock_client.exceptions.ClientError = ClientError
    mock_client.head_object = AsyncMock(side_effect=ClientError(error_response, "HeadObject"))

    with patch.object(storage, "_client") as ctx_mock:
        ctx_mock.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        ctx_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        assert await storage.exists("shots/sh010/comp.exr") is False


@pytest.mark.asyncio
async def test_s3_get_url() -> None:
    storage = _make_s3_storage()
    mock_client = AsyncMock()
    mock_client.generate_presigned_url = AsyncMock(
        return_value="https://test-bucket.s3.amazonaws.com/shots/sh010/comp.exr?AWSAccessKeyId=..."
    )

    with patch.object(storage, "_client") as ctx_mock:
        ctx_mock.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        ctx_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        url = await storage.get_url("shots/sh010/comp.exr", expires=900)

    assert "test-bucket" in url
    mock_client.generate_presigned_url.assert_awaited_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "shots/sh010/comp.exr"},
        ExpiresIn=900,
    )


@pytest.mark.asyncio
async def test_s3_delete_existing() -> None:
    storage = _make_s3_storage()
    mock_client = AsyncMock()
    mock_client.head_object = AsyncMock(return_value={})
    mock_client.delete_object = AsyncMock(return_value={})

    with patch.object(storage, "_client") as ctx_mock:
        ctx_mock.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        ctx_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        assert await storage.delete("shots/sh010/comp.exr") is True


@pytest.mark.asyncio
async def test_s3_delete_nonexistent() -> None:
    storage = _make_s3_storage()
    mock_client = AsyncMock()

    from botocore.exceptions import ClientError

    error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
    mock_client.exceptions.ClientError = ClientError
    mock_client.head_object = AsyncMock(side_effect=ClientError(error_response, "HeadObject"))

    with patch.object(storage, "_client") as ctx_mock:
        ctx_mock.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        ctx_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        assert await storage.delete("shots/sh010/comp.exr") is False


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


def test_get_storage_backend_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    local_backend = get_storage_backend()
    assert isinstance(local_backend, LocalStorage)

    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "bucket-a")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_endpoint_url", "https://s3.local")

    s3_backend = get_storage_backend()
    assert isinstance(s3_backend, S3Storage)


def test_get_storage_backend_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "unsupported")

    with pytest.raises(ValueError, match="Unsupported storage backend"):
        get_storage_backend()
