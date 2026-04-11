from __future__ import annotations

import sys
import uuid
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

models_module = import_module("app.models")
repository_module = import_module("app.repositories.file_repository")

Asset = models_module.Asset
AssetType = models_module.AssetType
File = models_module.File
Project = models_module.Project
Shot = models_module.Shot
User = models_module.User
FileRepository = repository_module.FileRepository


async def _seed_project_context(db_session: AsyncSession) -> tuple[User, Project, Shot, Asset]:
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"files-{uuid.uuid4().hex[:8]}@vfxhub.dev",
        hashed_password="hash",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(name="Files Project", code=f"FIL{uuid.uuid4().hex[:4]}", created_by=user_id)
    db_session.add(project)
    await db_session.flush()

    shot = Shot(project_id=project.id, name="Shot 001", code="SH001")
    asset = Asset(
        project_id=project.id,
        name="Robot",
        code="ROBOT",
        asset_type=AssetType.character,
    )
    db_session.add(shot)
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(project)
    await db_session.refresh(shot)
    await db_session.refresh(asset)
    return user, project, shot, asset


@pytest.mark.asyncio
async def test_file_model_enforces_exactly_one_parent(db_session: AsyncSession) -> None:
    user, _, shot, asset = await _seed_project_context(db_session)

    invalid_file = File(
        name="plate_v001.exr",
        original_name="plate.exr",
        version=1,
        storage_path="/demo/plate/v001/plate.exr",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        mime_type="image/x-exr",
        uploaded_by=user.id,
        shot_id=shot.id,
        asset_id=asset.id,
        metadata_json={},
    )
    db_session.add(invalid_file)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_file_versions_query_returns_latest_per_original_name(
    db_session: AsyncSession,
) -> None:
    user, _, shot, _ = await _seed_project_context(db_session)
    repository = FileRepository(db_session)

    await repository.create(
        name="comp_v001.exr",
        original_name="comp.exr",
        version=1,
        storage_path="/demo/shot/comp/v001/comp.exr",
        size_bytes=100,
        checksum_sha256="1" * 64,
        mime_type="image/x-exr",
        uploaded_by=user.id,
        shot_id=shot.id,
        asset_id=None,
        metadata_json={"stage": "layout"},
    )
    await repository.create(
        name="comp_v002.exr",
        original_name="comp.exr",
        version=2,
        storage_path="/demo/shot/comp/v002/comp.exr",
        size_bytes=120,
        checksum_sha256="2" * 64,
        mime_type="image/x-exr",
        uploaded_by=user.id,
        shot_id=shot.id,
        asset_id=None,
        metadata_json={"stage": "lighting"},
    )
    await repository.create(
        name="matte_v001.exr",
        original_name="matte.exr",
        version=1,
        storage_path="/demo/shot/matte/v001/matte.exr",
        size_bytes=90,
        checksum_sha256="3" * 64,
        mime_type="image/x-exr",
        uploaded_by=user.id,
        shot_id=shot.id,
        asset_id=None,
        metadata_json={},
    )
    await db_session.commit()

    grouped = await repository.list_file_versions(shot_id=shot.id)
    assert len(grouped) == 2

    grouped_map = {item.original_name: item for item in grouped}
    assert grouped_map["comp.exr"].version == 2
    assert grouped_map["matte.exr"].version == 1

    comp_history = await repository.list_versions(
        original_name="comp.exr",
        shot_id=shot.id,
        asset_id=None,
    )
    assert [item.version for item in comp_history] == [2, 1]
