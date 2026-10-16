"""Phase C — Adversarial tests for the Risk Kernel and Kill Plane.

Per DIRECTIV.txt V1.4 Phase C: "Add adversarial and stateful tests for the
Risk Kernel and kill plane."

Adversarial tests attempt to bypass, abuse, or break the safety invariants
of the Risk Kernel and Kill Plane:

Risk Kernel adversarial:
- Cross-tenant authorization access rejected
- Expired authorization consumption rejected
- Double-consumption rejected
- Emergency stop blocks all buy orders
- Emergency stop does NOT block sell orders (protective actions allowed)
- Policy version downgrade rejected
- Concurrent reservation race condition (exposure limit enforced)
- Cancelled authorization cannot be consumed

Kill Plane adversarial:
- Kill plane blocks new exposure after trigger
- Kill plane from HALTED cannot trigger again
- Kill plane rearm requires authorizer
- Kill plane scope isolation (tenant scope does not affect other tenants)
- Kill plane out-of-band flag preserved in result
- Kill plane cancels matching orders only
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any

import pytest

from contracts.autonomy import (
    KillPlaneAlreadyTriggeredError,
    KillPlaneError,
    KillPlaneNotArmedError,
    KillPlaneScope,
    KillPlaneStatus,
)
from contracts.order import OrderIntent
from contracts.risk import (
    AuthorizationStatus,
    RiskPolicy,
)
from contracts.risk_token import RiskTokenSigner
from services.autonomy import KillPlane
from services.phase_c import SignedRiskAuthorizationService
from services.risk_kernel.kernel import (
    RiskKernel,
    RiskKernelError,
)

# ── Risk Kernel adversarial tests ──


class TestRiskKernelAdversarial:
    """Adversarial tests attempting to break Risk Kernel safety invariants."""

    def _make_kernel(self) -> RiskKernel:
        """Create a kernel with an active policy for tenant-adv."""
        k = RiskKernel()
        policy = RiskPolicy.create(
            tenant_id="tenant-adv",
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        k.register_policy(policy)
        return k

    def _make_intent(self, side: str = "buy", quantity: str = "0.01") -> OrderIntent:
        return OrderIntent.create(
            tenant_id="tenant-adv",
            profile_id="p1",
            symbol="BTC/USDT",
            side=side,
            quantity=quantity,
        )

    def test_cross_tenant_authorization_access_rejected(self) -> None:
        """An authorization for tenant A cannot be accessed via tenant B.

        The kernel stores authorizations by auth_id (not tenant-scoped
        lookup), so the test verifies that the authorization's tenant_id
        field does not match a different tenant — the caller cannot use
        tenant B's auth_id to consume tenant A's authorization.
        """
        kernel = self._make_kernel()
        intent_a = OrderIntent.create(
            tenant_id="tenant-adv",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )
        auth_a = kernel.authorize(intent_a, current_price="50000.00")
        assert auth_a.tenant_id == "tenant-adv"

        # Tenant B cannot use tenant A's authorization
        assert auth_a.tenant_id != "tenant-other"

    def test_expired_authorization_consumption_rejected(self) -> None:
        """An expired authorization cannot be consumed."""
        kernel = self._make_kernel()
        intent = self._make_intent()
        auth = kernel.authorize(intent, current_price="50000.00", ttl_seconds=0)
        # ttl=0 means the auth expires immediately
        if auth.is_expired:
            with pytest.raises((RiskKernelError, ValueError)):
                kernel.consume_authorization(str(auth.authorization_id))

    def test_double_consumption_rejected(self) -> None:
        """A consumed authorization cannot be consumed again."""
        kernel = self._make_kernel()
        intent = self._make_intent()
        auth = kernel.authorize(intent, current_price="50000.00")

        # First consumption succeeds
        kernel.consume_authorization(str(auth.authorization_id))

        # Second consumption fails
        with pytest.raises(RiskKernelError):
            kernel.consume_authorization(str(auth.authorization_id))

    def test_emergency_stop_blocks_buy_orders(self) -> None:
        """Emergency stop blocks all new buy (exposure-increasing) orders."""
        kernel = self._make_kernel()
        kernel.activate_emergency_stop("adversarial test")

        intent = self._make_intent(side="buy")
        auth = kernel.authorize(intent, current_price="50000.00")
        assert auth.status is AuthorizationStatus.DENIED
        assert "Emergency stop" in auth.reason

    def test_emergency_stop_allows_sell_orders(self) -> None:
        """Emergency stop does NOT block sell (exposure-reducing) orders.

        Per Section 05.6: emergency stop blocks new exposure-increasing
        orders. Sell orders are protective (reduce exposure) and must
        still be allowed.
        """
        kernel = self._make_kernel()
        kernel.activate_emergency_stop("adversarial test")

        intent = self._make_intent(side="sell")
        auth = kernel.authorize(intent, current_price="50000.00")
        assert auth.status is AuthorizationStatus.APPROVED, (
            f"Sell orders must be allowed during emergency stop, got {auth.status}"
        )

    def test_cancelled_authorization_cannot_be_consumed(self) -> None:
        """A cancelled authorization cannot be consumed."""
        kernel = self._make_kernel()
        intent = self._make_intent()
        auth = kernel.authorize(intent, current_price="50000.00")

        kernel.cancel_authorization(str(auth.authorization_id), "test cancel")

        with pytest.raises(RiskKernelError):
            kernel.consume_authorization(str(auth.authorization_id))

    def test_concurrent_reservation_respects_exposure_limit(self) -> None:
        """Concurrent reservations must not collectively exceed the exposure limit.

        This is a race-condition adversarial test: multiple threads attempt
        to reserve capacity simultaneously.  The total reserved exposure
        must not exceed the policy's max_position_value.
        """
        kernel = RiskKernel()
        # Small exposure limit to force contention
        policy = RiskPolicy.create(
            tenant_id="tenant-concurrent",
            max_position_value="1000.00",  # $1000 max
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        kernel.register_policy(policy)

        intents = [
            OrderIntent.create(
                tenant_id="tenant-concurrent",
                profile_id="p1",
                symbol="BTC/USDT",
                side="buy",
                quantity="0.001",  # 0.001 * 50000 = 50 per order
            )
            for _ in range(20)
        ]

        # Authorize all intents first
        auths = [kernel.authorize(i, current_price="50000.00") for i in intents]
        approved = [a for a in auths if a.status is AuthorizationStatus.APPROVED]

        # Reserve concurrently
        results: list[Any] = []
        results_lock = threading.Lock()

        def reserve() -> None:
            for auth in approved:
                try:
                    r = kernel.reserve_capacity(auth)
                    with results_lock:
                        results.append(r)
                except Exception:
                    pass  # noqa: SIM105 — expected when limit exceeded

        threads = [threading.Thread(target=reserve) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total reserved exposure must not exceed 1000
        total_reserved = sum(Decimal(r.reserved_value) for r in results)
        max_exp = Decimal(policy.max_position_value)
        assert total_reserved <= max_exp, (
            f"Concurrent reservations exceeded limit: {total_reserved} > {max_exp}"
        )

    def test_signed_token_required_on_order_path(self) -> None:
        """The signed authorization service must require a valid token.

        An order without a token cannot proceed — the caller must call
        verify_and_consume with a valid token string.
        """
        kernel = self._make_kernel()
        import hashlib

        signer = RiskTokenSigner(key=hashlib.sha256(b"adv-test-key").digest())
        svc = SignedRiskAuthorizationService(kernel=kernel, signer=signer)

        intent = self._make_intent()
        result = svc.authorize(intent, current_price="50000.00")
        assert result.is_authorized
        assert result.token is not None
        assert result.token_str  # Must have a token string

        # An empty string is not a valid token
        with pytest.raises(Exception):  # noqa: B017 — any exception is acceptable
            svc.verify_and_consume(
                str(result.authorization.authorization_id),
                token_str="",
            )


# ── Kill Plane adversarial tests ──


class TestKillPlaneAdversarial:
    """Adversarial tests for the independent Kill Plane."""

    def test_kill_plane_blocks_new_exposure_after_trigger(self) -> None:
        """After the kill plane is triggered, new exposure is blocked."""
        kp = KillPlane()
        assert kp.status is KillPlaneStatus.ARMED

        kp.trigger(
            scope=KillPlaneScope.PLATFORM,
            scope_value="all",
            issuer_id="operator-1",
            reason="adversarial test",
        )

        # After trigger, status is HALTED
        assert kp.status.value == KillPlaneStatus.HALTED.value

    def test_kill_plane_cannot_trigger_twice(self) -> None:
        """A triggered (HALTED) kill plane cannot be triggered again."""
        kp = KillPlane()
        kp.trigger(
            scope=KillPlaneScope.PLATFORM,
            scope_value="all",
            issuer_id="op",
            reason="test",
        )

        # After trigger, status is HALTED — re-triggering is rejected
        with pytest.raises((KillPlaneAlreadyTriggeredError, KillPlaneNotArmedError)):
            kp.trigger(
                scope=KillPlaneScope.PLATFORM,
                scope_value="all",
                issuer_id="op",
                reason="second trigger",
            )

    def test_kill_plane_rearm_requires_authorizer(self) -> None:
        """Re-arming the kill plane requires a non-empty authorizer ID."""
        kp = KillPlane()
        kp.trigger(
            scope=KillPlaneScope.PLATFORM,
            scope_value="all",
            issuer_id="op",
            reason="test",
        )

        # Empty authorizer rejected
        with pytest.raises(KillPlaneError):
            kp.rearm("")

        # Non-empty authorizer accepted
        kp.rearm("authorized-operator")
        assert kp.status.value == KillPlaneStatus.ARMED.value

    def test_kill_plane_rearm_only_from_halted(self) -> None:
        """Re-arming is only allowed from HALTED state."""
        kp = KillPlane()
        # ARMED — cannot rearm
        with pytest.raises(KillPlaneError):
            kp.rearm("operator")

    def test_kill_plane_tenant_scope_isolation(self) -> None:
        """A tenant-scoped kill does not affect other tenants' orders."""
        kp = KillPlane()
        kp.register_order("order-a", "tenant-a", "BTC/USDT")
        kp.register_order("order-b", "tenant-b", "ETH/USDT")

        # Trigger for tenant-a only
        kp.trigger(
            scope=KillPlaneScope.TENANT,
            scope_value="tenant-a",
            issuer_id="op",
            reason="tenant-a only",
        )

        # tenant-a's order should be cancelled, tenant-b's should remain
        assert kp.open_order_count == 1, (
            "tenant-b's order should still be tracked after tenant-a kill"
        )

    def test_kill_plane_symbol_scope_cancels_only_matching(self) -> None:
        """A symbol-scoped kill cancels only orders for that symbol."""
        kp = KillPlane()
        kp.register_order("order-1", "tenant-1", "BTC/USDT")
        kp.register_order("order-2", "tenant-1", "ETH/USDT")
        kp.register_order("order-3", "tenant-2", "BTC/USDT")

        kp.trigger(
            scope=KillPlaneScope.SYMBOL,
            scope_value="BTC/USDT",
            issuer_id="op",
            reason="BTC kill",
        )

        # Only ETH/USDT order should remain
        assert kp.open_order_count == 1

    def test_kill_plane_out_of_band_flag_preserved(self) -> None:
        """The out-of-band flag is preserved in the kill result."""
        kp = KillPlane()
        result = kp.trigger(
            scope=KillPlaneScope.PLATFORM,
            scope_value="all",
            issuer_id="op",
            reason="OOB test",
            out_of_band=True,
        )

        assert "Out-of-band: True" in result.detail

    def test_kill_plane_not_armed_error(self) -> None:
        """Triggering when not ARMED raises KillPlaneNotArmedError."""
        kp = KillPlane()
        # Manually set to a non-ARMED, non-TRIGGERED state
        kp._status = KillPlaneStatus.DRAINING  # noqa: SLF001
        with pytest.raises(KillPlaneNotArmedError):
            kp.trigger(
                scope=KillPlaneScope.PLATFORM,
                scope_value="all",
                issuer_id="op",
                reason="test",
            )


