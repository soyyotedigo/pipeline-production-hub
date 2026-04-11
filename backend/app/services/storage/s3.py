from __future__ import annotations

import io
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, BinaryIO

from aiobotocore.session import get_session

from app.services.storage.base import StorageBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from types_aiobotocore_s3 import S3Client


class S3Storage(StorageBackend):
    """AWS S3 storage backend using aiobotocore."""

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str = "",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url or None
        self.access_key = access_key or None
        self.secret_key = secret_key or None
        self._session = get_session()

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[S3Client]:
        kwargs: dict[str, str] = {
            "region_name": self.region,
        }
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.access_key and self.secret_key:
            kwargs["aws_access_key_id"] = self.access_key
            kwargs["aws_secret_access_key"] = self.secret_key

        async with self._session.create_client("s3", **kwargs) as client:
            yield client

    async def upload(self, path: str, data: BinaryIO) -> str:
        key = path.lstrip("/")
        data.seek(0)
        body = data.read()

        async with self._client() as client:
            await client.put_object(Bucket=self.bucket, Key=key, Body=body)

        return f"s3://{self.bucket}/{key}"

    async def download(self, path: str) -> BinaryIO:
        key = path.lstrip("/")

        async with self._client() as client:
            response = await client.get_object(Bucket=self.bucket, Key=key)
            async with response["Body"] as stream:
                content = await stream.read()

        return io.BytesIO(content)

    async def delete(self, path: str) -> bool:
        key = path.lstrip("/")

        if not await self.exists(path):
            return False

        async with self._client() as client:
            await client.delete_object(Bucket=self.bucket, Key=key)

        return True

    async def exists(self, path: str) -> bool:
        key = path.lstrip("/")

        async with self._client() as client:
            try:
                await client.head_object(Bucket=self.bucket, Key=key)
                return True
            except client.exceptions.ClientError as exc:
                if exc.response["Error"]["Code"] == "404":
                    return False
                raise

    async def get_url(self, path: str, expires: int = 3600) -> str:
        key = path.lstrip("/")

        async with self._client() as client:
            url: str = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires,
            )
        return url
