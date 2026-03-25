from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import and_, select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, engine
from app.models import (
    Asset,
    AssetStatus,
    AssetType,
    Episode,
    EpisodeStatus,
    Project,
    ProjectStatus,
    ProjectType,
    Role,
    RoleName,
    Sequence,
    SequenceScopeType,
    SequenceStatus,
    Shot,
    ShotStatus,
    User,
    UserRole,
)


@dataclass(frozen=True)
class SeedConfig:
    admin_email: str
    admin_password: str
    demo_user_password: str
    demo_project_name: str
    demo_project_code: str
    demo_project_client: str


def _get_seed_config() -> SeedConfig:
    return SeedConfig(
        admin_email=os.getenv("SEED_ADMIN_EMAIL", "admin@vfxhub.dev"),
        admin_password=os.getenv("SEED_ADMIN_PASSWORD", "admin123"),
        demo_user_password=os.getenv("SEED_DEMO_USER_PASSWORD", "demo123"),
        demo_project_name=os.getenv("SEED_DEMO_PROJECT_NAME", "Demo Project"),
        demo_project_code=os.getenv("SEED_DEMO_PROJECT_CODE", "DEMO"),
        demo_project_client=os.getenv("SEED_DEMO_PROJECT_CLIENT", "Demo Client"),
    )


async def _ensure_roles() -> dict[RoleName, Role]:
    descriptions: dict[RoleName, str] = {
        RoleName.admin: "Global administrator",
        RoleName.supervisor: "Supervises production",
        RoleName.lead: "Leads a team or project",
        RoleName.artist: "Artist role",
        RoleName.worker: "General worker role",
        RoleName.client: "Client role for project visibility",
    }

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Role))
        existing_roles = {role.name: role for role in result.scalars().all()}

        created_count = 0
        for role_name, description in descriptions.items():
            if role_name in existing_roles:
                continue
            session.add(Role(name=role_name, description=description))
            created_count += 1

        if created_count > 0:
            await session.commit()

        result = await session.execute(select(Role))
        return {role.name: role for role in result.scalars().all()}


async def _ensure_admin_user(config: SeedConfig) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == config.admin_email))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=config.admin_email,
                hashed_password=hash_password(config.admin_password),
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        return user


async def _ensure_admin_role_assignment(admin_user: User, admin_role: Role) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserRole).where(
                and_(
                    UserRole.user_id == admin_user.id,
                    UserRole.role_id == admin_role.id,
                    UserRole.project_id.is_(None),
                )
            )
        )
        existing_assignment = result.scalar_one_or_none()
        if existing_assignment is not None:
            return

        session.add(
            UserRole(
                user_id=admin_user.id,
                role_id=admin_role.id,
                project_id=None,
            )
        )
        await session.commit()


async def _ensure_demo_project(config: SeedConfig, admin_user: User) -> Project:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Project).where(Project.code == config.demo_project_code)
        )
        project = result.scalar_one_or_none()

        if project is None:
            project = Project(
                name=config.demo_project_name,
                code=config.demo_project_code,
                project_type=ProjectType.series,
                client=config.demo_project_client,
                status=ProjectStatus.in_progress,
                description=f"Auto-seeded demo project created for {admin_user.email}",
                created_by=admin_user.id,
            )
            session.add(project)
        else:
            project.name = config.demo_project_name
            project.client = config.demo_project_client
            project.project_type = ProjectType.series
            project.status = ProjectStatus.in_progress
            if not project.description:
                project.description = f"Auto-seeded demo project created for {admin_user.email}"

        await session.commit()
        await session.refresh(project)
        return project


async def _ensure_demo_users(config: SeedConfig) -> dict[str, User]:
    demo_users: tuple[tuple[str, str, str, str, str, str], ...] = (
        ("supervisor@vfxhub.dev", "Sofia", "Stone", "Sofia Stone", "Production", "UTC"),
        ("lead@vfxhub.dev", "Leo", "Kim", "Leo Kim", "Lighting", "UTC"),
        ("artist@vfxhub.dev", "Aria", "Lopez", "Aria Lopez", "Compositing", "UTC"),
        ("worker@vfxhub.dev", "Will", "Park", "Will Park", "Matchmove", "UTC"),
        ("client@vfxhub.dev", "Clara", "Reed", "Clara Reed", "Client", "UTC"),
    )

    emails = [email for email, *_ in demo_users]

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email.in_(emails)))
        existing_by_email = {user.email: user for user in result.scalars().all()}

        for email, first_name, last_name, display_name, department, timezone in demo_users:
            if email in existing_by_email:
                user = existing_by_email[email]
                user.first_name = user.first_name or first_name
                user.last_name = user.last_name or last_name
                user.display_name = user.display_name or display_name
                user.department = user.department or department
                user.timezone = user.timezone or timezone
                continue

            session.add(
                User(
                    email=email,
                    hashed_password=hash_password(config.demo_user_password),
                    is_active=True,
                    first_name=first_name,
                    last_name=last_name,
                    display_name=display_name,
                    department=department,
                    timezone=timezone,
                )
            )

        await session.commit()

        refreshed = await session.execute(select(User).where(User.email.in_(emails)))
        return {user.email: user for user in refreshed.scalars().all()}


