"""Tests for the Risk Kernel service (Phase 04).

Per AD-004: the Risk Kernel is a deterministic safety service.
Per AD-013: enforce hard limits.
Per Section 05.4: concurrency-safe risk reservations.
Per Section 05.6: emergency stop blocks new exposure-increasing orders.
"""

from decimal import Decimal

import pytest

from contracts.enums import OrderState, SessionState
from contracts.exchange import ClientOrderId, FillResult
from contracts.order import OrderIntent
from contracts.risk import (
    AuthorizationStatus,
    ReservationStatus,
    RiskPolicy,
    RiskPolicyStatus,
)
from contracts.trading import TradingSession
from services.risk_kernel.kernel import (
    PolicyNotActiveError,
    RiskAuthorizationNotFound,
    RiskKernel,
    RiskKernelError,
)


@pytest.fixture
def kernel() -> RiskKernel:
    """Fresh RiskKernel with an active policy."""
    k = RiskKernel()
    policy = RiskPolicy.create(
        tenant_id="tenant-1",
        max_position_value="100000.00",
        max_daily_loss="5000.00",
        max_drawdown="10000.00",
        max_concentration_pct="100.0",
        max_position_per_symbol=10,
    ).activate()
    k.register_policy(policy)
    return k


@pytest.fixture
def policy() -> RiskPolicy:
    """Active risk policy."""
    return RiskPolicy.create(tenant_id="tenant-1").activate()


class TestRiskPolicyManagement:
    def test_register_and_get_policy(self, kernel: RiskKernel) -> None:
        policy = kernel.get_active_policy("tenant-1")
        assert policy.status is RiskPolicyStatus.ACTIVE

    def test_no_active_policy_raises(self) -> None:
        k = RiskKernel()
        with pytest.raises(PolicyNotActiveError):
            k.get_active_policy("tenant-1")

    def test_policy_versioning(self, kernel: RiskKernel) -> None:
        history = kernel.get_policy_history("tenant-1")
        assert len(history) == 1
        # Add a new version
        v2 = RiskPolicy.create(tenant_id="tenant-1", version=2).activate()
        kernel.register_policy(v2)
        history = kernel.get_policy_history("tenant-1")
        assert len(history) == 2
        active = kernel.get_active_policy("tenant-1")
        assert active.version == 2


