from __future__ import annotations

import sys
import uuid
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

security_module = import_module("app.core.security")
models_module = import_module("app.models")

create_access_token = security_module.create_access_token
hash_password = security_module.hash_password

Notification = models_module.Notification
NotificationEventType = models_module.NotificationEventType
NotificationEntityType = models_module.NotificationEntityType
Role = models_module.Role
RoleName = models_module.RoleName
User = models_module.User
UserRole = models_module.UserRole

pytestmark = pytest.mark.notifications


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user(db_session: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _ensure_role(db_session: AsyncSession, role_name: RoleName) -> Role:
    result = await db_session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()
    if role is not None:
        return role
    role = Role(name=role_name, description=f"{role_name.value} role")
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    return role


async def _assign_role(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    role_name: RoleName,
    project_id: uuid.UUID | None = None,
) -> None:
    role = await _ensure_role(db_session, role_name)
    db_session.add(UserRole(user_id=user_id, role_id=role.id, project_id=project_id))
    await db_session.commit()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


async def _create_notification(
    db_session: AsyncSession,
    user: User,
    *,
    is_read: bool = False,
    event_type: NotificationEventType = NotificationEventType.task_assigned,
    entity_type: NotificationEntityType = NotificationEntityType.pipeline_task,
) -> Notification:
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=uuid.uuid4(),
        title="Test notification",
        is_read=is_read,
    )
    db_session.add(notif)
    await db_session.commit()
    await db_session.refresh(notif)
    return notif


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


class TestListNotifications:
    async def test_list_returns_200_with_own_notifications(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-list@notif.test")
        await _create_notification(db_session, user)
        await _create_notification(db_session, user)

        resp = await client.get("/notifications", headers=_auth_headers(user))

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_only_returns_own_notifications(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user_a = await _create_user(db_session, "usera-iso@notif.test")
        user_b = await _create_user(db_session, "userb-iso@notif.test")
        await _create_notification(db_session, user_a)
        await _create_notification(db_session, user_b)

        resp = await client.get("/notifications", headers=_auth_headers(user_a))

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_filter_by_is_read(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-filter@notif.test")
        await _create_notification(db_session, user, is_read=False)
        await _create_notification(db_session, user, is_read=True)

        resp = await client.get("/notifications?is_read=false", headers=_auth_headers(user))

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_list_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-page@notif.test")
        for _ in range(5):
            await _create_notification(db_session, user)

        resp = await client.get("/notifications?offset=0&limit=3", headers=_auth_headers(user))

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["total"] == 5

    async def test_list_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.get("/notifications")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# UNREAD COUNT
# ---------------------------------------------------------------------------


class TestUnreadCount:
    async def test_returns_unread_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-count@notif.test")
        await _create_notification(db_session, user, is_read=False)
        await _create_notification(db_session, user, is_read=False)
        await _create_notification(db_session, user, is_read=True)

        resp = await client.get("/notifications/unread-count", headers=_auth_headers(user))

        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    async def test_count_zero_when_none(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-zero@notif.test")

        resp = await client.get("/notifications/unread-count", headers=_auth_headers(user))

        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# MARK READ
# ---------------------------------------------------------------------------


class TestMarkNotificationRead:
    async def test_mark_single_as_read(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-mark@notif.test")
        notif = await _create_notification(db_session, user, is_read=False)

        resp = await client.patch(
            f"/notifications/{notif.id}/read",
            headers=_auth_headers(user),
        )

        assert resp.status_code == 200
        assert resp.json()["is_read"] is True
        assert resp.json()["read_at"] is not None

    async def test_mark_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-mark404@notif.test")

        resp = await client.patch(
            f"/notifications/{uuid.uuid4()}/read",
            headers=_auth_headers(user),
        )

        assert resp.status_code == 404

    async def test_cannot_mark_other_users_notification(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        owner = await _create_user(db_session, "owner-mark@notif.test")
        other = await _create_user(db_session, "other-mark@notif.test")
        notif = await _create_notification(db_session, owner)

        resp = await client.patch(
            f"/notifications/{notif.id}/read",
            headers=_auth_headers(other),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# MARK ALL READ
# ---------------------------------------------------------------------------


class TestMarkAllRead:
    async def test_mark_all_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-all@notif.test")
        await _create_notification(db_session, user, is_read=False)
        await _create_notification(db_session, user, is_read=False)

        resp = await client.post("/notifications/read-all", headers=_auth_headers(user))

        assert resp.status_code == 204

        count_resp = await client.get("/notifications/unread-count", headers=_auth_headers(user))
        assert count_resp.json()["count"] == 0

    async def test_mark_all_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post("/notifications/read-all")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteNotification:
    async def test_delete_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-del@notif.test")
        notif = await _create_notification(db_session, user)

        resp = await client.delete(
            f"/notifications/{notif.id}",
            headers=_auth_headers(user),
        )

        assert resp.status_code == 204

    async def test_delete_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-del404@notif.test")

        resp = await client.delete(
            f"/notifications/{uuid.uuid4()}",
            headers=_auth_headers(user),
        )

        assert resp.status_code == 404

    async def test_cannot_delete_other_users_notification(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        owner = await _create_user(db_session, "owner-del@notif.test")
        other = await _create_user(db_session, "other-del@notif.test")
        notif = await _create_notification(db_session, owner)

        resp = await client.delete(
            f"/notifications/{notif.id}",
            headers=_auth_headers(other),
        )

        assert resp.status_code == 404
