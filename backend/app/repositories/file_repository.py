import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, File, Shot


class FileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        name: str,
        original_name: str,
        version: int,
        storage_path: str,
        size_bytes: int,
        checksum_sha256: str,
        mime_type: str,
        uploaded_by: uuid.UUID | None,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        metadata_json: dict[str, object] | None = None,
    ) -> File:
        item = File(
            name=name,
            original_name=original_name,
            version=version,
            storage_path=storage_path,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            mime_type=mime_type,
            uploaded_by=uploaded_by,
            shot_id=shot_id,
            asset_id=asset_id,
            metadata_json=metadata_json or {},
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def get_by_id(self, file_id: uuid.UUID) -> File | None:
        result = await self.db.execute(
            select(File).where(File.id == file_id, File.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_id_any(self, file_id: uuid.UUID) -> File | None:
        result = await self.db.execute(select(File).where(File.id == file_id))
        return result.scalar_one_or_none()

    async def get_latest_active_by_checksum(self, checksum_sha256: str) -> File | None:
        result = await self.db.execute(
            select(File)
            .where(
                File.checksum_sha256 == checksum_sha256,
                File.deleted_at.is_(None),
            )
            .order_by(File.created_at.desc(), File.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_next_version(
        self,
        *,
        original_name: str,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
    ) -> int:
        statement = select(func.max(File.version)).where(File.original_name == original_name)
        if shot_id is not None:
            statement = statement.where(
                File.shot_id == shot_id,
                File.asset_id.is_(None),
                File.deleted_at.is_(None),
            )
        if asset_id is not None:
            statement = statement.where(
                File.asset_id == asset_id,
                File.shot_id.is_(None),
                File.deleted_at.is_(None),
            )
        result = await self.db.execute(statement)
        current_max = result.scalar_one_or_none()
        return (int(current_max) if current_max is not None else 0) + 1

    async def list_versions(
        self,
        *,
        original_name: str,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
    ) -> list[File]:
        statement = select(File).where(
            File.original_name == original_name, File.deleted_at.is_(None)
        )
        if shot_id is not None:
            statement = statement.where(File.shot_id == shot_id, File.asset_id.is_(None))
        if asset_id is not None:
            statement = statement.where(File.asset_id == asset_id, File.shot_id.is_(None))

        result = await self.db.execute(
            statement.order_by(File.version.desc(), File.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_file_versions(
        self,
        *,
        shot_id: uuid.UUID | None = None,
        asset_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[File]:
        if (shot_id is None and asset_id is None) or (shot_id is not None and asset_id is not None):
            raise ValueError("Provide exactly one of shot_id or asset_id")

        partition_columns = (File.original_name, File.shot_id, File.asset_id)
        ranked_files = (
            select(
                File.id.label("file_id"),
                func.row_number()
                .over(
                    partition_by=partition_columns,
                    order_by=(File.version.desc(), File.created_at.desc()),
                )
                .label("row_num"),
            )
            .where(
                and_(
                    File.shot_id == shot_id if shot_id is not None else File.shot_id.is_(None),
                    File.asset_id == asset_id if asset_id is not None else File.asset_id.is_(None),
                    File.deleted_at.is_(None),
                )
            )
            .subquery()
        )

        statement = (
            select(File)
            .join(ranked_files, ranked_files.c.file_id == File.id)
            .where(ranked_files.c.row_num == 1)
            .order_by(File.original_name.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def list_file_versions_with_total(
        self,
        *,
        shot_id: uuid.UUID | None = None,
        asset_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[File], int]:
        items = await self.list_file_versions(
            shot_id=shot_id,
            asset_id=asset_id,
            offset=offset,
            limit=limit,
        )

        count_query = select(func.count(func.distinct(File.original_name))).where(
            File.deleted_at.is_(None)
        )
        if shot_id is not None:
            count_query = count_query.where(File.shot_id == shot_id, File.asset_id.is_(None))
        if asset_id is not None:
            count_query = count_query.where(File.asset_id == asset_id, File.shot_id.is_(None))

        total_result = await self.db.execute(count_query)
        total = int(total_result.scalar_one())
        return items, total

    async def list_versions_for_file(self, file_id: uuid.UUID) -> list[File]:
        item = await self.get_by_id(file_id)
        if item is None:
            return []
        return await self.list_versions(
            original_name=item.original_name,
            shot_id=item.shot_id,
            asset_id=item.asset_id,
        )

    async def soft_delete(self, item: File) -> File:
        item.deleted_at = datetime.now(timezone.utc)
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def restore(self, item: File) -> File:
        item.deleted_at = None
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def hard_delete(self, item: File) -> None:
        await self.db.delete(item)

    async def update(self, item: File, **fields: object) -> File:
        for key, value in fields.items():
            setattr(item, key, value)
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[File], int]:
        count_stmt = (
            select(func.count(File.id))
            .outerjoin(Shot, File.shot_id == Shot.id)
            .outerjoin(Asset, File.asset_id == Asset.id)
            .where(
                File.deleted_at.is_(None),
                or_(Shot.project_id == project_id, Asset.project_id == project_id),
            )
        )
        total_result = await self.db.execute(count_stmt)
        total = int(total_result.scalar_one())

        stmt = (
            select(File)
            .outerjoin(Shot, File.shot_id == Shot.id)
            .outerjoin(Asset, File.asset_id == Asset.id)
            .where(
                File.deleted_at.is_(None),
                or_(Shot.project_id == project_id, Asset.project_id == project_id),
            )
            .order_by(File.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def count_active_for_project(self, project_id: uuid.UUID) -> int:
        statement = (
            select(func.count(File.id))
            .select_from(File)
            .outerjoin(Shot, File.shot_id == Shot.id)
            .outerjoin(Asset, File.asset_id == Asset.id)
            .where(
                File.deleted_at.is_(None),
                or_(Shot.project_id == project_id, Asset.project_id == project_id),
            )
        )
        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def storage_used_bytes_for_project(self, project_id: uuid.UUID) -> int:
        statement = (
            select(func.coalesce(func.sum(File.size_bytes), 0))
            .select_from(File)
            .outerjoin(Shot, File.shot_id == Shot.id)
            .outerjoin(Asset, File.asset_id == Asset.id)
            .where(
                File.deleted_at.is_(None),
                or_(Shot.project_id == project_id, Asset.project_id == project_id),
            )
        )
        result = await self.db.execute(statement)
        return int(result.scalar_one())
