"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    RequireAdmin,
    get_app_session,
    get_app_settings,
    get_auth_service,
    get_fingerprint,
    verify_csrf,
)
from app.auth.cookies import (
    clear_session_cookies,
    read_persistent,
    read_refresh_token,
    set_session_cookies,
)
from app.auth.service import AuthService, RequestFingerprint, SessionTokens
from app.core.config import Settings
from app.core.exceptions import TokenError
from app.schemas.auth import (
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    LogoutRequest,
    SessionResponse,
    UpdatePreferencesRequest,
    UserProfile,
    user_profile,
)
from app.services.governance.quota import weekly_usage
from app.services.security.region_scope import load_region_scope

router = APIRouter(prefix="/auth", tags=["auth"])

ServiceDep = Annotated[AuthService, Depends(get_auth_service)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
FingerprintDep = Annotated[RequestFingerprint, Depends(get_fingerprint)]


def _session_response(
    response: Response,
    settings: Settings,
    tokens: SessionTokens,
    *,
    persistent: bool = True,
    scope=None,
) -> SessionResponse:
    set_session_cookies(
        response,
        settings,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        csrf_token=tokens.csrf_token,
        persistent=persistent,
    )
    return SessionResponse(
        user=user_profile(tokens.user, scope),
        csrf_token=tokens.csrf_token,
        access_expires_at=tokens.access_expires_at,
    )


@router.post(
    "/login",
    response_model=SessionResponse,
    summary="Sign in with username and password",
)
async def login(
    payload: LoginRequest,
    response: Response,
    service: ServiceDep,
    settings: SettingsDep,
    fingerprint: FingerprintDep,
) -> SessionResponse:
    tokens = await service.login(
        login=payload.username, password=payload.password, fingerprint=fingerprint
    )
    scope = await load_region_scope(service._session, tokens.user)
    return _session_response(
        response, settings, tokens, persistent=payload.remember_me, scope=scope
    )


@router.post(
    "/refresh",
    response_model=SessionResponse,
    summary="Exchange a refresh token for a new session",
)
async def refresh(
    request: Request,
    response: Response,
    service: ServiceDep,
    settings: SettingsDep,
    fingerprint: FingerprintDep,
) -> SessionResponse:
    token = read_refresh_token(request)
    if not token:
        raise TokenError("No refresh token was supplied.")
    try:
        tokens = await service.refresh(refresh_token=token, fingerprint=fingerprint)
    except TokenError:
        # The session is unusable; clear the cookies so the client stops retrying with a
        # token that will never work again.
        clear_session_cookies(response, settings)
        raise
    scope = await load_region_scope(service._session, tokens.user)
    return _session_response(
        response, settings, tokens, persistent=read_persistent(request), scope=scope
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_csrf)],
    summary="Revoke the current session",
)
async def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest,
    service: ServiceDep,
    settings: SettingsDep,
    fingerprint: FingerprintDep,
    user: CurrentUser,
) -> Response:
    await service.logout(
        refresh_token=read_refresh_token(request),
        user_id=user.id,
        fingerprint=fingerprint,
        all_sessions=payload.all_sessions,
    )
    clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserProfile, summary="Current user profile")
async def me(
    user: CurrentUser, session: Annotated[AsyncSession, Depends(get_app_session)]
) -> UserProfile:
    return user_profile(user, await load_region_scope(session, user))


@router.get("/me/usage", summary="The caller's AI usage for the current week")
async def my_usage(
    user: CurrentUser, session: Annotated[AsyncSession, Depends(get_app_session)]
) -> dict[str, Any]:
    return (await weekly_usage(session, user)).to_dict()


@router.patch(
    "/me/preferences",
    response_model=UserProfile,
    dependencies=[Depends(verify_csrf)],
    summary="Update the caller's default industry",
)
async def update_preferences(
    payload: UpdatePreferencesRequest, user: CurrentUser, service: ServiceDep
) -> UserProfile:
    await service.users.set_default_industry(user, payload.default_industry)
    scope = await load_region_scope(service._session, user)
    return user_profile(user, scope)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_csrf)],
    summary="Change the caller's password",
)
async def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: CurrentUser,
    service: ServiceDep,
    settings: SettingsDep,
    fingerprint: FingerprintDep,
) -> Response:
    await service.change_password(
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        fingerprint=fingerprint,
    )
    # Every session was revoked, including this one, so the client must sign in again.
    clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/users",
    response_model=UserProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
    summary="Create a user account (admin only)",
)
async def create_user(
    payload: CreateUserRequest,
    admin: RequireAdmin,
    service: ServiceDep,
    fingerprint: FingerprintDep,
) -> UserProfile:
    user = await service.create_user(
        actor=admin,
        email=str(payload.email),
        username=payload.username,
        full_name=payload.full_name,
        password=payload.password,
        role=payload.role,
        default_industry=payload.default_industry,
        must_change_password=payload.must_change_password,
        fingerprint=fingerprint,
    )
    return user_profile(user)


@router.get(
    "/users",
    response_model=list[UserProfile],
    summary="List user accounts (admin only)",
)
async def list_users(
    admin: RequireAdmin,
    service: ServiceDep,
    limit: int = 100,
    offset: int = 0,
) -> list[UserProfile]:
    users = await service.users.list_all(limit=min(limit, 500), offset=max(offset, 0))
    return [user_profile(user) for user in users]
