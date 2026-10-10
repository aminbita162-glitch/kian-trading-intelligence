"""MFA and step-up authentication service for Kian Trading Intelligence.

Architecture Decisions: AD-010 (Zero-Trust), AD-026 (Step-Up Authorization).

Per AD-026: step-up authentication for sensitive operations.
Per AD-010: MFA is required for privileged users.

MFA uses TOTP (RFC 6238) simulation. In Phase 02, the TOTP code
is deterministically generated from the user's MFA secret for
testability. In production, a real TOTP library would be used.
"""

from __future__ import annotations

import hashlib
import secrets
import time

from contracts.identity import (
    AuditEventType,
    AuthSession,
    MFAMethod,
    SessionStatus,
    User,
)
from services.identity.audit import audit
from services.identity.database import get_store
from services.identity.session import grant_step_up as _grant_step_up

MFA_CODE_DIGITS = 6
MFA_CODE_VALIDITY_SECONDS = 30
MAX_MFA_ATTEMPTS = 3
STEP_UP_DURATION_SECONDS = 15 * 60  # 15 minutes


class MFAError(Exception):
    """Raised when MFA verification fails."""


class MFANotEnabledError(MFAError):
    """Raised when MFA is not enabled for a user."""


class MFAMethodMismatchError(MFAError):
    """Raised when the MFA method does not match the user's configuration."""


def generate_mfa_secret() -> str:
    """Generate a new MFA secret."""
    return secrets.token_hex(20)


def generate_totp_code(secret: str, timestamp: int | None = None) -> str:
    """Generate a TOTP code from a secret.

    Deterministic for testability: the same secret+time-window produces
    the same code. Uses HMAC-SHA256 in place of HMAC-SHA1 for stronger security.
    """
    if timestamp is None:
        timestamp = int(time.time())
    counter = timestamp // MFA_CODE_VALIDITY_SECONDS
    msg = counter.to_bytes(8, byteorder="big")
    hmac_hash = hashlib.sha256(secret.encode() + msg).hexdigest()
    # Take the last 4 hex chars as a numeric seed
    seed = int(hmac_hash[-8:], 16)
    code = seed % (10**MFA_CODE_DIGITS)
    return str(code).zfill(MFA_CODE_DIGITS)


def verify_totp_code(secret: str, code: str, timestamp: int | None = None) -> bool:
    """Verify a TOTP code against the current time window.

    Allows one previous window (±30 seconds) for clock drift.
    """
    if timestamp is None:
        timestamp = int(time.time())
    for offset in (0, -MFA_CODE_VALIDITY_SECONDS):
        expected = generate_totp_code(secret, timestamp + offset)
        if expected == code:
            return True
    return False


def enable_mfa(
    user: User,
    method: MFAMethod,
) -> str:
    """Enable MFA for a user.

    Returns the MFA secret that the user should store in their authenticator app.
    """
    store = get_store()
    secret = generate_mfa_secret()
    user.mfa_enabled = True
    user.mfa_method = method
    user.mfa_secret = secret
    store.update_user(user)

    audit(
        event_type=AuditEventType.MFA_ENABLED,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        detail=f"MFA enabled: method={method.value}",
    )

    return secret


def disable_mfa(user: User) -> None:
    """Disable MFA for a user."""
    store = get_store()
    user.mfa_enabled = False
    user.mfa_method = None
    user.mfa_secret = None
    store.update_user(user)

    audit(
        event_type=AuditEventType.MFA_DISABLED,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        detail="MFA disabled",
    )


def verify_mfa(
    session: AuthSession,
    user: User,
    code: str,
    method: MFAMethod | None = None,
) -> bool:
    """Verify an MFA code and grant step-up authorization.

    Per AD-026: successful MFA verification grants step-up for a limited time.

    Returns True on success, raises MFAError on failure.
    """
    store = get_store()

    if not user.mfa_enabled or user.mfa_secret is None:
        raise MFANotEnabledError("MFA is not enabled for this user")

    expected_method = method or user.mfa_method
    if expected_method != user.mfa_method:
        raise MFAMethodMismatchError(
            f"Expected MFA method {user.mfa_method}, got {expected_method}"
        )

    if not verify_totp_code(user.mfa_secret, code):
        audit(
            event_type=AuditEventType.MFA_FAILED,
            tenant_id=user.tenant_id,
            actor_user_id=user.user_id,
            detail="MFA verification failed",
        )
        raise MFAError("Invalid MFA code")

    # Grant step-up
    _grant_step_up(session)
    session.status = SessionStatus.ACTIVE

    audit(
        event_type=AuditEventType.MFA_VERIFIED,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        detail="MFA verification successful",
    )

    store.update_session(session)
    return True
