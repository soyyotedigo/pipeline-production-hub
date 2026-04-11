from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.exceptions import TooManyRequestsError, UnauthorizedError
from app.core.login_rate_limit import (
    clear_failed_login_attempts,
    is_login_rate_limited,
    record_failed_login_attempt,
)
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    MeResponse,
    RefreshRequest,
    TokenPairResponse,
)
from app.services.auth_service import AuthService

router = APIRouter()
logger = structlog.get_logger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "/login",
    response_model=TokenPairResponse,
    summary="Login And Issue Tokens",
    description="Authenticate a user and return access and refresh JWT tokens.",
    responses={
        401: {"description": "Invalid credentials"},
        429: {"description": "Too many requests"},
    },
)
async def login(payload: LoginRequest, request: Request, db: DbDep) -> TokenPairResponse:
    client_ip = request.client.host if request.client is not None else "unknown"
    logger.info("auth.login.attempt", client_ip=client_ip, email=payload.email)

    if await is_login_rate_limited(client_ip):
        logger.warning("auth.login.rate_limited", client_ip=client_ip)
        raise TooManyRequestsError(
            f"Too many login attempts. Try again in {settings.login_rate_limit_window_min} minutes"
        )

    auth_service = AuthService(db)
    try:
        response = await auth_service.login(email=payload.email, password=payload.password)
    except UnauthorizedError:
        await record_failed_login_attempt(client_ip)
        logger.warning("auth.login.failed", client_ip=client_ip, email=payload.email)
        raise

    await clear_failed_login_attempts(client_ip)
    logger.info("auth.login.succeeded", client_ip=client_ip, email=payload.email)
    return response


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Refresh Access Token",
    description="Issue a new short-lived access token from a valid refresh token.",
    responses={401: {"description": "Invalid or expired refresh token"}},
)
async def refresh(payload: RefreshRequest, db: DbDep) -> AccessTokenResponse:
    auth_service = AuthService(db)
    response = await auth_service.refresh_access_token(payload.refresh_token)
    logger.info("auth.refresh.succeeded")
    return response


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Logout And Revoke Refresh Token",
    description="Invalidate a refresh token by adding it to Redis blacklist until token expiration.",
    responses={401: {"description": "Invalid refresh token"}},
)
async def logout(payload: LogoutRequest, db: DbDep) -> LogoutResponse:
    auth_service = AuthService(db)
    response = await auth_service.logout(payload.refresh_token)
    logger.info("auth.logout.succeeded")
    return response


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get Current User Profile",
    description="Return the authenticated user profile and role assignments.",
    responses={401: {"description": "Missing or invalid access token"}},
)
async def me(current_user: CurrentUserDep, db: DbDep) -> MeResponse:
    auth_service = AuthService(db)
    response = await auth_service.get_current_profile(current_user.id)
    logger.info("auth.me.fetched", user_id=str(current_user.id))
    return response
