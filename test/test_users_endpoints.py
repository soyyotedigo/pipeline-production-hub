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

Role = models_module.Role
RoleName = models_module.RoleName
User = models_module.User
UserRole = models_module.UserRole

pytestmark = pytest.mark.users


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


# ---------------------------------------------------------------------------
# CREATE USER
# ---------------------------------------------------------------------------


class TestCreateUser:
    async def test_admin_creates_user_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.post(
            "/api/v1/users",
            json={"email": "newuser@example.com", "password": "pass1234"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@example.com"
        assert data["is_active"] is True
        assert "id" in data
        assert "hashed_password" not in data

    async def test_create_with_optional_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-full@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.post(
            "/api/v1/users",
            json={
                "email": "full@example.com",
                "password": "pass1234",
                "first_name": "Alice",
                "last_name": "Smith",
                "display_name": "alice",
                "timezone": "UTC",
            },
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["first_name"] == "Alice"
        assert data["last_name"] == "Smith"
        assert data["display_name"] == "alice"

    async def test_duplicate_email_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dup@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)

        await client.post(
            "/api/v1/users",
            json={"email": "dup@example.com", "password": "pass1234"},
            headers=headers,
        )
        resp = await client.post(
            "/api/v1/users",
            json={"email": "dup@example.com", "password": "pass1234"},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_non_admin_cannot_create_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        artist = await _create_user(db_session, "artist-create@usr.test")
        await _assign_role(db_session, artist.id, RoleName.artist)

        resp = await client.post(
            "/api/v1/users",
            json={"email": "blocked@example.com", "password": "pass1234"},
            headers=_auth_headers(artist),
        )

        assert resp.status_code == 403

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post(
            "/api/v1/users",
            json={"email": "noauth@example.com", "password": "pass1234"},
        )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# LIST USERS
# ---------------------------------------------------------------------------


class TestListUsers:
    async def test_supervisor_can_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        supervisor = await _create_user(db_session, "sup-list@usr.test")
        await _assign_role(db_session, supervisor.id, RoleName.supervisor)
        await _create_user(db_session, "user-a@usr.test")
        await _create_user(db_session, "user-b@usr.test")

        resp = await client.get("/api/v1/users", headers=_auth_headers(supervisor))

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3
        assert "items" in data

    async def test_artist_cannot_list_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        artist = await _create_user(db_session, "artist-list@usr.test")
        await _assign_role(db_session, artist.id, RoleName.artist)

        resp = await client.get("/api/v1/users", headers=_auth_headers(artist))

        assert resp.status_code == 403

    async def test_list_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        supervisor = await _create_user(db_session, "sup-page@usr.test")
        await _assign_role(db_session, supervisor.id, RoleName.supervisor)
        for i in range(3):
            await _create_user(db_session, f"pager{i}@usr.test")

        resp = await client.get("/api/v1/users?limit=2&offset=0", headers=_auth_headers(supervisor))

        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    async def test_filter_inactive_users(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        supervisor = await _create_user(db_session, "sup-filter@usr.test")
        await _assign_role(db_session, supervisor.id, RoleName.supervisor)

        resp = await client.get("/api/v1/users?is_active=false", headers=_auth_headers(supervisor))

        assert resp.status_code == 200

    async def test_list_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.get("/api/v1/users")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET USER
# ---------------------------------------------------------------------------


class TestGetUser:
    async def test_get_own_profile_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "self-get@usr.test")

        resp = await client.get(f"/api/v1/users/{user.id}", headers=_auth_headers(user))

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(user.id)
        assert data["email"] == "self-get@usr.test"

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "admin-get404@usr.test")
        await _assign_role(db_session, user.id, RoleName.admin)

        resp = await client.get(f"/api/v1/users/{uuid.uuid4()}", headers=_auth_headers(user))

        assert resp.status_code == 404

    async def test_get_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "noauth-get@usr.test")

        resp = await client.get(f"/api/v1/users/{user.id}")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# UPDATE USER
# ---------------------------------------------------------------------------


class TestUpdateUser:
    async def test_update_own_profile(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "self-upd@usr.test")

        resp = await client.patch(
            f"/api/v1/users/{user.id}",
            json={"first_name": "Updated", "last_name": "Name"},
            headers=_auth_headers(user),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Name"

    async def test_admin_can_update_any_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@usr.test")
        other = await _create_user(db_session, "other-upd@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.patch(
            f"/api/v1/users/{other.id}",
            json={"display_name": "admin-set"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 200
        assert resp.json()["display_name"] == "admin-set"

    async def test_cross_user_update_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user_a = await _create_user(db_session, "usera-upd@usr.test")
        user_b = await _create_user(db_session, "userb-upd@usr.test")

        resp = await client.patch(
            f"/api/v1/users/{user_b.id}",
            json={"first_name": "Hacked"},
            headers=_auth_headers(user_a),
        )

        assert resp.status_code == 403

    async def test_update_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd404@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.patch(
            f"/api/v1/users/{uuid.uuid4()}",
            json={"first_name": "Ghost"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DEACTIVATE USER
# ---------------------------------------------------------------------------


class TestDeactivateUser:
    async def test_admin_deactivates_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-deact@usr.test")
        target = await _create_user(db_session, "target-deact@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.post(
            f"/api/v1/users/{target.id}/deactivate",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_non_admin_cannot_deactivate_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        artist = await _create_user(db_session, "artist-deact@usr.test")
        target = await _create_user(db_session, "target2-deact@usr.test")
        await _assign_role(db_session, artist.id, RoleName.artist)

        resp = await client.post(
            f"/api/v1/users/{target.id}/deactivate",
            headers=_auth_headers(artist),
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# USER ROLES
# ---------------------------------------------------------------------------


class TestUserRoles:
    async def test_assign_global_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-roles@usr.test")
        target = await _create_user(db_session, "target-roles@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        # Ensure artist role exists in DB before API can assign it
        await _ensure_role(db_session, RoleName.artist)

        resp = await client.post(
            f"/api/v1/users/{target.id}/roles",
            json={"role_name": "artist"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["role_name"] == "artist"
        assert data["project_id"] is None

    async def test_list_user_roles(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-listroles@usr.test")
        target = await _create_user(db_session, "target-listroles@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        await _assign_role(db_session, target.id, RoleName.artist)

        resp = await client.get(
            f"/api/v1/users/{target.id}/roles",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_remove_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-rmrole@usr.test")
        target = await _create_user(db_session, "target-rmrole@usr.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        await _assign_role(db_session, target.id, RoleName.artist)

        resp = await client.delete(
            f"/api/v1/users/{target.id}/roles/artist",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 204
