"""Authentication service.

Owns the login, refresh and logout flows, the audit trail that accompanies them, and the
administrative user operations. Routers call this; they contain no auth logic themselves.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import passwords
from app.auth.rate_limit import FixedWindowRateLimiter
from app.auth.tokens import (
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    hash_refresh_token,
)
from app.core.clock import ensure_aware
from app.core.config import Industry, Settings
from app.core.exceptions import (
    AccountLockedError,
    AuthorizationError,
    InvalidCredentialsError,
    NotFoundError,
    RateLimitedError,
    TokenError,
    TokenReuseError,
    ValidationError,
)
from app.models.enums import AuthEventType, Role
from app.models.user import User
from app.repositories.audit import AuthAuditRepository
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository, normalize_email

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RequestFingerprint:
    """Where a request came from, for audit and token binding."""

    request_id: str
    ip_address: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime
    user: User


class AuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        login_limiter: FixedWindowRateLimiter,
    ) -> None:
        self._session = session
        self._settings = settings
        self._login_limiter = login_limiter
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.audit = AuthAuditRepository(session)

    async def _persist(self) -> None:
        """Commit work that must survive the error about to be raised.

        The request-scoped session rolls back when a handler raises, which would discard
        failed-login audit rows and revoked token families — exactly the records that
        matter most. Committing first makes the security trail durable.
        """
        await self._session.commit()

    # --- login -------------------------------------------------------------

    async def login(
        self, *, email: str, password: str, fingerprint: RequestFingerprint
    ) -> SessionTokens:
        normalized = normalize_email(email)

        # Limit by account and by source address independently, so one attacker cannot
        # lock every account and a botnet cannot brute force a single one.
        for key in (f"email:{normalized}", f"ip:{fingerprint.ip_address or 'unknown'}"):
            decision = await self._login_limiter.check(key)
            if not decision.allowed:
                await self.audit.record(
                    AuthEventType.LOGIN_RATE_LIMITED,
                    succeeded=False,
                    email_attempted=normalized,
                    request_id=fingerprint.request_id,
                    ip_address=fingerprint.ip_address,
                    user_agent=fingerprint.user_agent,
                    reason="rate_limited",
                )
                await self._persist()
                raise RateLimitedError(decision.retry_after_seconds)

        user = await self.users.get_by_email(normalized)

        # Always run a verification, even for an unknown account, so response timing does
        # not disclose whether the address exists.
        password_ok = passwords.verify_password(
            password, user.password_hash if user else None
        )

        if user is None or not password_ok:
            await self.audit.record(
                AuthEventType.LOGIN_FAILED,
                succeeded=False,
                user_id=user.id if user else None,
                email_attempted=normalized,
                request_id=fingerprint.request_id,
                ip_address=fingerprint.ip_address,
                user_agent=fingerprint.user_agent,
                reason="bad_credentials",
            )
            await self._persist()
            raise InvalidCredentialsError

        if not user.is_active:
            await self.audit.record(
                AuthEventType.LOGIN_BLOCKED_INACTIVE,
                succeeded=False,
                user_id=user.id,
                email_attempted=normalized,
                request_id=fingerprint.request_id,
                ip_address=fingerprint.ip_address,
                user_agent=fingerprint.user_agent,
                reason="inactive_account",
            )
            await self._persist()
            raise AccountLockedError

        # Opportunistically upgrade a hash produced under weaker parameters. This is the
        # only moment the plaintext is available to do so.
        if passwords.needs_rehash(user.password_hash):
            await self.users.update_password_hash(user, passwords.hash_password(password))

        await self._login_limiter.reset(f"email:{normalized}")
        await self.users.record_successful_login(user)

        tokens = await self._issue_session(user, fingerprint=fingerprint, family_id=None)

        await self.audit.record(
            AuthEventType.LOGIN_SUCCEEDED,
            succeeded=True,
            user_id=user.id,
            email_attempted=normalized,
            request_id=fingerprint.request_id,
            ip_address=fingerprint.ip_address,
            user_agent=fingerprint.user_agent,
        )
        return tokens

    # --- refresh -----------------------------------------------------------

    async def refresh(
        self, *, refresh_token: str, fingerprint: RequestFingerprint
    ) -> SessionTokens:
        token_hash = hash_refresh_token(refresh_token)
        stored = await self.tokens.get_by_hash(token_hash)
        if stored is None:
            raise TokenError("Unknown refresh token.")

        now = datetime.now(UTC)

        if stored.rotated_at is not None:
            # This token was already exchanged. Presenting it again means it leaked, so
            # the entire family is revoked and the user must sign in again.
            revoked = await self.tokens.revoke_family(
                stored.family_id, reason="reuse_detected"
            )
            await self.audit.record(
                AuthEventType.TOKEN_REUSE_DETECTED,
                succeeded=False,
                user_id=stored.user_id,
                request_id=fingerprint.request_id,
                ip_address=fingerprint.ip_address,
                user_agent=fingerprint.user_agent,
                reason="reuse_detected",
                metadata={"family_id": str(stored.family_id), "revoked_tokens": revoked},
            )
            logger.warning(
                "refresh token reuse detected",
                extra={"user_id": str(stored.user_id), "family_id": str(stored.family_id)},
            )
            await self._persist()
            raise TokenReuseError

        if stored.revoked_at is not None:
            raise TokenError("This session has been revoked.", code="token_revoked")
        if ensure_aware(stored.expires_at) <= now:
            raise TokenError("The session has expired.", code="token_expired")

        user = await self.users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            await self.tokens.revoke_family(stored.family_id, reason="user_inactive")
            await self._persist()
            raise AccountLockedError

        await self.tokens.mark_rotated(stored)
        tokens = await self._issue_session(
            user, fingerprint=fingerprint, family_id=stored.family_id
        )

        await self.audit.record(
            AuthEventType.TOKEN_REFRESHED,
            succeeded=True,
            user_id=user.id,
            request_id=fingerprint.request_id,
            ip_address=fingerprint.ip_address,
            user_agent=fingerprint.user_agent,
            metadata={"family_id": str(stored.family_id)},
        )
        return tokens

    # --- logout ------------------------------------------------------------

    async def logout(
        self,
        *,
        refresh_token: str | None,
        user_id: uuid.UUID | None,
        fingerprint: RequestFingerprint,
        all_sessions: bool = False,
    ) -> None:
        if all_sessions and user_id is not None:
            await self.tokens.revoke_all_for_user(user_id, reason="logout_all")
        elif refresh_token:
            stored = await self.tokens.get_by_hash(hash_refresh_token(refresh_token))
            if stored is not None:
                await self.tokens.revoke_family(stored.family_id, reason="logout")

        await self.audit.record(
            AuthEventType.LOGOUT,
            succeeded=True,
            user_id=user_id,
            request_id=fingerprint.request_id,
            ip_address=fingerprint.ip_address,
            user_agent=fingerprint.user_agent,
            metadata={"all_sessions": all_sessions},
        )

    # --- password ----------------------------------------------------------

    async def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
        fingerprint: RequestFingerprint,
    ) -> None:
        if not passwords.verify_password(current_password, user.password_hash):
            await self.audit.record(
                AuthEventType.PASSWORD_CHANGED,
                succeeded=False,
                user_id=user.id,
                request_id=fingerprint.request_id,
                ip_address=fingerprint.ip_address,
                user_agent=fingerprint.user_agent,
                reason="current_password_incorrect",
            )
            await self._persist()
            raise InvalidCredentialsError("The current password is incorrect.")

        policy = passwords.check_password_policy(new_password, email=user.email)
        if not policy.ok:
            raise ValidationError(
                "The new password does not meet the policy.",
                details={"problems": list(policy.problems)},
            )

        await self.users.update_password_hash(user, passwords.hash_password(new_password))
        # Every existing session is invalidated: a password change should end access for
        # anyone holding a token issued under the old one.
        await self.tokens.revoke_all_for_user(user.id, reason="password_changed")

        await self.audit.record(
            AuthEventType.PASSWORD_CHANGED,
            succeeded=True,
            user_id=user.id,
            request_id=fingerprint.request_id,
            ip_address=fingerprint.ip_address,
            user_agent=fingerprint.user_agent,
        )

    # --- administration ----------------------------------------------------

    async def create_user(
        self,
        *,
        actor: User | None,
        email: str,
        full_name: str,
        password: str,
        role: Role,
        default_industry: Industry,
        must_change_password: bool = True,
        fingerprint: RequestFingerprint | None = None,
    ) -> User:
        if actor is not None and actor.role is not Role.ADMIN:
            raise AuthorizationError("Only an administrator can create accounts.")

        policy = passwords.check_password_policy(password, email=email)
        if not policy.ok:
            raise ValidationError(
                "The password does not meet the policy.",
                details={"problems": list(policy.problems)},
            )

        user = await self.users.create(
            email=email,
            full_name=full_name,
            password_hash=passwords.hash_password(password),
            role=role,
            default_industry=default_industry,
            must_change_password=must_change_password,
        )
        await self.audit.record(
            AuthEventType.USER_CREATED,
            succeeded=True,
            user_id=user.id,
            email_attempted=user.email_normalized,
            request_id=fingerprint.request_id if fingerprint else None,
            ip_address=fingerprint.ip_address if fingerprint else None,
            user_agent=fingerprint.user_agent if fingerprint else None,
            metadata={"role": role.value, "created_by": str(actor.id) if actor else "cli"},
        )
        return user

    async def set_user_role(
        self, *, actor: User, user_id: uuid.UUID, role: Role, fingerprint: RequestFingerprint
    ) -> User:
        if actor.role is not Role.ADMIN:
            raise AuthorizationError("Only an administrator can change roles.")
        target = await self.users.get_by_id(user_id)
        if target is None:
            raise NotFoundError("No such user.")
        if target.id == actor.id and role is not Role.ADMIN:
            raise ValidationError("You cannot remove your own administrator role.")

        previous = target.role
        await self.users.set_role(target, role)
        await self.audit.record(
            AuthEventType.ROLE_CHANGED,
            succeeded=True,
            user_id=target.id,
            request_id=fingerprint.request_id,
            ip_address=fingerprint.ip_address,
            user_agent=fingerprint.user_agent,
            metadata={"from": previous.value, "to": role.value, "by": str(actor.id)},
        )
        return target

    async def set_user_active(
        self,
        *,
        actor: User,
        user_id: uuid.UUID,
        is_active: bool,
        fingerprint: RequestFingerprint,
    ) -> User:
        if actor.role is not Role.ADMIN:
            raise AuthorizationError("Only an administrator can disable accounts.")
        target = await self.users.get_by_id(user_id)
        if target is None:
            raise NotFoundError("No such user.")
        if target.id == actor.id and not is_active:
            raise ValidationError("You cannot disable your own account.")

        await self.users.set_active(target, is_active=is_active)
        if not is_active:
            await self.tokens.revoke_all_for_user(target.id, reason="account_disabled")
            await self.audit.record(
                AuthEventType.USER_DISABLED,
                succeeded=True,
                user_id=target.id,
                request_id=fingerprint.request_id,
                ip_address=fingerprint.ip_address,
                user_agent=fingerprint.user_agent,
                metadata={"by": str(actor.id)},
            )
        return target

    # --- internal ----------------------------------------------------------

    async def _issue_session(
        self,
        user: User,
        *,
        fingerprint: RequestFingerprint,
        family_id: uuid.UUID | None,
    ) -> SessionTokens:
        refresh = create_refresh_token(self._settings, family_id=family_id)
        await self.tokens.store(
            refresh,
            user_id=user.id,
            user_agent=fingerprint.user_agent,
            ip_address=fingerprint.ip_address,
        )
        access_token, claims = create_access_token(
            self._settings,
            user_id=user.id,
            email=user.email,
            role=user.role,
            default_industry=user.default_industry,
            session_id=refresh.family_id,
        )
        return SessionTokens(
            access_token=access_token,
            refresh_token=refresh.plaintext,
            csrf_token=create_csrf_token(),
            access_expires_at=claims.expires_at,
            user=user,
        )
