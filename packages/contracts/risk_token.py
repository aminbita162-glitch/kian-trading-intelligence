"""Signed risk authorization tokens for Kian Trading Intelligence.

Per E4 (Safety Plane Hardening): risk authorizations must be cryptographically
signed so that tampering, expiry, and replay are detectable.  A signed token
binds the authorization payload to an HMAC-SHA256 tag computed over the
canonical encoding of the payload and the tenant context.

Architecture Decisions: AD-004 (independent Risk Kernel), AD-013 (dynamic
risk management), AD-036 (signed risk tokens).

Trust-domain separation (E4): the signing key for risk tokens is distinct
from the credential-vault master key (AD-019).  The kernel uses a
:class:`RiskTokenSigner` that derives its key from a separate env var
(``KTI_RISK_TOKEN_KEY``); the vault uses ``KTI_VAULT_KEY``.  Neither
component reads the other's key material.

Token format (compact JSON, base64url):
    {
        "p": <payload>,
        "t": <issued_at ISO-8601 UTC>,
        "e": <expires_at ISO-8601 UTC>,
        "n": <nonce hex>,
        "s": <HMAC-SHA256 hex>
    }

The payload ``p`` is a JSON object containing:
    - auth_id: str
    - tenant_id: str
    - policy_id: str
    - policy_version: int
    - intent_id: str
    - symbol: str
    - side: str ("buy" | "sell")
    - quantity: str
    - max_price: str | None

The signature covers the concatenation of ``p``, ``t``, ``e``, and ``n``
in canonical JSON form, plus the tenant context AAD.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

# ── Exceptions ──


class RiskTokenError(Exception):
    """Base exception for risk token errors."""


class RiskTokenTamperError(RiskTokenError):
    """Raised when a risk token signature is invalid (tamper detected)."""


class RiskTokenExpiredError(RiskTokenError):
    """Raised when a risk token has expired."""


class RiskTokenReplayError(RiskTokenError):
    """Raised when a risk token has already been consumed (replay)."""


class RiskTokenMalformedError(RiskTokenError):
    """Raised when a risk token is structurally invalid."""


class RiskTokenKeyError(RiskTokenError):
    """Raised when the signing key is missing or too short."""


# ── Trust domain identifiers ──

TRUST_DOMAIN_KERNEL = "kernel"
TRUST_DOMAIN_VAULT = "vault"

_MIN_KEY_BYTES = 32  # 256 bits — HMAC-SHA256 minimum


def _is_production() -> bool:
    """Return True when running in production mode."""
    return os.environ.get("KTI_ENVIRONMENT", "").lower() == "production"


def _load_risk_token_key() -> bytes:
    """Load the risk-token signing key from the environment.

    Per E4 trust-domain separation: the key is read from
    ``KTI_RISK_TOKEN_KEY`` — NOT ``KTI_VAULT_KEY``.  In production the
    env var must be set to a value of at least ``_MIN_KEY_BYTES`` bytes;
    otherwise :class:`RiskTokenKeyError` is raised (fail-closed).

    In development, a deterministic default is used so tests are
    reproducible.
    """
    raw = os.environ.get("KTI_RISK_TOKEN_KEY", "")
    if _is_production():
        if not raw or len(raw) < _MIN_KEY_BYTES:
            raise RiskTokenKeyError(
                "KTI_RISK_TOKEN_KEY is not set or too short for production. "
                "Set it to a strong random value of at least 32 bytes."
            )
        return raw.encode()
    raw = raw or "phase-e4-risk-token-key-change-in-prod"
    return hashlib.sha256(raw.encode()).digest()


# ── Token payload ──


@dataclass(frozen=True)
class RiskTokenPayload:
    """The payload carried inside a signed risk token.

    This mirrors the fields of :class:`~contracts.risk.RiskAuthorization`
    that must be integrity-protected.
    """

    auth_id: str
    tenant_id: str
    policy_id: str
    policy_version: int
    intent_id: str
    symbol: str
    side: str
    quantity: str
    max_price: str | None

    def to_dict(self) -> dict[str, object]:
        """Serialize to a canonical dict for signing."""
        return {
            "auth_id": self.auth_id,
            "tenant_id": self.tenant_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "max_price": self.max_price,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> RiskTokenPayload:
        """Deserialize from a canonical dict."""
        try:
            return cls(
                auth_id=str(d["auth_id"]),
                tenant_id=str(d["tenant_id"]),
                policy_id=str(d["policy_id"]),
                policy_version=int(str(d["policy_version"])),
                intent_id=str(d["intent_id"]),
                symbol=str(d["symbol"]),
                side=str(d["side"]),
                quantity=str(d["quantity"]),
                max_price=str(d["max_price"]) if d.get("max_price") is not None else None,
            )
        except KeyError as exc:
            raise RiskTokenMalformedError(f"Missing required field: {exc}") from exc


# ── Signed token ──


@dataclass(frozen=True)
class SignedRiskToken:
    """A signed risk authorization token.

    Attributes:
        payload: The integrity-protected payload.
        issued_at: UTC timestamp when the token was issued.
        expires_at: UTC timestamp when the token expires.
        nonce: Unique per-token nonce (prevents replay).
        signature: HMAC-SHA256 hex digest.
        token_str: The serialized token string (base64url-encoded JSON).
    """

    payload: RiskTokenPayload
    issued_at: datetime
    expires_at: datetime
    nonce: str
    signature: str
    token_str: str

    @property
    def is_expired(self) -> bool:
        """True if the token has expired."""
        return datetime.now(UTC) >= self.expires_at

    @property
    def tenant_id(self) -> str:
        """Tenant scope from the payload."""
        return self.payload.tenant_id


# ── Signer / verifier ──


class RiskTokenSigner:
    """HMAC-SHA256 signer for risk authorization tokens.

    Per E4 trust-domain separation: this signer uses a key derived from
    ``KTI_RISK_TOKEN_KEY`` (or a deterministic default in dev).  It is
    distinct from the vault encryption key and has no access to vault
    key material.

    Replay protection: the signer maintains a set of consumed nonces.
    Once a token is verified and consumed, its nonce is recorded;
    subsequent verification of a token with the same nonce raises
    :class:`RiskTokenReplayError`.
    """

    def __init__(self, key: bytes | None = None) -> None:
        if key is None:
            key = _load_risk_token_key()
        if len(key) < _MIN_KEY_BYTES:
            raise RiskTokenKeyError(
                f"Risk token key must be at least {_MIN_KEY_BYTES} bytes (got {len(key)})."
            )
        self._key: bytes = key
        self._consumed_nonces: set[str] = set()
        self._trust_domain: str = TRUST_DOMAIN_KERNEL

    @property
    def trust_domain(self) -> str:
        """The trust domain this signer belongs to."""
        return self._trust_domain

    @staticmethod
    def _canonical(
        payload: RiskTokenPayload, issued_at: datetime, expires_at: datetime, nonce: str
    ) -> str:
        """Return the canonical string that is signed."""
        payload_json = json.dumps(payload.to_dict(), sort_keys=True)
        return f"{payload_json}|{issued_at.isoformat()}|{expires_at.isoformat()}|{nonce}"

    def _compute_signature(self, canonical: str, tenant_aad: str) -> str:
        """Compute the HMAC-SHA256 signature over canonical + tenant AAD."""
        msg = f"{canonical}|{tenant_aad}".encode()
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def issue(
        self,
        payload: RiskTokenPayload,
        *,
        ttl_seconds: int = 30,
        tenant_aad: str = "",
    ) -> SignedRiskToken:
        """Issue a signed risk token for the given payload.

        Args:
            payload: The authorization payload to sign.
            ttl_seconds: Token time-to-live in seconds.
            tenant_aad: Tenant additional authenticated data (bound to
                signature but not stored in the token).

        Returns:
            A :class:`SignedRiskToken` with the serialized token string.
        """
        if payload.side not in ("buy", "sell"):
            raise RiskTokenMalformedError(
                f"Invalid side: {payload.side!r}. Must be 'buy' or 'sell'."
            )
        if payload.policy_version < 1:
            raise RiskTokenMalformedError("policy_version must be >= 1.")

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)
        nonce = uuid4().hex

        canonical = self._canonical(payload, now, expires_at, nonce)
        signature = self._compute_signature(canonical, tenant_aad)

        token_obj = {
            "p": payload.to_dict(),
            "t": now.isoformat(),
            "e": expires_at.isoformat(),
            "n": nonce,
            "s": signature,
        }
        token_json = json.dumps(token_obj, sort_keys=True)
        token_str = base64.urlsafe_b64encode(token_json.encode()).decode()

        return SignedRiskToken(
            payload=payload,
            issued_at=now,
            expires_at=expires_at,
            nonce=nonce,
            signature=signature,
            token_str=token_str,
        )

    def verify(
        self,
        token_str: str,
        *,
        tenant_aad: str = "",
        check_replay: bool = True,
    ) -> SignedRiskToken:
        """Verify a signed risk token.

        Performs:
        1. Structural validation (malformed tokens rejected).
        2. Signature verification (tampered tokens rejected).
        3. Expiry check (expired tokens rejected).
        4. Replay check (consumed nonces rejected, if ``check_replay``).

        Args:
            token_str: The serialized token string.
            tenant_aad: Tenant AAD that was used at issuance time.
            check_replay: If True, reject tokens whose nonce has been
                consumed.

        Returns:
            The verified :class:`SignedRiskToken`.

        Raises:
            RiskTokenMalformedError: If the token is structurally invalid.
            RiskTokenTamperError: If the signature does not match.
            RiskTokenExpiredError: If the token has expired.
            RiskTokenReplayError: If the token has already been consumed.
        """
        try:
            token_json = base64.urlsafe_b64decode(token_str.encode()).decode()
            obj = json.loads(token_json)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RiskTokenMalformedError(f"Malformed token: {exc}") from exc

        required = {"p", "t", "e", "n", "s"}
        if not required.issubset(obj.keys()):
            raise RiskTokenMalformedError(
                f"Token missing required fields: {required - set(obj.keys())}"
            )

        try:
            payload = RiskTokenPayload.from_dict(obj["p"])
            issued_at = datetime.fromisoformat(obj["t"])
            expires_at = datetime.fromisoformat(obj["e"])
            nonce = str(obj["n"])
            signature = str(obj["s"])
        except (ValueError, KeyError) as exc:
            raise RiskTokenMalformedError(f"Invalid token field: {exc}") from exc

        if issued_at.tzinfo is None:
            raise RiskTokenMalformedError("issued_at must be timezone-aware.")
        if expires_at.tzinfo is None:
            raise RiskTokenMalformedError("expires_at must be timezone-aware.")

        # Recompute signature
        canonical = self._canonical(payload, issued_at, expires_at, nonce)
        expected_sig = self._compute_signature(canonical, tenant_aad)

        if not hmac.compare_digest(signature, expected_sig):
            raise RiskTokenTamperError(
                "Signature verification failed — token may be tampered or "
                "the tenant AAD does not match."
            )

        # Expiry
        if datetime.now(UTC) >= expires_at:
            raise RiskTokenExpiredError("Token has expired.")

        # Replay
        if check_replay and nonce in self._consumed_nonces:
            raise RiskTokenReplayError(f"Token nonce {nonce} has already been consumed (replay).")

        return SignedRiskToken(
            payload=payload,
            issued_at=issued_at,
            expires_at=expires_at,
            nonce=nonce,
            signature=signature,
            token_str=token_str,
        )

    def consume(self, token_str: str, *, tenant_aad: str = "") -> SignedRiskToken:
        """Verify and consume a token (marks nonce as used).

        This is the one-shot consumption path: verify then record the nonce
        so the same token cannot be reused.

        Raises:
            Same as :meth:`verify`.
        """
        token = self.verify(token_str, tenant_aad=tenant_aad, check_replay=True)
        self._consumed_nonces.add(token.nonce)
        return token

    def reset(self) -> None:
        """Reset consumed nonces (for testing only)."""
        self._consumed_nonces.clear()
