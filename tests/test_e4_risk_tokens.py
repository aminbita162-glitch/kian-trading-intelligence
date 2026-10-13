"""E4 — Signed risk authorization token tests.

Per E4 (Safety Plane Hardening): signed risk authorization tokens with
tamper/expiry/replay detection.

Tests:
- Token issuance and verification round-trip
- Tampered payload rejected
- Tampered signature rejected
- Tampered timestamp rejected
- Expired token rejected
- Replayed (consumed) token rejected
- Malformed token rejected
- Tenant AAD mismatch rejected
- Different trust domain keys
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from contracts.risk import (
    RiskAuthorizationId,
    RiskPolicyId,
)
from contracts.risk_token import (
    _MIN_KEY_BYTES,
    RiskTokenExpiredError,
    RiskTokenMalformedError,
    RiskTokenReplayError,
    RiskTokenSigner,
    RiskTokenTamperError,
    SignedRiskToken,
    _load_risk_token_key,
)

# ── Fixtures ──


@pytest.fixture
def signer() -> RiskTokenSigner:
    """Create a signer with a known key for deterministic tests."""
    return RiskTokenSigner(key=hashlib.sha256(b"test-signing-key-for-e4").digest())


@pytest.fixture
def payload() -> dict[str, object]:
    """A canonical payload dict for testing."""
    return {
        "auth_id": str(RiskAuthorizationId.generate()),
        "tenant_id": "tenant-001",
        "policy_id": str(RiskPolicyId.generate()),
        "policy_version": 1,
        "intent_id": "intent-001",
        "symbol": "BTC/USDT",
        "side": "buy",
        "quantity": "1.5",
        "max_price": "50000.00",
    }


def _make_token(
    signer: RiskTokenSigner, payload_dict: dict[str, object], ttl: int = 30, aad: str = ""
) -> SignedRiskToken:
    """Helper: issue a token from a dict payload."""
    from contracts.risk_token import RiskTokenPayload

    p = RiskTokenPayload(
        auth_id=str(payload_dict["auth_id"]),
        tenant_id=str(payload_dict["tenant_id"]),
        policy_id=str(payload_dict["policy_id"]),
        policy_version=int(str(payload_dict["policy_version"])),
        intent_id=str(payload_dict["intent_id"]),
        symbol=str(payload_dict["symbol"]),
        side=str(payload_dict["side"]),
        quantity=str(payload_dict["quantity"]),
        max_price=str(payload_dict["max_price"]) if payload_dict.get("max_price") else None,
    )
    return signer.issue(p, ttl_seconds=ttl, tenant_aad=aad)


# ── Round-trip tests ──


class TestTokenRoundTrip:
    """Test basic token issuance and verification."""

    def test_issue_and_verify(self, signer: RiskTokenSigner, payload: dict[str, object]) -> None:
        """A freshly issued token verifies successfully."""
        token = _make_token(signer, payload)
        verified = signer.verify(token.token_str, tenant_aad="")
        assert verified.payload.auth_id == str(payload["auth_id"])
        assert verified.payload.tenant_id == "tenant-001"
        assert verified.payload.side == "buy"

    def test_token_has_nonce(self, signer: RiskTokenSigner, payload: dict[str, object]) -> None:
        """Token must have a unique nonce."""
        token = _make_token(signer, payload)
        assert len(token.nonce) > 0

    def test_token_has_expiry(self, signer: RiskTokenSigner, payload: dict[str, object]) -> None:
        """Token must have a future expiry."""
        token = _make_token(signer, payload, ttl=30)
        assert token.expires_at > datetime.now(UTC)

    def test_two_tokens_have_different_nonces(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """Two tokens for the same payload must have different nonces."""
        t1 = _make_token(signer, payload)
        t2 = _make_token(signer, payload)
        assert t1.nonce != t2.nonce

    def test_token_is_expired_property(
        self, signer: RiskTokenSigner, payload: dict[str, object]
    ) -> None:
        """is_expired returns True for a past expiry."""
        token = _make_token(signer, payload, ttl=0)
        # ttl=0 means expires_at = now, so it's already expired
        assert token.is_expired


# ── Tamper tests ──


class TestTokenTamper:
    """Test tamper detection."""

    def test_tampered_payload_rejected(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """Tampering with the payload must be detected."""
        token = _make_token(signer, payload)
        obj = json.loads(base64.urlsafe_b64decode(token.token_str.encode()))
        # Tamper with the quantity
        obj["p"]["quantity"] = "9999.0"
        tampered = base64.urlsafe_b64encode(json.dumps(obj, sort_keys=True).encode()).decode()
        with pytest.raises(RiskTokenTamperError):
            signer.verify(tampered)

    def test_tampered_signature_rejected(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """Tampering with the signature must be detected."""
        token = _make_token(signer, payload)
        obj = json.loads(base64.urlsafe_b64decode(token.token_str.encode()))
        # Flip a bit in the signature
        sig = obj["s"]
        obj["s"] = "0" + sig[1:] if sig[0] != "0" else "1" + sig[1:]
        tampered = base64.urlsafe_b64encode(json.dumps(obj, sort_keys=True).encode()).decode()
        with pytest.raises(RiskTokenTamperError):
            signer.verify(tampered)

    def test_tampered_expiry_rejected(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """Tampering with the expiry must be detected (signature covers it)."""
        token = _make_token(signer, payload, ttl=30)
        obj = json.loads(base64.urlsafe_b64decode(token.token_str.encode()))
        # Extend expiry by 1 hour — signature won't match
        original = datetime.fromisoformat(obj["e"])
        obj["e"] = (original + timedelta(hours=1)).isoformat()
        tampered = base64.urlsafe_b64encode(json.dumps(obj, sort_keys=True).encode()).decode()
        with pytest.raises(RiskTokenTamperError):
            signer.verify(tampered)

    def test_tampered_nonce_rejected(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """Tampering with the nonce must be detected."""
        token = _make_token(signer, payload)
        obj = json.loads(base64.urlsafe_b64decode(token.token_str.encode()))
        obj["n"] = "a" * len(obj["n"])
        tampered = base64.urlsafe_b64encode(json.dumps(obj, sort_keys=True).encode()).decode()
        with pytest.raises(RiskTokenTamperError):
            signer.verify(tampered)


# ── Expiry tests ──


class TestTokenExpiry:
    """Test expiry detection."""

    def test_expired_token_rejected(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """An expired token must be rejected."""
        token = _make_token(signer, payload, ttl=0)
        # The token is already expired (expires_at = now)
        with pytest.raises(RiskTokenExpiredError):
            signer.verify(token.token_str)


# ── Replay tests ──


class TestTokenReplay:
    """Test replay detection."""

    def test_consume_marks_nonce(self, signer: RiskTokenSigner, payload: dict[str, object]) -> None:
        """Consuming a token records its nonce."""
        token = _make_token(signer, payload)
        signer.consume(token.token_str)
        assert token.nonce in signer._consumed_nonces

    def test_replayed_token_rejected(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """A consumed token cannot be reused (replay)."""
        token = _make_token(signer, payload)
        signer.consume(token.token_str)
        with pytest.raises(RiskTokenReplayError):
            signer.consume(token.token_str)

    def test_verify_without_replay_check_allows_reuse(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """verify with check_replay=False allows the same nonce twice."""
        token = _make_token(signer, payload)
        signer.consume(token.token_str)
        # verify without replay check should still work
        verified = signer.verify(token.token_str, check_replay=False)
        assert verified is not None


# ── Malformed tests ──


class TestTokenMalformed:
    """Test malformed token handling."""

    def test_garbage_string_rejected(self, signer: RiskTokenSigner) -> None:
        """A garbage string must raise RiskTokenMalformedError."""
        with pytest.raises(RiskTokenMalformedError):
            signer.verify("not-a-valid-base64-!!!")

    def test_missing_field_rejected(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """A token missing a required field must be rejected."""
        token = _make_token(signer, payload)
        obj = json.loads(base64.urlsafe_b64decode(token.token_str.encode()))
        del obj["s"]
        malformed = base64.urlsafe_b64encode(json.dumps(obj, sort_keys=True).encode()).decode()
        with pytest.raises(RiskTokenMalformedError):
            signer.verify(malformed)

    def test_empty_string_rejected(self, signer: RiskTokenSigner) -> None:
        """An empty string must be rejected."""
        with pytest.raises(RiskTokenMalformedError):
            signer.verify("")


# ── Tenant AAD tests ──


class TestTenantAAD:
    """Test tenant additional authenticated data binding."""

    def test_aad_mismatch_rejected(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """A token issued with AAD must fail verification with different AAD."""
        token = _make_token(signer, payload, aad="tenant-A")
        with pytest.raises(RiskTokenTamperError):
            signer.verify(token.token_str, tenant_aad="tenant-B")

    def test_aad_match_succeeds(
        self,
        signer: RiskTokenSigner,
        payload: dict[str, object],
    ) -> None:
        """A token issued with AAD must verify with matching AAD."""
        token = _make_token(signer, payload, aad="tenant-A")
        verified = signer.verify(token.token_str, tenant_aad="tenant-A")
        assert verified.payload.auth_id == str(payload["auth_id"])


# ── Key separation tests ──


class TestKeySeparation:
    """Test that different signers produce different signatures."""

    def test_different_keys_different_signatures(
        self,
        payload: dict[str, object],
    ) -> None:
        """Two signers with different keys produce different signatures."""
        s1 = RiskTokenSigner(key=hashlib.sha256(b"key-A").digest())
        s2 = RiskTokenSigner(key=hashlib.sha256(b"key-B").digest())
        t1 = _make_token(s1, payload)
        t2 = _make_token(s2, payload)
        assert t1.signature != t2.signature

    def test_cross_key_verification_fails(
        self,
        payload: dict[str, object],
    ) -> None:
        """A token from signer A cannot be verified by signer B."""
        s1 = RiskTokenSigner(key=hashlib.sha256(b"key-A").digest())
        s2 = RiskTokenSigner(key=hashlib.sha256(b"key-B").digest())
        t1 = _make_token(s1, payload)
        with pytest.raises(RiskTokenTamperError):
            s2.verify(t1.token_str)

    def test_key_too_short_rejected(self) -> None:
        """A key shorter than _MIN_KEY_BYTES must be rejected."""
        with pytest.raises(Exception):  # noqa: B017
            RiskTokenSigner(key=b"short")

    def test_load_key_returns_bytes(self) -> None:
        """_load_risk_token_key must return bytes of sufficient length."""
        key = _load_risk_token_key()
        assert isinstance(key, bytes)
        assert len(key) >= _MIN_KEY_BYTES
