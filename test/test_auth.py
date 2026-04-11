from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, hash_password
from app.core.token_blacklist import get_redis_client
from app.models.project import Project, ProjectStatus
from app.models.role import Role, RoleName
from app.models.user import User
from app.models.user_role import UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user(
    db_session: AsyncSession,
    email: str,
    password: str,
    *,
    is_active: bool = True,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        is_active=is_active,
        first_name=first_name,
        last_name=last_name,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client: AsyncClient, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_returns_access_and_refresh_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, "admin@vfxhub.dev", "admin123")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vfxhub.dev", "password": "admin123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token_expires_in"] == 1800
    assert payload["refresh_token_expires_in"] == 604800

    access_claims = decode_token(payload["access_token"])
    refresh_claims = decode_token(payload["refresh_token"])
    assert access_claims["typ"] == "access"
    assert refresh_claims["typ"] == "refresh"


@pytest.mark.asyncio
async def test_login_token_sub_matches_user_id(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "artist@vfxhub.dev", "pass123")

    tokens = await _login(client, "artist@vfxhub.dev", "pass123")

    access_claims = decode_token(tokens["access_token"])
    refresh_claims = decode_token(tokens["refresh_token"])
    assert access_claims["sub"] == str(user.id)
    assert refresh_claims["sub"] == str(user.id)


@pytest.mark.asyncio
async def test_login_invalid_credentials_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, "admin@vfxhub.dev", "admin123")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vfxhub.dev", "password": "wrongpass"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Invalid credentials",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_login_nonexistent_email_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@vfxhub.dev", "password": "admin123"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Invalid credentials",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, "inactive@vfxhub.dev", "admin123", is_active=False)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@vfxhub.dev", "password": "admin123"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.json()["error"]["message"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_validation_missing_password_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vfxhub.dev"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    errors = payload["error"]["detail"]["errors"]
    assert any(e.get("loc") == ["body", "password"] for e in errors)


@pytest.mark.asyncio
async def test_login_validation_missing_email_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"password": "admin123"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    errors = payload["error"]["detail"]["errors"]
    assert any(e.get("loc") == ["body", "email"] for e in errors)


@pytest.mark.asyncio
async def test_login_validation_error_uses_consistent_error_format(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "ab"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"] == "Validation error"
    assert isinstance(payload["error"]["detail"], dict)
    assert "errors" in payload["error"]["detail"]

    errors = payload["error"]["detail"]["errors"]
    assert isinstance(errors, list)
    assert any(error.get("loc") == ["body", "password"] for error in errors)


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_returns_new_access_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, "admin@vfxhub.dev", "admin123")

    tokens = await _login(client, "admin@vfxhub.dev", "admin123")

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert refresh_response.status_code == 200
    payload = refresh_response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token_expires_in"] == 1800
    assert "access_token" in payload
    assert "refresh_token" not in payload


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, "admin@vfxhub.dev", "admin123")

    tokens = await _login(client, "admin@vfxhub.dev", "admin123")

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )

    assert refresh_response.status_code == 401
    assert refresh_response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Invalid refresh token",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_refresh_with_invalid_token_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not.a.valid.jwt"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_refresh_inactive_user_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "soon-inactive@vfxhub.dev", "admin123")
    tokens = await _login(client, "soon-inactive@vfxhub.dev", "admin123")

    # Deactivate the user after obtaining a valid refresh token.
    await db_session.execute(
        text("UPDATE users SET is_active = false WHERE id = :uid"),
        {"uid": str(user.id)},
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_refresh_deleted_user_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "temp@vfxhub.dev", "admin123")
    tokens = await _login(client, "temp@vfxhub.dev", "admin123")

    await db_session.execute(
        text("DELETE FROM users WHERE id = :uid"),
        {"uid": str(user.id)},
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_blacklists_refresh_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, "admin@vfxhub.dev", "admin123")
    tokens = await _login(client, "admin@vfxhub.dev", "admin123")
    refresh_token = tokens["refresh_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert logout_response.status_code == 200
    assert logout_response.json() == {"message": "Logged out"}

    redis_client = get_redis_client()
    try:
        blacklist_key = f"auth:blacklist:{refresh_token}"
        assert await redis_client.exists(blacklist_key) == 1
        assert await redis_client.ttl(blacklist_key) > 0
    finally:
        await redis_client.aclose()

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 401
    assert refresh_response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Refresh token revoked",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_logout_with_access_token_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, "admin@vfxhub.dev", "admin123")
    tokens = await _login(client, "admin@vfxhub.dev", "admin123")

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["access_token"]},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_logout_with_invalid_token_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "garbage.token.value"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Authentication required",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_me_with_invalid_bearer_token_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.real.token"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_me_returns_user_info_and_roles(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "admin@vfxhub.dev", "admin123")

    admin_role = Role(name=RoleName.admin, description="Administrator")
    db_session.add(admin_role)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=admin_role.id, project_id=None))
    await db_session.commit()

    tokens = await _login(client, "admin@vfxhub.dev", "admin123")

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(user.id)
    assert payload["email"] == "admin@vfxhub.dev"
    assert payload["is_active"] is True
    assert payload["roles"] == [{"name": "admin", "project_id": None}]


