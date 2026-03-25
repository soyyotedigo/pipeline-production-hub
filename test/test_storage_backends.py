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
LocalStorage = storage_module.LocalStorage
S3Storage = storage_module.S3Storage
get_storage_backend = storage_module.get_storage_backend


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


@pytest.mark.asyncio
async def test_s3_storage_stub_behaviour() -> None:
    storage = S3Storage(bucket="vfxhub", endpoint_url="https://s3.example.com")

    url = await storage.get_url("shots/sh010/comp.exr")
    assert url == "https://s3.example.com/vfxhub/shots/sh010/comp.exr"

    with pytest.raises(NotImplementedError):
        await storage.upload("shots/sh010/comp.exr", io.BytesIO(b"payload"))


def test_get_storage_backend_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    local_backend = get_storage_backend()
    assert isinstance(local_backend, LocalStorage)

    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "bucket-a")
    monkeypatch.setattr(settings, "s3_endpoint_url", "https://s3.local")

    s3_backend = get_storage_backend()
    assert isinstance(s3_backend, S3Storage)


def test_get_storage_backend_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "unsupported")

    with pytest.raises(ValueError, match="Unsupported storage backend"):
        get_storage_backend()
