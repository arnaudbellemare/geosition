"""Owner-issued, email-bound invitations to an existing workspace."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def create_invitation(service, token, email):
    user, org = service.require_session(token)
    if service.store.membership_role(user.user_id, org.org_id) != "owner":
        raise PermissionError("Only the workspace owner can invite an operator.")
    email = email.strip().lower()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise ValueError("Enter the operator’s account email address.")
    raw = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    service.store.create_workspace_invitation(org.org_id, email, hashlib.sha256(raw.encode()).hexdigest(), expires)
    return {"token": raw, "expires_at": expires}


def accept_invitation(service, session_token, invite_token):
    user, _ = service.require_session(session_token)
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,64}", invite_token):
        raise ValueError("Invitation is invalid or expired.")
    if not service.store.accept_workspace_invitation(
        hashlib.sha256(invite_token.encode()).hexdigest(), user.user_id, session_token
    ):
        raise ValueError("Invitation is invalid, expired, already used, or belongs to another email.")
    return {"accepted": True}