@pytest.mark.asyncio
async def test_me_returns_no_roles_for_new_user(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "noroles@vfxhub.dev", "pass123")
    tokens = await _login(client, "noroles@vfxhub.dev", "pass123")

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(user.id)
    assert payload["roles"] == []


@pytest.mark.asyncio
async def test_me_returns_multiple_roles_including_project_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "multi@vfxhub.dev", "pass123")

    project = Project(
        id=uuid.uuid4(),
        name="Test Film",
        code="TF001",
        status=ProjectStatus.in_progress,
    )
    db_session.add(project)

    admin_role = Role(name=RoleName.admin, description="Administrator")
    artist_role = Role(name=RoleName.artist, description="Artist")
    db_session.add_all([admin_role, artist_role])
    await db_session.flush()

    db_session.add(UserRole(user_id=user.id, role_id=admin_role.id, project_id=None))
    db_session.add(UserRole(user_id=user.id, role_id=artist_role.id, project_id=project.id))
    await db_session.commit()

    tokens = await _login(client, "multi@vfxhub.dev", "pass123")

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    roles = response.json()["roles"]
    assert len(roles) == 2
    role_names = {r["name"] for r in roles}
    assert role_names == {"admin", "artist"}
    project_scoped = next(r for r in roles if r["name"] == "artist")
    assert project_scoped["project_id"] == str(project.id)
    global_role = next(r for r in roles if r["name"] == "admin")
    assert global_role["project_id"] is None


@pytest.mark.asyncio
async def test_me_returns_user_profile_fields(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(
        db_session,
        "fullprofile@vfxhub.dev",
        "pass123",
        first_name="John",
        last_name="Doe",
    )
    tokens = await _login(client, "fullprofile@vfxhub.dev", "pass123")

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["first_name"] == "John"
    assert payload["last_name"] == "Doe"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429_after_five_failed_attempts(
    client: AsyncClient,
) -> None:
    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@vfxhub.dev", "password": "wrongpass"},
        )
        assert response.status_code == 401

    blocked_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@vfxhub.dev", "password": "wrongpass"},
    )
    assert blocked_response.status_code == 429
    assert blocked_response.json() == {
        "error": {
            "code": "TOO_MANY_REQUESTS",
            "message": "Too many login attempts. Try again in 15 minutes",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_login_success_clears_rate_limit(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, "admin@vfxhub.dev", "admin123")

    # 4 failed attempts — one short of the limit.
    for _ in range(4):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@vfxhub.dev", "password": "wrongpass"},
        )
        assert response.status_code == 401

    # A successful login should reset the counter.
    await _login(client, "admin@vfxhub.dev", "admin123")

    # One more failure should be allowed (counter is back to 1, not 5).
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vfxhub.dev", "password": "wrongpass"},
    )
    assert response.status_code == 401
