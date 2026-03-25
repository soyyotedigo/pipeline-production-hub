import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.core.token_blacklist import blacklist_token_until_exp, is_token_blacklisted
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AccessTokenResponse,
    LogoutResponse,
    MeResponse,
    TokenPairResponse,
    UserRoleResponse,
)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.user_repository = UserRepository(db)

    async def login(self, email: str, password: str) -> TokenPairResponse:
        user = await self.user_repository.get_by_email(email=email)
        if user is None or not user.is_active:
            raise UnauthorizedError("Invalid credentials")

        if not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Invalid credentials")

        user_id = str(uuid.UUID(str(user.id)))
        return TokenPairResponse(
            access_token=create_access_token(subject=user_id),
            refresh_token=create_refresh_token(subject=user_id),
        )

    async def refresh_access_token(self, refresh_token: str) -> AccessTokenResponse:
        if await is_token_blacklisted(refresh_token):
            raise UnauthorizedError("Refresh token revoked")

        payload = decode_token(refresh_token)
        token_type = payload.get("typ")
        if token_type != "refresh":
            raise UnauthorizedError("Invalid refresh token")

        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise UnauthorizedError("Invalid refresh token")

        try:
            user_id = uuid.UUID(subject)
        except ValueError as exc:
            raise UnauthorizedError("Invalid refresh token") from exc

        user = await self.user_repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Invalid refresh token")

        return AccessTokenResponse(access_token=create_access_token(subject=subject))

    async def logout(self, refresh_token: str) -> LogoutResponse:
        payload = decode_token(refresh_token)
        token_type = payload.get("typ")
        if token_type != "refresh":
            raise UnauthorizedError("Invalid refresh token")

        exp = payload.get("exp")
        if not isinstance(exp, int):
            raise UnauthorizedError("Invalid refresh token")

        await blacklist_token_until_exp(refresh_token, exp)
        return LogoutResponse()

    async def get_current_profile(self, user_id: uuid.UUID) -> MeResponse:
        user = await self.user_repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Invalid access token")

        role_rows = await self.user_repository.list_user_roles(user_id)
        roles = [
            UserRoleResponse(
                name=role_name,
                project_id=str(project_id) if project_id is not None else None,
            )
            for role_name, project_id in role_rows
        ]

        return MeResponse(
            id=str(user.id),
            email=user.email,
            is_active=user.is_active,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            department=user.department,
            timezone=user.timezone,
            phone=user.phone,
            roles=roles,
        )
