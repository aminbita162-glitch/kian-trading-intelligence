"""Tests for risk policy and authorization contracts (Phase 04).

Per AD-004 (Risk Kernel): deterministic safety validation.
Per AD-013: enforce hard limits for exposure, daily loss, drawdown,
concentration, volatility, liquidity.
Per Section 05.4: risk reservations are concurrency-safe.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from contracts.risk import (
    AuthorizationStatus,
    ReservationId,
    ReservationStatus,
    RiskAssessment,
    RiskAuthorization,
    RiskAuthorizationId,
    RiskPolicy,
    RiskPolicyId,
    RiskPolicyStatus,
    RiskReservation,
)


class TestRiskPolicyId:
    def test_generated_ids_are_unique(self) -> None:
        id1 = RiskPolicyId.generate()
        id2 = RiskPolicyId.generate()
        assert id1 != id2

    def test_str_representation(self) -> None:
        pid = RiskPolicyId.generate()
        assert str(pid) == str(pid.value)


class TestRiskPolicy:
    def test_create_draft_policy(self) -> None:
        policy = RiskPolicy.create(tenant_id="tenant-1")
        assert policy.status is RiskPolicyStatus.DRAFT
        assert policy.version == 1
        assert policy.activated_at is None

    def test_activate_policy(self) -> None:
        policy = RiskPolicy.create(tenant_id="tenant-1")
        activated = policy.activate()
        assert activated.status is RiskPolicyStatus.ACTIVE
        assert activated.activated_at is not None

    def test_cannot_activate_non_draft(self) -> None:
        policy = RiskPolicy.create(tenant_id="tenant-1")
        activated = policy.activate()
        with pytest.raises(ValueError, match="Cannot activate"):
            activated.activate()

    def test_supersede_policy(self) -> None:
        policy = RiskPolicy.create(tenant_id="tenant-1")
        activated = policy.activate()
        superseded = activated.supersede()
        assert superseded.status is RiskPolicyStatus.SUPERSEDED

    def test_cannot_supersede_non_active(self) -> None:
        policy = RiskPolicy.create(tenant_id="tenant-1")
        with pytest.raises(ValueError, match="Cannot supersede"):
            policy.supersede()

    def test_custom_limits(self) -> None:
        policy = RiskPolicy.create(
            tenant_id="tenant-1",
            version=2,
            max_position_value="50000.00",
            max_daily_loss="1000.00",
            max_drawdown="2000.00",
            max_concentration_pct="10.0",
            max_position_per_symbol=5,
            min_liquidity_usd="5000.00",
            max_volatility="0.03",
        )
        assert policy.version == 2
        assert policy.max_position_value == "50000.00"
        assert policy.max_concentration_pct == "10.0"

    def test_invalid_version_rejected(self) -> None:
        with pytest.raises(ValueError, match="Version must be"):
            RiskPolicy(tenant_id="t1", policy_id=RiskPolicyId.generate(), version=0)

    def test_invalid_exposure_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_position_value"):
            RiskPolicy(
                policy_id=RiskPolicyId.generate(),
                tenant_id="t1",
                version=1,
                max_position_value="0",
            )

    def test_invalid_concentration_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_concentration_pct"):
            RiskPolicy(
                policy_id=RiskPolicyId.generate(),
                tenant_id="t1",
                version=1,
                max_concentration_pct="0",
            )

    def test_invalid_concentration_too_high(self) -> None:
        with pytest.raises(ValueError, match="max_concentration_pct"):
            RiskPolicy(
                policy_id=RiskPolicyId.generate(),
                tenant_id="t1",
                version=1,
                max_concentration_pct="150",
            )

    def test_naive_created_at_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            RiskPolicy(
                policy_id=RiskPolicyId.generate(),
                tenant_id="t1",
                version=1,
                created_at=datetime.now(),
            )


class TestRiskAuthorization:
    def _make_auth(self, **overrides: object) -> RiskAuthorization:
        defaults: dict[str, object] = {
            "authorization_id": RiskAuthorizationId.generate(),
            "tenant_id": "tenant-1",
            "policy_id": RiskPolicyId.generate(),
            "policy_version": 1,
            "intent_id": str(uuid4()),
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": "1.0",
            "status": AuthorizationStatus.APPROVED,
        }
        defaults.update(overrides)
        return RiskAuthorization(**defaults)  # type: ignore[arg-type]

    def test_approved_is_valid(self) -> None:
        auth = self._make_auth()
        assert auth.is_valid
        assert auth.is_exposure_increasing

    def test_expired_not_valid(self) -> None:
        auth = self._make_auth(
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert not auth.is_valid
        assert auth.is_expired

    def test_consume_approved(self) -> None:
        auth = self._make_auth()
        consumed = auth.consume()
        assert consumed.status is AuthorizationStatus.CONSUMED
        assert consumed.consumed_at is not None

    def test_cannot_consumed_denied(self) -> None:
        auth = self._make_auth(status=AuthorizationStatus.DENIED)
        with pytest.raises(ValueError, match="Cannot consume"):
            auth.consume()

    def test_cancel(self) -> None:
        auth = self._make_auth()
        cancelled = auth.cancel("test cancel")
        assert cancelled.status is AuthorizationStatus.CANCELLED
        assert cancelled.reason == "test cancel"

    def test_sell_not_exposure_increasing(self) -> None:
        auth = self._make_auth(side="sell")
        assert not auth.is_exposure_increasing

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid side"):
            self._make_auth(side="invalid")

    def test_invalid_quantity_rejected(self) -> None:
        with pytest.raises(ValueError, match="Quantity must be positive"):
            self._make_auth(quantity="0")


class TestRiskReservation:
    def _make_reservation(self, **overrides: object) -> RiskReservation:
        defaults: dict[str, object] = {
            "reservation_id": ReservationId.generate(),
            "tenant_id": "tenant-1",
            "authorization_id": RiskAuthorizationId.generate(),
            "intent_id": str(uuid4()),
            "reserved_value": "5000.00",
        }
        defaults.update(overrides)
        return RiskReservation(**defaults)  # type: ignore[arg-type]

    def test_active_is_active(self) -> None:
        res = self._make_reservation()
        assert res.is_active
        assert res.status is ReservationStatus.ACTIVE

    def test_release(self) -> None:
        res = self._make_reservation()
        released = res.release()
        assert released.status is ReservationStatus.RELEASED
        assert released.released_at is not None

    def test_consume(self) -> None:
        res = self._make_reservation()
        consumed = res.consume()
        assert consumed.status is ReservationStatus.CONSUMED

    def test_expired_not_active(self) -> None:
        res = self._make_reservation(
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert not res.is_active
        assert res.is_expired

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="reserved_value must be positive"):
            self._make_reservation(reserved_value="0")


class TestRiskAssessment:
    def test_authorized_assessment(self) -> None:
        assessment = RiskAssessment(
            authorized=True,
            reason="passed",
            checked_limits=["exposure_limit"],
        )
        assert assessment.authorized
        assert "exposure_limit" in assessment.checked_limits

    def test_denied_assessment(self) -> None:
        assessment = RiskAssessment(
            authorized=False,
            reason="exceeded",
        )
        assert not assessment.authorized
        assert assessment.reason == "exceeded"