async def _ensure_demo_project_role_assignments(
    project: Project,
    roles: dict[RoleName, Role],
    users_by_email: dict[str, User],
) -> int:
    assignments: tuple[tuple[str, RoleName], ...] = (
        ("supervisor@vfxhub.dev", RoleName.supervisor),
        ("lead@vfxhub.dev", RoleName.lead),
        ("artist@vfxhub.dev", RoleName.artist),
        ("worker@vfxhub.dev", RoleName.worker),
        ("client@vfxhub.dev", RoleName.client),
    )

    user_ids = [user.id for user in users_by_email.values()]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserRole).where(
                and_(
                    UserRole.project_id == project.id,
                    UserRole.user_id.in_(user_ids),
                )
            )
        )
        existing = {
            (assignment.user_id, assignment.role_id) for assignment in result.scalars().all()
        }

        created_count = 0
        for email, role_name in assignments:
            user = users_by_email.get(email)
            role = roles.get(role_name)
            if user is None or role is None:
                continue

            key = (user.id, role.id)
            if key in existing:
                continue

            session.add(UserRole(user_id=user.id, role_id=role.id, project_id=project.id))
            created_count += 1

        if created_count > 0:
            await session.commit()

        return created_count


async def _ensure_demo_episodes(project: Project) -> dict[str, Episode]:
    demo_episodes: tuple[tuple[str, str, int, int], ...] = (
        ("E01", "Pilot", 101, 1),
        ("E02", "Arrival", 102, 2),
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Episode).where(Episode.project_id == project.id))
        existing_by_code = {episode.code: episode for episode in result.scalars().all()}

        for code, name, production_number, order in demo_episodes:
            episode = existing_by_code.get(code)
            if episode is None:
                episode = Episode(project_id=project.id, code=code, name=name)
                session.add(episode)

            episode.name = name
            episode.status = EpisodeStatus.in_progress
            episode.production_number = production_number
            episode.order = order

        await session.commit()

        refreshed = await session.execute(
            select(Episode).where(Episode.project_id == project.id).order_by(Episode.code)
        )
        return {episode.code: episode for episode in refreshed.scalars().all()}


async def _ensure_demo_sequences(
    project: Project,
    episodes_by_code: dict[str, Episode],
) -> dict[str, Sequence]:
    demo_sequences: tuple[tuple[str, str, str, int, int], ...] = (
        ("SQ010", "City Intro", "E01", 1001, 1),
        ("SQ020", "Hangar Conflict", "E01", 1002, 2),
        ("SQ030", "Escape Run", "E02", 2001, 1),
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Sequence).where(Sequence.project_id == project.id))
        existing_by_code = {sequence.code: sequence for sequence in result.scalars().all()}

        for code, name, episode_code, production_number, order in demo_sequences:
            sequence = existing_by_code.get(code)
            if sequence is None:
                sequence = Sequence(project_id=project.id, code=code, name=name)
                session.add(sequence)

            sequence.name = name
            sequence.episode_id = episodes_by_code[episode_code].id
            sequence.scope_type = SequenceScopeType.sequence
            sequence.status = SequenceStatus.in_progress
            sequence.production_number = production_number
            sequence.order = order

        await session.commit()

        refreshed = await session.execute(
            select(Sequence).where(Sequence.project_id == project.id).order_by(Sequence.code)
        )
        return {sequence.code: sequence for sequence in refreshed.scalars().all()}


