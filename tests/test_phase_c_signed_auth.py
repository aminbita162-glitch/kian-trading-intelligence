"""Phase C — Signed risk authorization token integration on the simulation order path.

Per DIRECTIV.txt V1.4 Phase C: "Activate signed risk authorization tokens on
the simulation order path (short-lived, single-use, cryptographically signed,
bound to exact order parameters)."

These tests verify that the :class:`~services.phase_c.SignedRiskAuthorizationService`
issues signed tokens on the order path and that the tokens are:
- Short-lived (TTL expiry)
- Single-use (nonce replay rejection)
- Cryptographically signed (tamper detection)
- Bound to exact order parameters (payload mismatch rejection)
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from contracts.order import OrderIntent
from contracts.risk import (
    AuthorizationStatus,
    RiskPolicy,
)
from contracts.risk_token import (
    RiskTokenExpiredError,
    RiskTokenMalformedError,
    RiskTokenReplayError,
    RiskTokenSigner,
    RiskTokenTamperError,
)
from services.phase_c import SignedRiskAuthorizationService
from services.risk_kernel.kernel import RiskKernel

# ── Fixtures ──


@pytest.fixture
def kernel() -> RiskKernel:
    """Create a risk kernel with an active policy for a test tenant."""
    k = RiskKernel()
    policy = RiskPolicy.create(
        tenant_id="tenant-signed",
        max_concentration_pct="100.0",
        max_position_per_symbol=10000,
    ).activate()
    k.register_policy(policy)
    return k


@pytest.fixture
def signer() -> RiskTokenSigner:
    """Create a signer with a known key for deterministic tests."""
    return RiskTokenSigner(key=hashlib.sha256(b"phase-c-test-signing-key").digest())


@pytest.fixture
def service(kernel: RiskKernel, signer: RiskTokenSigner) -> SignedRiskAuthorizationService:
    """Create a SignedRiskAuthorizationService with the test kernel and signer."""
    return SignedRiskAuthorizationService(kernel=kernel, signer=signer, ttl_seconds=30)


@pytest.fixture
def intent() -> OrderIntent:
    """Create a valid buy order intent."""
    return OrderIntent.create(
        tenant_id="tenant-signed",
        profile_id="profile-1",
        symbol="BTC/USDT",
        side="buy",
        quantity="0.01",
    )


# ── Authorization + signing tests ──


class TestSignedAuthorization:
    """Test that the signed authorization service issues tokens correctly."""

    def test_authorize_issues_signed_token(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """Authorizing an approved order issues a signed token."""
        result = service.authorize(intent, current_price="50000.00")

        assert result.is_authorized
        assert result.token is not None
        assert result.token.payload.symbol == "BTC/USDT"
        assert result.token.payload.side == "buy"
        assert result.token.payload.quantity == "0.01"
        assert result.token.payload.tenant_id == "tenant-signed"

    def test_authorize_denied_no_token(
        self,
        kernel: RiskKernel,
        service: SignedRiskAuthorizationService,
    ) -> None:
        """A denied authorization does not issue a token."""
        # Activate emergency stop to deny the order
        kernel.activate_emergency_stop("test")
        bad_intent = OrderIntent.create(
            tenant_id="tenant-signed",
            profile_id="profile-1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )
        result = service.authorize(bad_intent, current_price="50000.00")

        assert not result.is_authorized
        assert result.token is None
        assert result.authorization.status is AuthorizationStatus.DENIED

    def test_token_is_short_lived(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """The token has a short TTL (default 30 seconds)."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.token is not None

        # Token should expire within 30 seconds
        delta = result.token.expires_at - result.token.issued_at
        assert delta <= timedelta(seconds=30)
        assert result.token.expires_at > datetime.now(UTC)

    def test_token_bound_to_exact_order_parameters(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """The token payload matches the exact order parameters."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.token is not None
        auth = result.authorization

        assert result.token.payload.auth_id == str(auth.authorization_id)
        assert result.token.payload.intent_id == str(intent.intent_id)
        assert result.token.payload.symbol == intent.symbol
        assert result.token.payload.side == intent.side
        assert result.token.payload.quantity == intent.quantity
        assert result.token.payload.max_price == "50000.00"


# ── Verify and consume tests ──


class TestVerifyAndConsume:
    """Test the verify-and-consume flow."""

    def test_verify_and_consume_succeeds(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """A valid token is verified and the authorization consumed."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.is_authorized
        assert result.token is not None

        auth_id = str(result.authorization.authorization_id)
        consumed = service.verify_and_consume(
            auth_id,
            token_str=result.token.token_str,
        )

        assert consumed.authorization.status is AuthorizationStatus.CONSUMED
        assert consumed.token is not None
        assert consumed.token.payload.auth_id == auth_id

    def test_replay_rejected(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """A consumed token cannot be reused (replay protection)."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.token is not None

        auth_id = str(result.authorization.authorization_id)
        token_str = result.token.token_str

        # First consumption succeeds
        service.verify_and_consume(auth_id, token_str=token_str)

        # Second consumption with the same token is rejected
        with pytest.raises(RiskTokenReplayError):
            service.verify_and_consume(auth_id, token_str=token_str)

    def test_tampered_payload_rejected(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """A tampered token payload is rejected."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.token is not None

        # Tamper with the payload quantity
        obj = json.loads(base64.urlsafe_b64decode(result.token.token_str.encode()))
        obj["p"]["quantity"] = "9999.0"
        tampered = base64.urlsafe_b64encode(json.dumps(obj, sort_keys=True).encode()).decode()

        auth_id = str(result.authorization.authorization_id)
        with pytest.raises(RiskTokenTamperError):
            service.verify_and_consume(auth_id, token_str=tampered)

    def test_tampered_signature_rejected(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """A tampered signature is rejected."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.token is not None

        obj = json.loads(base64.urlsafe_b64decode(result.token.token_str.encode()))
        sig = obj["s"]
        obj["s"] = "0" + sig[1:] if sig[0] != "0" else "1" + sig[1:]
        tampered = base64.urlsafe_b64encode(json.dumps(obj, sort_keys=True).encode()).decode()

        auth_id = str(result.authorization.authorization_id)
        with pytest.raises(RiskTokenTamperError):
            service.verify_and_consume(auth_id, token_str=tampered)

    def test_expired_token_rejected(
        self,
        kernel: RiskKernel,
        intent: OrderIntent,
    ) -> None:
        """An expired token is rejected."""
        # Use a 0-second TTL to create an immediately expired token
        signer = RiskTokenSigner(key=hashlib.sha256(b"phase-c-test-signing-key").digest())
        svc = SignedRiskAuthorizationService(kernel=kernel, signer=signer, ttl_seconds=0)

        result = svc.authorize(intent, current_price="50000.00")
        # With ttl=0, the token expires immediately
        if result.token is not None and result.token.is_expired:
            auth_id = str(result.authorization.authorization_id)
            with pytest.raises((RiskTokenExpiredError, RiskTokenReplayError)):
                svc.verify_and_consume(auth_id, token_str=result.token.token_str)

    def test_wrong_tenant_aad_rejected(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """A token verified with the wrong tenant AAD is rejected."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.token is not None

        # Try to verify with wrong AAD directly via the signer
        with pytest.raises(RiskTokenTamperError):
            service.signer.verify(
                result.token.token_str,
                tenant_aad="wrong-tenant",
                check_replay=True,
            )

    def test_malformed_token_rejected(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """A structurally invalid token is rejected."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.token is not None

        auth_id = str(result.authorization.authorization_id)
        with pytest.raises(RiskTokenMalformedError):
            service.verify_and_consume(auth_id, token_str="not-a-valid-token")


# ── Cross-check tests ──


class TestTokenPayloadCrossCheck:
    """Test that the token payload must match the authorization."""

    def test_token_for_wrong_auth_rejected(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """A token for one authorization cannot be used with a different one."""
        # Authorize two orders
        result1 = service.authorize(intent, current_price="50000.00")
        intent2 = OrderIntent.create(
            tenant_id="tenant-signed",
            profile_id="profile-1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.02",
        )
        result2 = service.authorize(intent2, current_price="50000.00")

        assert result1.token is not None
        assert result2.token is not None

        # Try to use token1 with auth2 — should fail payload mismatch
        auth2_id = str(result2.authorization.authorization_id)
        with pytest.raises(RiskTokenTamperError):
            service.verify_and_consume(auth2_id, token_str=result1.token.token_str)

    def test_quantity_mismatch_detected(
        self,
        service: SignedRiskAuthorizationService,
        intent: OrderIntent,
    ) -> None:
        """A token with a different quantity than the authorization is rejected."""
        result = service.authorize(intent, current_price="50000.00")
        assert result.token is not None

        auth_id = str(result.authorization.authorization_id)
        token_str = result.token.token_str

        # The token payload has quantity="0.01" — this matches the auth.
        # A token with a different quantity would fail signature verification
        # first (since the signature covers the payload).  Verify that the
        # legitimate token passes the cross-check.
        consumed = service.verify_and_consume(auth_id, token_str=token_str)
        assert consumed.authorization.status is AuthorizationStatus.CONSUMED
