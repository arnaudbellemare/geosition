"""Registration, login, and sessions."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import cast

from geo_optimizer.models.config import PLATFORM_SESSION_DAYS
from geo_optimizer.saas.models import Organization, PlatformUser, SessionInfo
from geo_optimizer.saas.store import PlatformStore, _IntInput

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PBKDF2_ITERATIONS = 260_000
_PASSWORD_RESET_MINUTES = 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _email_domain(email: str) -> str:
    return email.strip().lower().split("@", 1)[1]


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return salt:hexdigest for storage."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored salt:hexdigest."""
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return secrets.compare_digest(computed, expected)


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_user(
    store: PlatformStore,
    *,
    email: str,
    password: str,
    org_name: str = "",
) -> tuple[PlatformUser, Organization, SessionInfo]:
    """Create user, organization, and session."""
    normalized = email.strip().lower()
    if not _EMAIL_RE.match(normalized):
        raise ValueError("Invalid email address")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    domain = _email_domain(normalized)
    if store.get_user_by_email(normalized):
        raise ValueError("An account with this email already exists")

    password_hash = hash_password(password)
    user = store.create_user(normalized, domain, password_hash)
    name = org_name.strip() or domain.split(".")[0].title()
    try:
        org = store.create_organization(name=name, email_domain=domain, owner_user_id=user.user_id)
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(days=PLATFORM_SESSION_DAYS)).isoformat()
        store.create_session(user.user_id, token, expires)
    except Exception:
        delete_user = getattr(store, "delete_user", None)
        if callable(delete_user):
            delete_user(user.user_id)
        raise
    return user, org, SessionInfo(token=token, user_id=user.user_id, expires_at=expires)


def login_user(store: PlatformStore, *, email: str, password: str) -> tuple[PlatformUser, Organization, SessionInfo]:
    """Authenticate and issue a new session."""
    normalized = email.strip().lower()
    user = store.get_user_by_email(normalized)
    if user is None:
        raise ValueError("Invalid email or password")
    row = store.get_password_hash(user.user_id)
    if not row or not verify_password(password, row):
        raise ValueError("Invalid email or password")

    org = store.get_primary_org_for_user(user.user_id)
    if org is None:
        raise ValueError("No workspace linked to this account")

    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=PLATFORM_SESSION_DAYS)).isoformat()
    store.create_session(user.user_id, token, expires)
    return user, org, SessionInfo(token=token, user_id=user.user_id, expires_at=expires)


def request_password_reset(store: PlatformStore, *, email: str) -> dict[str, object]:
    """Create a one-time reset token for a known account.

    The caller should use a generic response so unknown emails are not exposed.
    """
    normalized = email.strip().lower()
    result: dict[str, object] = {
        "ok": True,
        "message": "If an account exists for that email, a password reset link is ready.",
    }
    if not _EMAIL_RE.match(normalized):
        return result

    user = store.get_user_by_email(normalized)
    if user is None:
        return result

    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=_PASSWORD_RESET_MINUTES)).isoformat()
    store.create_password_reset_token(user.user_id, _hash_reset_token(token), expires)
    result.update({"reset_token": token, "expires_at": expires})
    return result


def reset_password(store: PlatformStore, *, token: str, password: str) -> None:
    """Consume a one-time reset token and replace the account password."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    raw_token = token.strip()
    if not raw_token:
        raise ValueError("Invalid or expired reset link")

    token_hash = _hash_reset_token(raw_token)
    reset = store.get_password_reset_token(token_hash)
    if reset is None:
        raise ValueError("Invalid or expired reset link")

    user_id = int(cast(_IntInput, reset["user_id"]))
    store.update_user_password(user_id, hash_password(password))
    store.mark_password_reset_token_used(token_hash)
    store.delete_sessions_for_user(user_id)


def resolve_session(store: PlatformStore, token: str) -> tuple[PlatformUser, Organization] | None:
    """Return user and org for a valid session token."""
    session = store.get_session(token)
    if session is None:
        return None
    try:
        expires = datetime.fromisoformat(session.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        store.delete_session(token)
        return None

    user = store.get_user_by_id(session.user_id)
    if user is None:
        return None
    org = store.get_primary_org_for_user(user.user_id)
    if org is None:
        return None
    return user, org
