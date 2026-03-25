from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class LoginRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=255,
        description="User email used for authentication.",
        examples=["admin@vfxhub.dev"],
    )
    password: str = Field(
        min_length=1,
        max_length=255,
        description="Plain text password validated against the stored hash.",
        examples=["admin123"],
    )

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "admin@vfxhub.dev", "password": "admin123"}}
    )


class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        min_length=1,
        description="JWT refresh token returned by /auth/login.",
    )


class LogoutRequest(BaseModel):
    refresh_token: str = Field(
        min_length=1,
        description="Refresh token to invalidate in Redis blacklist.",
    )


class LogoutResponse(BaseModel):
    message: str = "Logged out"

    model_config = ConfigDict(json_schema_extra={"example": {"message": "Logged out"}})


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    access_token_expires_in: int = settings.access_token_expire_min * 60

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "<jwt-access-token>",
                "token_type": "bearer",
                "access_token_expires_in": 1800,
            }
        }
    )


class UserRoleResponse(BaseModel):
    name: str
    project_id: str | None = None


class MeResponse(BaseModel):
    id: str
    email: str
    is_active: bool
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    department: str | None = None
    timezone: str | None = None
    phone: str | None = None
    roles: list[UserRoleResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "admin@vfxhub.dev",
                "is_active": True,
                "roles": [{"name": "admin", "project_id": None}],
            }
        }
    )


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_expires_in: int = settings.access_token_expire_min * 60
    refresh_token_expires_in: int = settings.refresh_token_expire_days * 24 * 60 * 60

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "<jwt-access-token>",
                "refresh_token": "<jwt-refresh-token>",
                "token_type": "bearer",
                "access_token_expires_in": 1800,
                "refresh_token_expires_in": 604800,
            }
        }
    )
