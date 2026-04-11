from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, engine
from app.models import (
    Asset,
    AssetStatus,
    AssetType,
    Delivery,
    DeliveryItem,
    DeliveryStatus,
    EntityTag,
    Episode,
    EpisodeStatus,
    Note,
    NoteEntityType,
    PipelineStepType,
    PipelineTask,
    PipelineTaskStatus,
    Playlist,
    PlaylistItem,
    PlaylistStatus,
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
    Tag,
    TagEntityType,
    TimeLog,
    User,
    UserRole,
    Version,
    VersionStatus,
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


async def _ensure_roles(session: AsyncSession) -> dict[RoleName, Role]:
    descriptions: dict[RoleName, str] = {
        RoleName.admin: "Global administrator",
        RoleName.supervisor: "Supervises production",
        RoleName.lead: "Leads a team or project",
        RoleName.artist: "Artist role",
        RoleName.worker: "General worker role",
        RoleName.client: "Client role for project visibility",
    }

    result = await session.execute(select(Role))
    existing_roles = {role.name: role for role in result.scalars().all()}

    created_count = 0
    for role_name, description in descriptions.items():
        if role_name in existing_roles:
            continue
        session.add(Role(name=role_name, description=description))
        created_count += 1

    if created_count > 0:
        await session.flush()

    result = await session.execute(select(Role))
    return {role.name: role for role in result.scalars().all()}


async def _ensure_admin_user(session: AsyncSession, config: SeedConfig) -> User:
    result = await session.execute(select(User).where(User.email == config.admin_email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=config.admin_email,
            hashed_password=hash_password(config.admin_password),
            is_active=True,
            first_name="Admin",
            last_name="User",
            display_name="Admin",
            department="Administration",
            timezone="UTC",
        )
        session.add(user)
        await session.flush()
    else:
        user.first_name = user.first_name or "Admin"
        user.last_name = user.last_name or "User"
        user.display_name = user.display_name or "Admin"
        user.department = user.department or "Administration"
        user.timezone = user.timezone or "UTC"

    return user


async def _ensure_admin_role_assignment(
    session: AsyncSession, admin_user: User, admin_role: Role
) -> None:
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
    await session.flush()


async def _ensure_demo_project(
    session: AsyncSession, config: SeedConfig, admin_user: User
) -> Project:
    result = await session.execute(select(Project).where(Project.code == config.demo_project_code))
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

    await session.flush()
    return project


async def _ensure_demo_users(session: AsyncSession, config: SeedConfig) -> dict[str, User]:
    demo_users: tuple[tuple[str, str, str, str, str, str], ...] = (
        ("supervisor@vfxhub.dev", "Sofia", "Stone", "Sofia Stone", "Production", "UTC"),
        ("lead@vfxhub.dev", "Leo", "Kim", "Leo Kim", "Lighting", "UTC"),
        ("artist@vfxhub.dev", "Aria", "Lopez", "Aria Lopez", "Compositing", "UTC"),
        ("worker@vfxhub.dev", "Will", "Park", "Will Park", "Matchmove", "UTC"),
        ("client@vfxhub.dev", "Clara", "Reed", "Clara Reed", "Client", "UTC"),
    )

    emails = [email for email, *_ in demo_users]

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

    await session.flush()

    refreshed = await session.execute(select(User).where(User.email.in_(emails)))
    return {user.email: user for user in refreshed.scalars().all()}


async def _ensure_demo_project_role_assignments(
    session: AsyncSession,
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

    result = await session.execute(
        select(UserRole).where(
            and_(
                UserRole.project_id == project.id,
                UserRole.user_id.in_(user_ids),
            )
        )
    )
    existing = {(assignment.user_id, assignment.role_id) for assignment in result.scalars().all()}

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
        await session.flush()

    return created_count


async def _ensure_demo_episodes(session: AsyncSession, project: Project) -> dict[str, Episode]:
    demo_episodes: tuple[tuple[str, str, int, int], ...] = (
        ("E01", "Pilot", 101, 1),
        ("E02", "Arrival", 102, 2),
    )

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

    await session.flush()

    refreshed = await session.execute(
        select(Episode).where(Episode.project_id == project.id).order_by(Episode.code)
    )
    return {episode.code: episode for episode in refreshed.scalars().all()}


async def _ensure_demo_sequences(
    session: AsyncSession,
    project: Project,
    episodes_by_code: dict[str, Episode],
) -> dict[str, Sequence]:
    demo_sequences: tuple[tuple[str, str, str, int, int], ...] = (
        ("SQ010", "City Intro", "E01", 1001, 1),
        ("SQ020", "Hangar Conflict", "E01", 1002, 2),
        ("SQ030", "Escape Run", "E02", 2001, 1),
    )

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

    await session.flush()

    refreshed = await session.execute(
        select(Sequence).where(Sequence.project_id == project.id).order_by(Sequence.code)
    )
    return {sequence.code: sequence for sequence in refreshed.scalars().all()}


async def _ensure_demo_shots(
    session: AsyncSession,
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

    await session.flush()

    refreshed = await session.execute(
        select(Shot).where(Shot.project_id == project.id).order_by(Shot.code)
    )
    return list(refreshed.scalars().all())


async def _ensure_demo_assets(
    session: AsyncSession, project: Project, users_by_email: dict[str, User]
) -> list[Asset]:
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

    result = await session.execute(select(Asset).where(Asset.project_id == project.id))
    existing_assets = result.scalars().all()
    existing_by_name = {asset.name: asset for asset in existing_assets}
    existing_by_code = {asset.code: asset for asset in existing_assets if asset.code is not None}

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

    await session.flush()

    refreshed = await session.execute(
        select(Asset).where(Asset.project_id == project.id).order_by(Asset.name)
    )
    return list(refreshed.scalars().all())


# ── Generic helpers for extra projects ────────────────────────────────────────


async def _ensure_extra_projects(
    session: AsyncSession,
    admin_user: User,
) -> list[Project]:
    specs = [
        ("Alpha VFX Film", "ALPHA", ProjectType.film, "Alpha Studios", "High-action feature film"),
        (
            "Beta Commercial",
            "BETA",
            ProjectType.commercial,
            "Beta Corp",
            "Product launch commercial",
        ),
    ]
    projects: list[Project] = []
    for name, code, ptype, client, desc in specs:
        result = await session.execute(select(Project).where(Project.code == code))
        project = result.scalar_one_or_none()
        if project is None:
            project = Project(
                name=name,
                code=code,
                project_type=ptype,
                client=client,
                status=ProjectStatus.in_progress,
                description=desc,
                created_by=admin_user.id,
            )
            session.add(project)
        else:
            project.name = name
            project.client = client
            project.status = ProjectStatus.in_progress
        projects.append(project)
    await session.flush()
    return projects


async def _ensure_sequences(
    session: AsyncSession,
    project: Project,
    seq_data: tuple[tuple[str, str, str | None, int, int], ...],
    episodes_by_code: dict[str, Episode] | None = None,
) -> dict[str, Sequence]:
    result = await session.execute(select(Sequence).where(Sequence.project_id == project.id))
    existing_by_code = {s.code: s for s in result.scalars().all()}

    for code, name, episode_code, production_number, order in seq_data:
        seq = existing_by_code.get(code)
        if seq is None:
            seq = Sequence(project_id=project.id, code=code, name=name)
            session.add(seq)
        seq.name = name
        if episode_code and episodes_by_code:
            seq.episode_id = episodes_by_code[episode_code].id
        seq.scope_type = SequenceScopeType.sequence
        seq.status = SequenceStatus.in_progress
        seq.production_number = production_number
        seq.order = order

    await session.flush()

    refreshed = await session.execute(
        select(Sequence).where(Sequence.project_id == project.id).order_by(Sequence.code)
    )
    return {s.code: s for s in refreshed.scalars().all()}


async def _ensure_shots(
    session: AsyncSession,
    project: Project,
    shot_data: tuple[tuple[str, str, str, int, int, str, ShotStatus], ...],
    sequences_by_code: dict[str, Sequence],
    users_by_email: dict[str, User],
) -> list[Shot]:
    result = await session.execute(select(Shot).where(Shot.project_id == project.id))
    existing_by_code = {s.code: s for s in result.scalars().all()}

    for shot_code, shot_name, seq_code, frame_start, frame_end, assignee_email, status in shot_data:
        shot = existing_by_code.get(shot_code)
        if shot is None:
            shot = Shot(project_id=project.id, code=shot_code, name=shot_name)
            session.add(shot)
        shot.name = shot_name
        shot.status = status
        shot.sequence_id = sequences_by_code[seq_code].id
        shot.frame_start = frame_start
        shot.frame_end = frame_end
        shot.assigned_to = users_by_email[assignee_email].id

    await session.flush()

    refreshed = await session.execute(
        select(Shot).where(Shot.project_id == project.id).order_by(Shot.code)
    )
    return list(refreshed.scalars().all())


async def _ensure_assets(
    session: AsyncSession,
    project: Project,
    asset_data: tuple[tuple[str, str, AssetType, str, AssetStatus], ...],
    users_by_email: dict[str, User],
) -> list[Asset]:
    result = await session.execute(select(Asset).where(Asset.project_id == project.id))
    existing_assets = result.scalars().all()
    existing_by_name = {a.name: a for a in existing_assets}
    existing_by_code = {a.code: a for a in existing_assets if a.code is not None}

    for asset_name, asset_code, asset_type, assignee_email, status in asset_data:
        asset = existing_by_code.get(asset_code) or existing_by_name.get(asset_name)
        if asset is None:
            asset = Asset(project_id=project.id, name=asset_name, asset_type=asset_type)
            session.add(asset)
        asset.name = asset_name
        asset.code = asset_code
        asset.asset_type = asset_type
        asset.status = status
        asset.assigned_to = (
            users_by_email[assignee_email].id if assignee_email in users_by_email else None
        )

    await session.flush()

    refreshed = await session.execute(
        select(Asset).where(Asset.project_id == project.id).order_by(Asset.name)
    )
    return list(refreshed.scalars().all())


# ── New entity seeders ────────────────────────────────────────────────────────


async def _ensure_pipeline_tasks(
    session: AsyncSession,
    shots: list[Shot],
    assets: list[Asset],
    users_by_email: dict[str, User],
) -> list[PipelineTask]:
    shot_steps = [
        (PipelineStepType.layout, "Layout", 1, PipelineTaskStatus.approved, "worker@vfxhub.dev"),
        (
            PipelineStepType.lighting,
            "Lighting",
            2,
            PipelineTaskStatus.in_progress,
            "lead@vfxhub.dev",
        ),
        (
            PipelineStepType.compositing,
            "Compositing",
            3,
            PipelineTaskStatus.pending,
            "artist@vfxhub.dev",
        ),
    ]
    asset_steps = [
        (
            PipelineStepType.modeling,
            "Modeling",
            1,
            PipelineTaskStatus.in_progress,
            "lead@vfxhub.dev",
        ),
        (PipelineStepType.shading, "Shading", 2, PipelineTaskStatus.pending, "artist@vfxhub.dev"),
    ]

    shot_ids = [s.id for s in shots]
    asset_ids = [a.id for a in assets]
    existing_shot_tasks: dict[tuple[uuid.UUID | None, PipelineStepType], PipelineTask] = {}
    existing_asset_tasks: dict[tuple[uuid.UUID | None, PipelineStepType], PipelineTask] = {}

    if shot_ids:
        res = await session.execute(select(PipelineTask).where(PipelineTask.shot_id.in_(shot_ids)))
        for t in res.scalars().all():
            existing_shot_tasks[(t.shot_id, t.step_type)] = t

    if asset_ids:
        res = await session.execute(
            select(PipelineTask).where(PipelineTask.asset_id.in_(asset_ids))
        )
        for t in res.scalars().all():
            existing_asset_tasks[(t.asset_id, t.step_type)] = t

    for shot in shots:
        for step_type, step_name, order, status, assignee_email in shot_steps:
            if (shot.id, step_type) in existing_shot_tasks:
                continue
            session.add(
                PipelineTask(
                    shot_id=shot.id,
                    asset_id=None,
                    step_name=step_name,
                    step_type=step_type,
                    order=order,
                    status=status,
                    assigned_to=users_by_email[assignee_email].id,
                )
            )

    for asset in assets:
        for step_type, step_name, order, status, assignee_email in asset_steps:
            if (asset.id, step_type) in existing_asset_tasks:
                continue
            session.add(
                PipelineTask(
                    shot_id=None,
                    asset_id=asset.id,
                    step_name=step_name,
                    step_type=step_type,
                    order=order,
                    status=status,
                    assigned_to=users_by_email[assignee_email].id,
                )
            )

    await session.flush()

    all_tasks: list[PipelineTask] = []
    if shot_ids:
        res = await session.execute(select(PipelineTask).where(PipelineTask.shot_id.in_(shot_ids)))
        all_tasks.extend(res.scalars().all())
    if asset_ids:
        res = await session.execute(
            select(PipelineTask).where(PipelineTask.asset_id.in_(asset_ids))
        )
        all_tasks.extend(res.scalars().all())
    return all_tasks


async def _ensure_versions(
    session: AsyncSession,
    project: Project,
    shots: list[Shot],
    tasks_by_shot: dict[uuid.UUID, list[PipelineTask]],
    users_by_email: dict[str, User],
) -> list[Version]:
    result = await session.execute(
        select(Version).where(
            Version.project_id == project.id,
            Version.shot_id.isnot(None),
        )
    )
    existing: dict[tuple[uuid.UUID | None, int], Version] = {
        (v.shot_id, v.version_number): v for v in result.scalars().all()
    }

    submitters = [
        u
        for u in [
            users_by_email.get("artist@vfxhub.dev"),
            users_by_email.get("lead@vfxhub.dev"),
            users_by_email.get("worker@vfxhub.dev"),
        ]
        if u is not None
    ]

    for i, shot in enumerate(shots):
        shot_tasks = tasks_by_shot.get(shot.id, [])
        comp_task = next(
            (t for t in shot_tasks if t.step_type == PipelineStepType.compositing), None
        )
        submitter = submitters[i % len(submitters)]
        for vnum in (1, 2):
            if (shot.id, vnum) in existing:
                continue
            status = VersionStatus.approved if vnum == 1 else VersionStatus.pending_review
            session.add(
                Version(
                    project_id=project.id,
                    shot_id=shot.id,
                    asset_id=None,
                    pipeline_task_id=comp_task.id if comp_task else None,
                    code=f"{shot.code}_v{vnum:03d}",
                    version_number=vnum,
                    status=status,
                    description=f"Version {vnum} of {shot.name}",
                    submitted_by=submitter.id,
                )
            )

    await session.flush()

    refreshed = await session.execute(
        select(Version).where(
            Version.project_id == project.id,
            Version.shot_id.isnot(None),
        )
    )
    return list(refreshed.scalars().all())


async def _ensure_notes(
    session: AsyncSession,
    project: Project,
    shots: list[Shot],
    assets: list[Asset],
    users_by_email: dict[str, User],
) -> int:
    supervisor = users_by_email.get("supervisor@vfxhub.dev")
    lead = users_by_email.get("lead@vfxhub.dev")
    if not supervisor or not lead:
        return 0

    result = await session.execute(select(Note).where(Note.project_id == project.id))
    existing: set[tuple[NoteEntityType, uuid.UUID, uuid.UUID]] = {
        (n.entity_type, n.entity_id, n.author_id) for n in result.scalars().all()
    }

    created = 0
    for shot in shots:
        key = (NoteEntityType.shot, shot.id, supervisor.id)
        if key not in existing:
            session.add(
                Note(
                    project_id=project.id,
                    entity_type=NoteEntityType.shot,
                    entity_id=shot.id,
                    author_id=supervisor.id,
                    subject="Review feedback",
                    body=f"Please check the framing on {shot.name}. Looks slightly off.",
                    is_client_visible=False,
                )
            )
            created += 1

    for asset in assets:
        key = (NoteEntityType.asset, asset.id, lead.id)
        if key not in existing:
            session.add(
                Note(
                    project_id=project.id,
                    entity_type=NoteEntityType.asset,
                    entity_id=asset.id,
                    author_id=lead.id,
                    subject="Asset notes",
                    body=f"Good progress on {asset.name}. Minor surface detail pass needed.",
                    is_client_visible=False,
                )
            )
            created += 1

    if created > 0:
        await session.flush()
    return created


async def _ensure_time_logs(
    session: AsyncSession,
    project: Project,
    tasks: list[PipelineTask],
    users_by_email: dict[str, User],
) -> int:
    today = date.today()
    cycle = [
        users_by_email.get("worker@vfxhub.dev"),
        users_by_email.get("artist@vfxhub.dev"),
        users_by_email.get("lead@vfxhub.dev"),
    ]

    result = await session.execute(select(TimeLog).where(TimeLog.project_id == project.id))
    existing: set[tuple[uuid.UUID, uuid.UUID | None, str]] = {
        (tl.user_id, tl.pipeline_task_id, str(tl.date)) for tl in result.scalars().all()
    }

    created = 0
    for i, task in enumerate(tasks[:6]):
        user = cycle[i % 3]
        if user is None:
            continue
        log_date = today - timedelta(days=i)
        key = (user.id, task.id, str(log_date))
        if key in existing:
            continue
        session.add(
            TimeLog(
                project_id=project.id,
                pipeline_task_id=task.id,
                user_id=user.id,
                date=log_date,
                duration_minutes=240 + (i * 30),
                description=f"Work session on {task.step_name}",
            )
        )
        created += 1

    if created > 0:
        await session.flush()
    return created


async def _ensure_tags(
    session: AsyncSession,
    project: Project,
    shots: list[Shot],
) -> int:
    tag_defs = [
        ("priority", "#FF4444"),
        ("wip", "#FFA500"),
        ("approved", "#44BB44"),
    ]

    result = await session.execute(select(Tag).where(Tag.project_id == project.id))
    existing_tags = {t.name: t for t in result.scalars().all()}
    new_tags_count = 0
    for name, color in tag_defs:
        if name not in existing_tags:
            session.add(Tag(project_id=project.id, name=name, color=color))
            new_tags_count += 1

    if new_tags_count > 0:
        await session.flush()

    result = await session.execute(select(Tag).where(Tag.project_id == project.id))
    tags_by_name = {t.name: t for t in result.scalars().all()}

    entity_tag_pairs: list[tuple[Tag, TagEntityType, uuid.UUID]] = []
    if shots and "wip" in tags_by_name:
        entity_tag_pairs.append((tags_by_name["wip"], TagEntityType.shot, shots[0].id))
    if shots and "priority" in tags_by_name:
        entity_tag_pairs.append((tags_by_name["priority"], TagEntityType.shot, shots[0].id))
    if len(shots) > 1 and "approved" in tags_by_name:
        entity_tag_pairs.append((tags_by_name["approved"], TagEntityType.shot, shots[1].id))

    tag_ids = [t.id for t in tags_by_name.values()]
    existing_et: set[tuple[uuid.UUID, str, str]] = set()
    if tag_ids:
        res = await session.execute(select(EntityTag).where(EntityTag.tag_id.in_(tag_ids)))
        existing_et = {
            (et.tag_id, et.entity_type.value, str(et.entity_id)) for et in res.scalars().all()
        }

    et_created = 0
    for tag, entity_type, entity_id in entity_tag_pairs:
        key = (tag.id, entity_type.value, str(entity_id))
        if key in existing_et:
            continue
        session.add(EntityTag(tag_id=tag.id, entity_type=entity_type, entity_id=entity_id))
        et_created += 1

    if et_created > 0:
        await session.flush()
    return new_tags_count + et_created


async def _ensure_delivery(
    session: AsyncSession,
    project: Project,
    versions: list[Version],
    admin_user: User,
) -> int:
    delivery_name = f"{project.code} - Initial Delivery"
    result = await session.execute(
        select(Delivery).where(
            Delivery.project_id == project.id,
            Delivery.name == delivery_name,
        )
    )
    delivery = result.scalar_one_or_none()

    if delivery is None:
        delivery = Delivery(
            project_id=project.id,
            name=delivery_name,
            delivery_date=date.today() + timedelta(days=14),
            recipient="Client Review Team",
            notes="First batch for internal review.",
            status=DeliveryStatus.preparing,
            created_by=admin_user.id,
        )
        session.add(delivery)
        await session.flush()

    # Link versions as delivery items
    items_result = await session.execute(
        select(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id)
    )
    existing_version_ids = {item.version_id for item in items_result.scalars().all()}

    created = 0
    for version in versions[:3]:
        if version.id in existing_version_ids:
            continue
        session.add(
            DeliveryItem(
                delivery_id=delivery.id,
                version_id=version.id,
                shot_id=version.shot_id,
            )
        )
        created += 1

    if created > 0:
        await session.flush()
    return created


async def _ensure_playlist(
    session: AsyncSession,
    project: Project,
    versions: list[Version],
    admin_user: User,
) -> int:
    playlist_name = f"{project.code} - Daily Review"
    result = await session.execute(
        select(Playlist).where(
            Playlist.project_id == project.id,
            Playlist.name == playlist_name,
        )
    )
    playlist = result.scalar_one_or_none()

    if playlist is None:
        playlist = Playlist(
            project_id=project.id,
            name=playlist_name,
            description=f"Daily review playlist for {project.name}",
            created_by=admin_user.id,
            date=date.today(),
            status=PlaylistStatus.in_progress,
        )
        session.add(playlist)
        await session.flush()

    items_result = await session.execute(
        select(PlaylistItem).where(PlaylistItem.playlist_id == playlist.id)
    )
    existing_version_ids = {item.version_id for item in items_result.scalars().all()}

    created = 0
    for i, version in enumerate(versions[:5]):
        if version.id in existing_version_ids:
            continue
        session.add(
            PlaylistItem(
                playlist_id=playlist.id,
                version_id=version.id,
                order=i + 1,
            )
        )
        created += 1

    if created > 0:
        await session.flush()
    return created


# ── run_seed ──────────────────────────────────────────────────────────────────


async def run_seed() -> None:
    config = _get_seed_config()

    def _tasks_by_shot(tasks: list[PipelineTask]) -> dict[uuid.UUID, list[PipelineTask]]:
        m: dict[uuid.UUID, list[PipelineTask]] = {}
        for t in tasks:
            if t.shot_id:
                m.setdefault(t.shot_id, []).append(t)
        return m

    try:
        async with AsyncSessionLocal() as session:
            roles = await _ensure_roles(session)
            admin_user = await _ensure_admin_user(session, config)
            users_by_email = await _ensure_demo_users(session, config)
            await _ensure_admin_role_assignment(session, admin_user, roles[RoleName.admin])

            # ── DEMO project (series) ──────────────────────────────────────────
            demo_project = await _ensure_demo_project(session, config, admin_user)
            await _ensure_demo_project_role_assignments(
                session, demo_project, roles, users_by_email
            )
            demo_episodes = await _ensure_demo_episodes(session, demo_project)
            demo_sequences = await _ensure_demo_sequences(session, demo_project, demo_episodes)
            demo_shots = await _ensure_demo_shots(
                session, demo_project, demo_sequences, users_by_email
            )
            demo_assets = await _ensure_demo_assets(session, demo_project, users_by_email)

            # ── ALPHA project (film) ───────────────────────────────────────────
            alpha_project, beta_project = await _ensure_extra_projects(session, admin_user)
            await _ensure_demo_project_role_assignments(
                session, alpha_project, roles, users_by_email
            )
            alpha_sequences = await _ensure_sequences(
                session,
                alpha_project,
                (
                    ("SQ100", "Dawn Raid", None, 2001, 1),
                    ("SQ200", "Rooftop Chase", None, 2002, 2),
                ),
            )
            alpha_shots = await _ensure_shots(
                session,
                alpha_project,
                (
                    (
                        "SH100",
                        "Dawn Exterior",
                        "SQ100",
                        2001,
                        2090,
                        "artist@vfxhub.dev",
                        ShotStatus.in_progress,
                    ),
                    (
                        "SH110",
                        "Hero Entry",
                        "SQ100",
                        2091,
                        2180,
                        "lead@vfxhub.dev",
                        ShotStatus.review,
                    ),
                    (
                        "SH200",
                        "Rooftop Jump",
                        "SQ200",
                        2181,
                        2310,
                        "worker@vfxhub.dev",
                        ShotStatus.pending,
                    ),
                ),
                alpha_sequences,
                users_by_email,
            )
            alpha_assets = await _ensure_assets(
                session,
                alpha_project,
                (
                    (
                        "Protagonist",
                        "AST-CHR-100",
                        AssetType.character,
                        "lead@vfxhub.dev",
                        AssetStatus.in_progress,
                    ),
                    (
                        "Rooftop Set",
                        "AST-ENV-100",
                        AssetType.environment,
                        "artist@vfxhub.dev",
                        AssetStatus.review,
                    ),
                ),
                users_by_email,
            )

            # ── BETA project (commercial) ──────────────────────────────────────
            await _ensure_demo_project_role_assignments(
                session, beta_project, roles, users_by_email
            )
            beta_sequences = await _ensure_sequences(
                session,
                beta_project,
                (
                    ("SQ001", "Opening Sequence", None, 3001, 1),
                    ("SQ002", "Product Reveal", None, 3002, 2),
                ),
            )
            beta_shots = await _ensure_shots(
                session,
                beta_project,
                (
                    (
                        "SH001",
                        "Logo Sting",
                        "SQ001",
                        3001,
                        3060,
                        "artist@vfxhub.dev",
                        ShotStatus.in_progress,
                    ),
                    (
                        "SH002",
                        "Product Closeup",
                        "SQ002",
                        3061,
                        3130,
                        "worker@vfxhub.dev",
                        ShotStatus.review,
                    ),
                ),
                beta_sequences,
                users_by_email,
            )
            beta_assets = await _ensure_assets(
                session,
                beta_project,
                (
                    (
                        "Product Model",
                        "AST-PRD-001",
                        AssetType.prop,
                        "worker@vfxhub.dev",
                        AssetStatus.in_progress,
                    ),
                ),
                users_by_email,
            )

            # ── Pipeline tasks ─────────────────────────────────────────────────
            demo_tasks = await _ensure_pipeline_tasks(
                session, demo_shots, demo_assets, users_by_email
            )
            alpha_tasks = await _ensure_pipeline_tasks(
                session, alpha_shots, alpha_assets, users_by_email
            )
            beta_tasks = await _ensure_pipeline_tasks(
                session, beta_shots, beta_assets, users_by_email
            )

            # ── Versions ──────────────────────────────────────────────────────
            demo_versions = await _ensure_versions(
                session, demo_project, demo_shots, _tasks_by_shot(demo_tasks), users_by_email
            )
            alpha_versions = await _ensure_versions(
                session, alpha_project, alpha_shots, _tasks_by_shot(alpha_tasks), users_by_email
            )
            beta_versions = await _ensure_versions(
                session, beta_project, beta_shots, _tasks_by_shot(beta_tasks), users_by_email
            )

            # ── Notes ─────────────────────────────────────────────────────────
            await _ensure_notes(session, demo_project, demo_shots, demo_assets, users_by_email)
            await _ensure_notes(session, alpha_project, alpha_shots, alpha_assets, users_by_email)
            await _ensure_notes(session, beta_project, beta_shots, beta_assets, users_by_email)

            # ── Time logs ─────────────────────────────────────────────────────
            await _ensure_time_logs(session, demo_project, demo_tasks, users_by_email)
            await _ensure_time_logs(session, alpha_project, alpha_tasks, users_by_email)
            await _ensure_time_logs(session, beta_project, beta_tasks, users_by_email)

            # ── Tags ──────────────────────────────────────────────────────────
            await _ensure_tags(session, demo_project, demo_shots)
            await _ensure_tags(session, alpha_project, alpha_shots)
            await _ensure_tags(session, beta_project, beta_shots)

            # ── Deliveries ────────────────────────────────────────────────────
            await _ensure_delivery(session, demo_project, demo_versions, admin_user)
            await _ensure_delivery(session, alpha_project, alpha_versions, admin_user)
            await _ensure_delivery(session, beta_project, beta_versions, admin_user)

            # ── Playlists ─────────────────────────────────────────────────────
            await _ensure_playlist(session, demo_project, demo_versions, admin_user)
            await _ensure_playlist(session, alpha_project, alpha_versions, admin_user)
            await _ensure_playlist(session, beta_project, beta_versions, admin_user)

            await session.commit()

        print("Seed complete")
        print(f"Admin email: {config.admin_email}")
        print(f"Admin password: {config.admin_password}")
        print(f"Demo user password: {config.demo_user_password}")
        print(f"Demo users ensured: {len(users_by_email)}")
        print("Roles ensured:", ", ".join(sorted(role.value for role in roles)))
        print("Projects ensured: DEMO, ALPHA, BETA")
        print(
            f"  DEMO  — shots: {len(demo_shots)}, assets: {len(demo_assets)}, tasks: {len(demo_tasks)}, versions: {len(demo_versions)}"
        )
        print(
            f"  ALPHA — shots: {len(alpha_shots)}, assets: {len(alpha_assets)}, tasks: {len(alpha_tasks)}, versions: {len(alpha_versions)}"
        )
        print(
            f"  BETA  — shots: {len(beta_shots)}, assets: {len(beta_assets)}, tasks: {len(beta_tasks)}, versions: {len(beta_versions)}"
        )
    except Exception as exc:
        print(f"\nSeed failed: {type(exc).__name__}: {exc}", flush=True)
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_seed())
