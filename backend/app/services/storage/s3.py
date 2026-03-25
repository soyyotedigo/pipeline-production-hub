from __future__ import annotations

from typing import BinaryIO

from app.services.storage.base import StorageBackend


class S3Storage(StorageBackend):
    def __init__(
        self,
        bucket: str,
        endpoint_url: str = "",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key

    async def upload(self, path: str, data: BinaryIO) -> str:
        del data
        msg = f"S3 upload is not implemented for demo backend yet: {path}"
        raise NotImplementedError(msg)

    async def download(self, path: str) -> BinaryIO:
        msg = f"S3 download is not implemented for demo backend yet: {path}"
        raise NotImplementedError(msg)

    async def delete(self, path: str) -> bool:
        msg = f"S3 delete is not implemented for demo backend yet: {path}"
        raise NotImplementedError(msg)

    async def exists(self, path: str) -> bool:
        msg = f"S3 exists is not implemented for demo backend yet: {path}"
        raise NotImplementedError(msg)

    async def get_url(self, path: str, expires: int = 3600) -> str:
        del expires
        normalized_path = path.lstrip("/")
        if self.endpoint_url:
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket}/{normalized_path}"
        return f"s3://{self.bucket}/{normalized_path}"
