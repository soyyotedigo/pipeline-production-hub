from __future__ import annotations

from app.core.config import settings
from app.services.storage.base import StorageBackend
from app.services.storage.local import LocalStorage
from app.services.storage.s3 import S3Storage


def get_storage_backend() -> StorageBackend:
    backend = settings.storage_backend.strip().lower()

    if backend == "local":
        return LocalStorage(root=settings.local_storage_root)

    if backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
        )

    msg = f"Unsupported storage backend: {settings.storage_backend}"
    raise ValueError(msg)
