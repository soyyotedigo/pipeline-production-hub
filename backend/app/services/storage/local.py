from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from app.services.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, root: str) -> None:
        self.chunk_size_bytes = 1024 * 1024
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        if self.root != candidate and self.root not in candidate.parents:
            msg = "Invalid storage path outside local storage root"
            raise ValueError(msg)
        return candidate

    async def upload(self, path: str, data: BinaryIO) -> str:
        destination = self._resolve_safe_path(path)

        def _write() -> str:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with suppress(AttributeError, OSError):
                data.seek(0)
            with destination.open("wb") as output:
                while True:
                    chunk = data.read(self.chunk_size_bytes)
                    if not chunk:
                        break
                    output.write(chunk)
            return str(destination)

        return await asyncio.to_thread(_write)

    async def download(self, path: str) -> BinaryIO:
        source = self._resolve_safe_path(path)

        def _open() -> BinaryIO:
            return source.open("rb")

        return await asyncio.to_thread(_open)

    async def delete(self, path: str) -> bool:
        target = self._resolve_safe_path(path)

        def _delete() -> bool:
            if not target.exists():
                return False
            target.unlink()
            return True

        return await asyncio.to_thread(_delete)

    async def exists(self, path: str) -> bool:
        target = self._resolve_safe_path(path)
        return await asyncio.to_thread(target.exists)

    async def get_url(self, path: str, expires: int = 3600) -> str:
        del expires
        safe_path = quote(path.lstrip("/"))
        return f"local://{safe_path}"
