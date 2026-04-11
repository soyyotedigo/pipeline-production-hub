from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageBackend(ABC):
    @abstractmethod
    async def upload(self, path: str, data: BinaryIO) -> str:
        raise NotImplementedError

    @abstractmethod
    async def download(self, path: str) -> BinaryIO:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_url(self, path: str, expires: int = 3600) -> str:
        raise NotImplementedError