async def _ensure_demo_shots(
    project: Project,
    sequences_by_code: dict[str, Sequence],
    users_by_email: dict[str, User],
) -> list[Shot]:
    demo_shots: tuple[tuple[str, str, str, int, int, str, ShotStatus], ...] = (
        (
            "SH010",
            "Opening Wide",
            "SQ010",
            1001,
            1110,
            "artist@vfxhub.dev",
            ShotStatus.in_progress,
        ),
        (
            "SH020",
            "Hero Reveal",
            "SQ020",
            1111,
            1220,
            "lead@vfxhub.dev",
            ShotStatus.review,
        ),
        (
            "SH030",
            "FX Impact",
            "SQ030",
            1221,
            1320,
            "worker@vfxhub.dev",
            ShotStatus.pending,
        ),
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Shot).where(Shot.project_id == project.id))
        existing_by_code = {shot.code: shot for shot in result.scalars().all()}

        for (
            shot_code,
            shot_name,
            sequence_code,
            frame_start,
            frame_end,
            assignee_email,
            status,
        ) in demo_shots:
            shot = existing_by_code.get(shot_code)
            if shot is None:
                shot = Shot(project_id=project.id, code=shot_code, name=shot_name)
                session.add(shot)

            shot.name = shot_name
            shot.status = status
            shot.sequence_id = sequences_by_code[sequence_code].id
            shot.frame_start = frame_start
            shot.frame_end = frame_end
            shot.assigned_to = users_by_email[assignee_email].id

        await session.commit()

        refreshed = await session.execute(
            select(Shot).where(Shot.project_id == project.id).order_by(Shot.code)
        )
        return list(refreshed.scalars().all())


async def _ensure_demo_assets(project: Project, users_by_email: dict[str, User]) -> list[Asset]:
    demo_assets: tuple[tuple[str, str, AssetType, str, AssetStatus], ...] = (
        (
            "Hero Character",
            "AST-CHR-001",
            AssetType.character,
            "lead@vfxhub.dev",
            AssetStatus.in_progress,
        ),
        (
            "Main Environment",
            "AST-ENV-001",
            AssetType.environment,
            "artist@vfxhub.dev",
            AssetStatus.review,
        ),
        (
            "Explosion FX",
            "AST-FX-001",
            AssetType.fx,
            "worker@vfxhub.dev",
            AssetStatus.pending,
        ),
    )

    assignees = {
        email: user.id
        for email, user in users_by_email.items()
        if email in {"lead@vfxhub.dev", "artist@vfxhub.dev", "worker@vfxhub.dev"}
    }

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Asset).where(Asset.project_id == project.id))
        existing_assets = result.scalars().all()
        existing_by_name = {asset.name: asset for asset in existing_assets}
        existing_by_code = {
            asset.code: asset for asset in existing_assets if asset.code is not None
        }

        for asset_name, asset_code, asset_type, assignee_email, status in demo_assets:
            asset = existing_by_code.get(asset_code) or existing_by_name.get(asset_name)
            if asset is None:
                asset = Asset(project_id=project.id, name=asset_name, asset_type=asset_type)
                session.add(asset)

            asset.name = asset_name
            asset.code = asset_code
            asset.asset_type = asset_type
            asset.status = status
            asset.assigned_to = assignees.get(assignee_email)

        await session.commit()

        refreshed = await session.execute(
            select(Asset).where(Asset.project_id == project.id).order_by(Asset.name)
        )
        return list(refreshed.scalars().all())


async def run_seed() -> None:
    config = _get_seed_config()

    roles = await _ensure_roles()
    admin_user = await _ensure_admin_user(config)
    users_by_email = await _ensure_demo_users(config)
    await _ensure_admin_role_assignment(admin_user, roles[RoleName.admin])
    demo_project = await _ensure_demo_project(config, admin_user)
    created_project_assignments = await _ensure_demo_project_role_assignments(
        demo_project, roles, users_by_email
    )
    episodes_by_code = await _ensure_demo_episodes(demo_project)
    sequences_by_code = await _ensure_demo_sequences(demo_project, episodes_by_code)
    shots = await _ensure_demo_shots(demo_project, sequences_by_code, users_by_email)
    assets = await _ensure_demo_assets(demo_project, users_by_email)

    print("Seed complete")
    print(f"Admin email: {config.admin_email}")
    print(f"Demo user password: {config.demo_user_password}")
    print(f"Demo users ensured: {len(users_by_email)}")
    print("Roles ensured:", ", ".join(sorted(role.value for role in roles)))
    print(f"Project ensured: {demo_project.code} ({demo_project.name})")
    print(f"Project role assignments created: {created_project_assignments}")
    print(f"Episodes ensured: {len(episodes_by_code)}")
    print(f"Sequences ensured: {len(sequences_by_code)}")
    print(f"Shots ensured: {len(shots)}")
    print(f"Assets ensured: {len(assets)}")
    await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_seed())