class TestRiskAssessment:
    def test_approve_valid_order(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        assessment = kernel.assess(intent, current_price="50000.00")
        assert assessment.authorized
        assert "exposure_limit" in assessment.checked_limits

    def test_deny_exposure_exceeded(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="3.0",  # 3 * 50000 = 150000 > 100000 limit
        )
        assessment = kernel.assess(intent, current_price="50000.00")
        assert not assessment.authorized
        assert "exposure_limit" in assessment.checked_limits

    def test_deny_daily_loss_exceeded(self, kernel: RiskKernel) -> None:
        # Simulate daily loss by recording fills
        fill = FillResult(
            fill_id="fill-1",
            client_order_id=ClientOrderId("test-1"),
            symbol="BTC/USDT",
            side="sell",
            filled_quantity="1.0",
            fill_price="50000.00",
            fee="6000.00",  # exceeds max_daily_loss of 5000
        )
        kernel.record_fill("tenant-1", fill)
        kernel._reset_daily_loss_if_needed("tenant-1")
        # Manually set the loss to trigger the check
        kernel._daily_loss["tenant-1"] = Decimal("6000.00")

        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.1",
        )
        assessment = kernel.assess(intent, current_price="50000.00")
        assert not assessment.authorized
        assert "daily_loss_limit" in assessment.checked_limits

    def test_sell_allowed_when_exposure_exceeded(self, kernel: RiskKernel) -> None:
        # Set current exposure to the limit
        kernel._current_exposure["tenant-1"] = Decimal("100000.00")
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="sell",  # Sells don't increase exposure
            quantity="1.0",
        )
        assessment = kernel.assess(intent, current_price="50000.00")
        assert assessment.authorized

    def test_concentration_limit(self) -> None:
        """Concentration limit should block orders that exceed the percentage."""
        k = RiskKernel()
        policy = RiskPolicy.create(
            tenant_id="tenant-1",
            max_concentration_pct="25.0",
        ).activate()
        k.register_policy(policy)
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.6",  # 0.6 * 50000 = 30000, 30000/100000 = 30% > 25%
        )
        assessment = k.assess(intent, current_price="50000.00")
        assert not assessment.authorized
        assert "concentration_limit" in assessment.checked_limits

    def test_position_count_limit(self, kernel: RiskKernel) -> None:
        # Set position count to the limit
        kernel._position_count["tenant-1"] = {"BTC/USDT": 10}
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.1",
        )
        assessment = kernel.assess(intent, current_price="50000.00")
        assert not assessment.authorized
        assert "position_count_limit" in assessment.checked_limits

    def test_order_state_must_be_created_or_validated(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.1",
        )
        # Manually set state to SUBMITTED (should be rejected)
        intent.state = OrderState.SUBMITTED
        assessment = kernel.assess(intent, current_price="50000.00")
        assert not assessment.authorized
        assert "order_state" in assessment.checked_limits

    def test_deterministic_assessment(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        a1 = kernel.assess(intent, current_price="50000.00")
        a2 = kernel.assess(intent, current_price="50000.00")
        assert a1.authorized == a2.authorized
        assert a1.checked_limits == a2.checked_limits


class TestRiskAuthorization:
    def test_authorize_approved(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        assert auth.status is AuthorizationStatus.APPROVED
        assert auth.is_valid
        assert auth.is_exposure_increasing
        assert auth.max_price == "50000.00"

    def test_authorize_denied(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="3.0",  # exceeds exposure
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        assert auth.status is AuthorizationStatus.DENIED
        assert auth.reason

    def test_get_authorization(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        retrieved = kernel.get_authorization(str(auth.authorization_id))
        assert retrieved.authorization_id == auth.authorization_id

    def test_get_authorization_not_found(self, kernel: RiskKernel) -> None:
        with pytest.raises(RiskAuthorizationNotFound):
            kernel.get_authorization("nonexistent")

    def test_get_authorization_for_intent(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        kernel.authorize(intent, current_price="50000.00")
        auth = kernel.get_authorization_for_intent(str(intent.intent_id))
        assert auth.intent_id == str(intent.intent_id)

    def test_consume_authorization(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        consumed = kernel.consume_authorization(str(auth.authorization_id))
        assert consumed.status is AuthorizationStatus.CONSUMED

    def test_cannot_consume_denied(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="10.0",  # exceeds
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        with pytest.raises(RiskKernelError, match="Cannot consume"):
            kernel.consume_authorization(str(auth.authorization_id))

    def test_cancel_authorization(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        cancelled = kernel.cancel_authorization(str(auth.authorization_id))
        assert cancelled.status is AuthorizationStatus.CANCELLED


class TestRiskReservations:
    def test_reserve_capacity(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        reservation = kernel.reserve_capacity(auth)
        assert reservation.is_active
        assert reservation.status is ReservationStatus.ACTIVE

    def test_release_reservation(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        reservation = kernel.reserve_capacity(auth)
        released = kernel.release_reservation(str(reservation.reservation_id))
        assert released.status is ReservationStatus.RELEASED

    def test_cannot_release_twice(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        reservation = kernel.reserve_capacity(auth)
        kernel.release_reservation(str(reservation.reservation_id))
        with pytest.raises(RiskKernelError, match="not active"):
            kernel.release_reservation(str(reservation.reservation_id))

    def test_consume_reservation(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        reservation = kernel.reserve_capacity(auth)
        consumed = kernel.consume_reservation(str(reservation.reservation_id))
        assert consumed.status is ReservationStatus.CONSUMED

    def test_reservation_updates_exposure(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        kernel.reserve_capacity(auth, reserved_value="50000.00")
        assert kernel.get_current_exposure("tenant-1") == "50000.00"

    def test_release_reduces_exposure(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        reservation = kernel.reserve_capacity(auth, reserved_value="50000.00")

        assert Decimal(kernel.get_current_exposure("tenant-1")) == Decimal("50000.00")
        kernel.release_reservation(str(reservation.reservation_id))
        assert Decimal(kernel.get_current_exposure("tenant-1")) == Decimal(0)

    def test_cannot_reserve_for_denied_auth(self, kernel: RiskKernel) -> None:
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="10.0",  # exceeds
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        assert auth.status is AuthorizationStatus.DENIED
        with pytest.raises(RiskKernelError, match="Cannot reserve"):
            kernel.reserve_capacity(auth)


class TestEmergencyStop:
    def test_activate_and_block_buys(self, kernel: RiskKernel) -> None:
        assert not kernel.emergency_stop.is_active
        kernel.activate_emergency_stop("test emergency")
        assert kernel.emergency_stop.is_active
        assert kernel.emergency_stop.reason == "test emergency"

        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.1",
        )
        assessment = kernel.assess(intent, current_price="50000.00")
        assert not assessment.authorized
        assert "emergency_stop" in assessment.checked_limits

    def test_emergency_stop_allows_sells(self, kernel: RiskKernel) -> None:
        kernel.activate_emergency_stop("test")
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="sell",
            quantity="0.1",
        )
        assessment = kernel.assess(intent, current_price="50000.00")
        assert assessment.authorized  # Sells are protective actions

    def test_deactivate_emergency_stop(self, kernel: RiskKernel) -> None:
        kernel.activate_emergency_stop("test")
        assert kernel.emergency_stop.is_active
        kernel.deactivate_emergency_stop()
        assert not kernel.emergency_stop.is_active

    def test_emergency_stop_activated_at(self, kernel: RiskKernel) -> None:
        kernel.activate_emergency_stop("test")
        assert kernel.emergency_stop.activated_at is not None
        assert kernel.emergency_stop.activated_at.tzinfo is not None


class TestSessionStateChecks:
    def _make_session(self) -> TradingSession:
        return TradingSession.create(
            tenant_id="tenant-1",
            profile_id="p1",
            strategy_version="v1",
            exchange="simulated",
            instruments=["BTC/USDT"],
            capital_allocation="10000.00",
            risk_policy_id="policy-1",
        )

    def test_halted_session_blocks_orders(self, kernel: RiskKernel) -> None:
        session = self._make_session()
        scheduled = session.transition_to(SessionState.SCHEDULED)
        preflight = scheduled.transition_to(SessionState.PREFLIGHT)
        halted = preflight.transition_to(SessionState.SAFE_HALT)

        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.1",
        )
        assessment = kernel.assess(intent, current_price="50000.00", session=halted)
        assert not assessment.authorized
        assert "session_state" in assessment.checked_limits

    def test_completed_session_blocks_orders(self, kernel: RiskKernel) -> None:
        session = self._make_session()
        scheduled = session.transition_to(SessionState.SCHEDULED)
        preflight = scheduled.transition_to(SessionState.PREFLIGHT)
        awaiting = preflight.transition_to(SessionState.AWAITING_USER_APPROVAL)
        running = awaiting.transition_to(SessionState.RUNNING)
        completed = running.transition_to(SessionState.COMPLETED)

        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.1",
        )
        assessment = kernel.assess(intent, current_price="50000.00", session=completed)
        assert not assessment.authorized
