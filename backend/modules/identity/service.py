from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.responses import Response

from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.core.models import AccountSession, User
from backend.core.rate_limit import SlidingWindowLimiter
from backend.core.security import hash_password, new_token, token_hash, verify_password
from backend.modules.identity.schemas import AccountResponse

SESSION_COOKIE = "ww_session"
CSRF_COOKIE = "ww_csrf"
COOKIE_PATH = "/api/v1"
_registration_lock = threading.Lock()
_rate_limiter = SlidingWindowLimiter()


def _check_rate_limit(
    request: Request, settings: Settings, operation: str
) -> None:
    address = request.client.host if request.client else "unknown"
    key = f"{operation}:{address}"
    if not _rate_limiter.allow(
        key,
        limit=settings.auth_rate_limit,
        window_seconds=settings.auth_rate_window_seconds,
    ):
        raise ApiError(429, "rate_limited", "Too many attempts. Please try again later.")


def _validate_same_origin(request: Request) -> None:
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if fetch_site == "cross-site":
        raise ApiError(403, "csrf_rejected", "Cross-site request rejected.")

    origin = request.headers.get("origin")
    if not origin:
        return

    forwarded_host = request.headers.get("x-forwarded-host")
    host = (forwarded_host or request.headers.get("host", "")).split(",", 1)[0].strip()
    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = (forwarded_proto or request.url.scheme).split(",", 1)[0].strip()
    origin_parts = urlsplit(origin)

    if (
        not origin_parts.netloc
        or origin_parts.netloc.lower() != host.lower()
        or origin_parts.scheme.lower() != scheme.lower()
    ):
        raise ApiError(403, "csrf_rejected", "Cross-origin request rejected.")


def _set_session_cookies(
    response: Response,
    settings: Settings,
    session_token: str,
    csrf_token: str,
) -> None:
    max_age = settings.session_ttl_days * 24 * 60 * 60
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def _new_session(
    db: Session, user: User, settings: Settings
) -> tuple[AccountSession, str, str]:
    session_token = new_token()
    csrf_token = new_token()
    session = AccountSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=token_hash(session_token),
        csrf_hash=token_hash(csrf_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.session_ttl_days),
    )
    db.add(session)
    return session, session_token, csrf_token


def _account_payload(user: User) -> dict[str, Any]:
    return AccountResponse.model_validate(user).model_dump(mode="json")


def register_account(
    request: Request,
    response: Response,
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    display_name: str,
) -> dict[str, Any]:
    _check_rate_limit(request, settings, "register")
    _validate_same_origin(request)
    normalized_email = email.strip().lower()

    with _registration_lock:
        if settings.registration_mode == "closed":
            raise ApiError(
                403, "registration_disabled", "Account registration is disabled."
            )
        if (
            settings.registration_mode == "bootstrap_only"
            and db.scalar(select(User.id).limit(1)) is not None
        ):
            raise ApiError(
                403,
                "registration_disabled",
                "Open registration is disabled after the initial administrator account.",
            )

        user = User(
            id=uuid.uuid4(),
            email=normalized_email,
            password_hash=hash_password(password),
            display_name=display_name.strip(),
            status="active",
        )
        db.add(user)
        try:
            db.flush()
            _session, session_token, csrf_token = _new_session(db, user, settings)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ApiError(
                409, "account_exists", "An account with this email already exists."
            ) from exc

    _set_session_cookies(response, settings, session_token, csrf_token)
    return _account_payload(user)


def login_account(
    request: Request,
    response: Response,
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
) -> dict[str, Any]:
    _check_rate_limit(request, settings, "login")
    _validate_same_origin(request)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))

    if not verify_password(password, user.password_hash if user else None):
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    if user is None or user.status != "active":
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")

    previous_token = request.cookies.get(SESSION_COOKIE)
    if previous_token:
        previous_session = db.scalar(
            select(AccountSession).where(
                AccountSession.token_hash == token_hash(previous_token),
                AccountSession.revoked_at.is_(None),
            )
        )
        if previous_session:
            previous_session.revoked_at = datetime.now(timezone.utc)

    _session, session_token, csrf_token = _new_session(db, user, settings)
    db.commit()
    _set_session_cookies(response, settings, session_token, csrf_token)
    return _account_payload(user)


def get_active_session(request: Request, db: Session) -> AccountSession:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise ApiError(401, "authentication_required", "Authentication is required.")

    current_time = datetime.now(timezone.utc)
    session = db.scalar(
        select(AccountSession).where(
            AccountSession.token_hash == token_hash(raw_token),
            AccountSession.revoked_at.is_(None),
            AccountSession.expires_at > current_time,
        )
    )
    if session is None:
        raise ApiError(401, "authentication_required", "Authentication is required.")

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= current_time:
        raise ApiError(401, "authentication_required", "Authentication is required.")

    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        raise ApiError(401, "authentication_required", "Authentication is required.")
    return session


def get_current_account(request: Request, db: Session) -> User:
    session = get_active_session(request, db)
    user = db.get(User, session.user_id)
    if user is None:
        raise ApiError(401, "authentication_required", "Authentication is required.")
    return user


def revoke_current_session(
    request: Request,
    response: Response,
    db: Session,
    settings: Settings,
) -> None:
    session = get_active_session(request, db)
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if (
        not csrf_cookie
        or not csrf_header
        or csrf_cookie != csrf_header
        or token_hash(csrf_header) != session.csrf_hash
    ):
        raise ApiError(403, "csrf_rejected", "CSRF verification failed.")

    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    _clear_session_cookies(response, settings)
