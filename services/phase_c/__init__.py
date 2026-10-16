"""Signed risk authorization service — Phase C Safety Hardening.

Per DIRECTIV.txt V1.4 Phase C: "Activate signed risk authorization tokens on
the simulation order path (short-lived, single-use, cryptographically signed,
bound to exact order parameters)."

This module provides :class:`SignedRiskAuthorizationService`, which wraps the
:class:`~services.risk_kernel.kernel.RiskKernel`'s authorization flow with
cryptographic signing.  When an order is authorized, a signed token
(:class:`~contracts.risk_token.SignedRiskToken`) is issued bound to the exact
order parameters (symbol, side, quantity, max_price, tenant).  The token is
short-lived (30s default) and single-use (nonce replay protection).  Before
the order is submitted to the exchange, the token must be verified and
consumed — a tampered, expired, or replayed token is rejected.

This closes the gap between the E4 signed-token infrastructure (which existed
as a standalone module) and the actual simulation order path (which used
plain :class:`~contracts.risk.RiskAuthorization` without signature verification).

Architecture Decisions: AD-036 (signed risk tokens), AD-004 (independent
Risk Kernel), AD-014 (deterministic execution).
"""

from __future__ import annotations

import hashlib
from typing import Any

from contracts.order import OrderIntent
from contracts.phase_c import SignedAuthorization
from contracts.risk import (
    AuthorizationStatus,
    RiskAuthorization,
)
from contracts.risk_token import (
    RiskTokenPayload,
    RiskTokenSigner,
    RiskTokenTamperError,
)


def _default_signer_key() -> bytes:
    """Derive a deterministic signing key for dev/test."""
    return hashlib.sha256(b"phase-c-signed-auth-key-change-in-prod").digest()


def _auth_to_payload(auth: RiskAuthorization) -> RiskTokenPayload:
    """Convert a RiskAuthorization to a RiskTokenPayload."""
    return RiskTokenPayload(
        auth_id=str(auth.authorization_id),
        tenant_id=auth.tenant_id,
        policy_id=str(auth.policy_id),
        policy_version=auth.policy_version,
        intent_id=auth.intent_id,
        symbol=auth.symbol,
        side=auth.side,
        quantity=auth.quantity,
        max_price=auth.max_price,
    )


class SignedRiskAuthorizationService:
    """Activates signed risk authorization tokens on the simulation order path.

    Per Phase C: the service wraps the RiskKernel's authorize → consume flow
    with cryptographic signing.  When :meth:`authorize` is called, the
    underlying kernel assesses and authorizes the order; if approved, a signed
    token is issued bound to the exact order parameters.  When
    :meth:`verify_and_consume` is called, the token is verified (signature,
    expiry, replay) and the underlying kernel authorization is consumed.

    The service enforces the invariant: no order may proceed to exchange
    submission without a valid signed token.
    """

    def __init__(
        self,
        kernel: Any,
        *,
        signer: RiskTokenSigner | None = None,
        ttl_seconds: int = 30,
    ) -> None:
        self._kernel = kernel
        self._signer = signer or RiskTokenSigner(key=_default_signer_key())
        self._ttl_seconds = ttl_seconds
        self._auth_to_token: dict[str, str] = {}  # auth_id → token_str

    @property
    def kernel(self) -> Any:
        """Access the underlying risk kernel."""
        return self._kernel

    @property
    def signer(self) -> RiskTokenSigner:
        """Access the token signer."""
        return self._signer

    def authorize(
        self,
        intent: OrderIntent,
        *,
        current_price: str,
        session: Any | None = None,
    ) -> SignedAuthorization:
        """Authorize an order and issue a signed token.

        Delegates to the underlying kernel's authorize() method.  If the
        authorization is APPROVED, issues a signed token bound to the exact
        order parameters.  If DENIED, returns a SignedAuthorization with
        token=None.

        Per Phase C: the token is short-lived (ttl_seconds) and single-use.
        """
        auth = self._kernel.authorize(
            intent,
            current_price=current_price,
            session=session,
            ttl_seconds=self._ttl_seconds,
        )

        if auth.status is not AuthorizationStatus.APPROVED:
            return SignedAuthorization(authorization=auth, token=None)

        # Issue signed token bound to exact order parameters
        payload = _auth_to_payload(auth)
        tenant_aad = auth.tenant_id
        token = self._signer.issue(
            payload,
            ttl_seconds=self._ttl_seconds,
            tenant_aad=tenant_aad,
        )
        self._auth_to_token[str(auth.authorization_id)] = token.token_str

        return SignedAuthorization(authorization=auth, token=token)

    def verify_and_consume(
        self,
        auth_id: str,
        *,
        token_str: str,
    ) -> SignedAuthorization:
        """Verify a signed token and consume the underlying authorization.

        Performs:
        1. Token verification (signature, expiry, replay).
        2. Cross-check that the token payload matches the authorization.
        3. Consume the underlying kernel authorization.

        Raises:
            RiskTokenTamperError: If the signature is invalid.
            RiskTokenExpiredError: If the token has expired.
            RiskTokenReplayError: If the token has already been consumed.
            RiskTokenMalformedError: If the token is structurally invalid.
            ValueError: If the token payload does not match the authorization.
        """
        # Look up the authorization from the kernel
        auth = self._kernel.get_authorization(auth_id)

        # Verify the signed token (this also checks replay)
        tenant_aad = auth.tenant_id
        token = self._signer.verify(token_str, tenant_aad=tenant_aad, check_replay=True)

        # Cross-check: token payload must match the authorization
        if token.payload.auth_id != str(auth.authorization_id):
            raise RiskTokenTamperError(
                f"Token auth_id {token.payload.auth_id} does not match "
                f"authorization {auth.authorization_id}."
            )
        if token.payload.intent_id != auth.intent_id:
            raise RiskTokenTamperError(
                f"Token intent_id {token.payload.intent_id} does not match "
                f"authorization intent {auth.intent_id}."
            )
        if token.payload.symbol != auth.symbol:
            raise RiskTokenTamperError(
                f"Token symbol {token.payload.symbol} does not match "
                f"authorization symbol {auth.symbol}."
            )
        if token.payload.side != auth.side:
            raise RiskTokenTamperError(
                f"Token side {token.payload.side} does not match authorization side {auth.side}."
            )
        if token.payload.quantity != auth.quantity:
            raise RiskTokenTamperError(
                f"Token quantity {token.payload.quantity} does not match "
                f"authorization quantity {auth.quantity}."
            )

        # Mark the nonce as consumed (single-use)
        self._signer._consumed_nonces.add(token.nonce)  # noqa: SLF001

        # Consume the underlying kernel authorization
        consumed_auth = self._kernel.consume_authorization(auth_id)

        return SignedAuthorization(authorization=consumed_auth, token=token)

    def verify_token(
        self,
        token_str: str,
        *,
        tenant_aad: str = "",
    ) -> RiskTokenPayload:
        """Verify a token without consuming it (inspection only).

        Returns the verified payload.  Raises on tamper/expiry/replay.
        """
        token = self._signer.verify(token_str, tenant_aad=tenant_aad, check_replay=True)
        return token.payload

    def reset(self) -> None:
        """Reset the signer's nonce cache (for testing)."""
        self._signer.reset()
        self._auth_to_token.clear()