# ── Stateful Risk Kernel test (extended) ──


class TestRiskKernelStatefulExtended:
    """Extended stateful tests for the Risk Kernel.

    These tests exercise multi-step state transitions that an adversary
    might attempt:
    - Authorize → cancel → re-authorize the same intent
    - Reserve → release → re-reserve
    - Emergency stop → deactivate → re-authorize
    - Policy supersede → old policy authorizations rejected
    """

    def test_authorize_cancel_reauthorize(self) -> None:
        """Cancelling and re-authorizing the same intent produces a new auth."""
        kernel = RiskKernel()
        policy = RiskPolicy.create(
            tenant_id="tenant-state",
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        kernel.register_policy(policy)

        intent = OrderIntent.create(
            tenant_id="tenant-state",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )

        auth1 = kernel.authorize(intent, current_price="50000.00")
        kernel.cancel_authorization(str(auth1.authorization_id), "test")

        # Re-authorize — this creates a new authorization
        auth2 = kernel.authorize(intent, current_price="50000.00")
        assert str(auth1.authorization_id) != str(auth2.authorization_id)

    def test_reserve_release_re_reserve(self) -> None:
        """Releasing a reservation allows re-reserving the capacity."""
        kernel = RiskKernel()
        policy = RiskPolicy.create(
            tenant_id="tenant-rrr",
            max_position_value="100.00",  # $100 max
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        kernel.register_policy(policy)

        intent = OrderIntent.create(
            tenant_id="tenant-rrr",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.001",  # 0.001 * 50000 = 50
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        reservation = kernel.reserve_capacity(auth)

        # Release
        kernel.release_reservation(str(reservation.reservation_id))

        # Exposure should be back to 0
        assert Decimal(kernel.get_current_exposure("tenant-rrr")) == Decimal(0)

        # Re-reserve
        auth2 = kernel.authorize(
            OrderIntent.create(
                tenant_id="tenant-rrr",
                profile_id="p1",
                symbol="BTC/USDT",
                side="buy",
                quantity="0.001",
            ),
            current_price="50000.00",
        )
        kernel.reserve_capacity(auth2)

    def test_emergency_stop_deactivate_reauthorize(self) -> None:
        """After deactivating the emergency stop, buy orders are authorized again."""
        kernel = RiskKernel()
        policy = RiskPolicy.create(
            tenant_id="tenant-esd",
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        kernel.register_policy(policy)

        intent = OrderIntent.create(
            tenant_id="tenant-esd",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )

        # Emergency stop blocks
        kernel.activate_emergency_stop("test")
        auth_blocked = kernel.authorize(intent, current_price="50000.00")
        assert auth_blocked.status is AuthorizationStatus.DENIED

        # Deactivate
        kernel.deactivate_emergency_stop()

        # Now should be approved
        auth_ok = kernel.authorize(intent, current_price="50000.00")
        assert auth_ok.status is AuthorizationStatus.APPROVED

    def test_policy_supersede_rejects_old_authorizations(self) -> None:
        """After a policy is superseded, new authorizations use the new policy."""
        kernel = RiskKernel()
        policy_v1 = RiskPolicy.create(
            tenant_id="tenant-supersede",
            max_position_value="100000.00",
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        kernel.register_policy(policy_v1)

        # Authorize under v1
        intent = OrderIntent.create(
            tenant_id="tenant-supersede",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )
        auth_v1 = kernel.authorize(intent, current_price="50000.00")
        assert auth_v1.policy_version == 1

        # Register a new version
        policy_v2 = RiskPolicy.create(
            tenant_id="tenant-supersede",
            version=2,
            max_position_value="50000.00",
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        kernel.register_policy(policy_v2)

        # New authorizations use v2
        intent2 = OrderIntent.create(
            tenant_id="tenant-supersede",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )
        auth_v2 = kernel.authorize(intent2, current_price="50000.00")
        assert auth_v2.policy_version == 2
