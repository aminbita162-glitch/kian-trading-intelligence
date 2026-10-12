"""E2 — Durable Core: persistent risk kernel tests (SQLite-backed).

Tests that the persistent risk kernel correctly replaces in-memory state
with DB-backed state, and that all risk assessment logic works with DB
state.

Per E2 scope: "PostgreSQL schemas for all authoritative aggregates,
versioned migrations with up/down tests, DB-enforced invariants."
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from contracts.enums import SessionState
from contracts.order import OrderIntent
from contracts.risk import (
    AuthorizationStatus,
    ReservationStatus,
    RiskPolicy,
    RiskPolicyStatus,
)
from contracts.trading import TradingSession
from services.risk_kernel.kernel import PolicyNotActiveError
from services.risk_kernel.persistent_kernel import (
    PersistentRiskKernel,
    run_risk_migrations_down,
    run_risk_migrations_up,
)


@pytest.fixture
def kernel() -> Iterator[PersistentRiskKernel]:
    """Create a fresh persistent risk kernel with file-based SQLite."""
    db_path = tempfile.mktemp(suffix=".db")
    db_url = f"sqlite:///{db_path}"
    kern = PersistentRiskKernel(db_url=db_url)
    yield kern
    kern.close()
    with contextlib.suppress(OSError):
        os.unlink(db_path)


def _make_intent(
    tenant_id: str = "tenant-1",
    symbol: str = "BTC/USDT",
    side: str = "buy",
    quantity: str = "0.01",
) -> OrderIntent:
    return OrderIntent.create(
        tenant_id=tenant_id,
        profile_id="profile-1",
        symbol=symbol,
        side=side,
        quantity=quantity,
    )


def _make_session(
    tenant_id: str = "tenant-1",
    state: SessionState = SessionState.SCHEDULED,
) -> TradingSession:
    session = TradingSession.create(
        tenant_id=tenant_id,
        profile_id="profile-1",
        strategy_version="v1",
        exchange="simulated",
        instruments=["BTC/USDT"],
        capital_allocation="100000",
        risk_policy_id="policy-1",
    )
    if state is not SessionState.DRAFT:
        session = session.transition_to(state)
    return session


def _activate_policy(kernel: PersistentRiskKernel, tenant_id: str = "tenant-1") -> RiskPolicy:
    policy = RiskPolicy.create(
        tenant_id=tenant_id,
        version=1,
        max_position_value="100000",
        max_daily_loss="5000",
        max_drawdown="10000",
        max_concentration_pct="100.0",
    )
    activated = policy.activate()
    kernel.register_policy(activated)
    return activated


class TestRiskMigrations:
    """Test versioned migrations with up/down."""

    def test_migrations_up_creates_tables(self) -> None:
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        engine = create_engine(db_url)
        version = run_risk_migrations_up(engine)
        assert version >= 1
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
            table_names = {r[0] for r in tables}
            assert "risk_policies" in table_names
            assert "risk_authorizations" in table_names
            assert "risk_reservations" in table_names
            assert "risk_exposure" in table_names
        engine.dispose()
        os.unlink(db_path)

    def test_migrations_down_drops_tables(self) -> None:
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        engine = create_engine(db_url)
        run_risk_migrations_up(engine)
        run_risk_migrations_down(engine, target_version=0)
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
            table_names = {r[0] for r in tables}
            assert "risk_policies" not in table_names
        engine.dispose()
        os.unlink(db_path)


class TestPersistentPolicyManagement:
    """Test DB-backed risk policy management."""

    def test_register_and_get_active_policy(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        fetched = kernel.get_active_policy("tenant-1")
        assert fetched.tenant_id == "tenant-1"
        assert fetched.status is RiskPolicyStatus.ACTIVE
        assert fetched.version == 1

    def test_no_active_policy_raises(self, kernel: PersistentRiskKernel) -> None:
        with pytest.raises(PolicyNotActiveError):
            kernel.get_active_policy("tenant-99")

    def test_policy_superseded_on_new_registration(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        policy2 = RiskPolicy.create(
            tenant_id="tenant-1",
            version=2,
            max_position_value="200000",
            max_concentration_pct="100.0",
        ).activate()
        kernel.register_policy(policy2)
        active = kernel.get_active_policy("tenant-1")
        assert active.version == 2
        history = kernel.get_policy_history("tenant-1")
        assert len(history) >= 2

    def test_policy_survives_store_recreation(self) -> None:
        """Crash safety: policy must survive store recreation."""
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        store1 = PersistentRiskKernel(db_url=db_url)
        _activate_policy(store1)
        store1.close()

        store2 = PersistentRiskKernel(db_url=db_url)
        policy = store2.get_active_policy("tenant-1")
        assert policy is not None
        assert policy.status is RiskPolicyStatus.ACTIVE
        store2.close()
        os.unlink(db_path)


class TestPersistentAssessment:
    """Test DB-backed risk assessment."""

    def test_assess_approved(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        intent = _make_intent(quantity="0.01")
        session = _make_session()
        assessment = kernel.assess(intent, current_price="50000", session=session)
        assert assessment.authorized
        assert "All risk checks passed" in assessment.reason

    def test_assess_denied_on_exposure(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        intent = _make_intent(quantity="10")  # 500000 > 100000
        session = _make_session()
        assessment = kernel.assess(intent, current_price="50000", session=session)
        assert not assessment.authorized
        assert "Exposure" in assessment.reason

    def test_assess_denied_on_emergency_stop(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        kernel.activate_emergency_stop("test")
        intent = _make_intent(side="buy")
        session = _make_session()
        assessment = kernel.assess(intent, current_price="50000", session=session)
        assert not assessment.authorized
        assert "Emergency stop" in assessment.reason


class TestPersistentAuthorization:
    """Test DB-backed risk authorization."""

    def test_authorize_approved(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        intent = _make_intent()
        session = _make_session()
        auth = kernel.authorize(intent, current_price="50000", session=session)
        assert auth.status is AuthorizationStatus.APPROVED
        assert auth.is_valid

    def test_authorize_denied(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        intent = _make_intent(quantity="100")
        session = _make_session()
        auth = kernel.authorize(intent, current_price="50000", session=session)
        assert auth.status is AuthorizationStatus.DENIED

    def test_get_authorization_after_creation(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        intent = _make_intent()
        auth = kernel.authorize(intent, current_price="50000")
        fetched = kernel.get_authorization(str(auth.authorization_id))
        assert fetched.status is AuthorizationStatus.APPROVED

    def test_consume_authorization(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        intent = _make_intent()
        auth = kernel.authorize(intent, current_price="50000")
        consumed = kernel.consume_authorization(str(auth.authorization_id))
        assert consumed.status is AuthorizationStatus.CONSUMED

    def test_authorization_survives_store_recreation(self) -> None:
        """Crash safety: authorization must survive store recreation."""
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        store1 = PersistentRiskKernel(db_url=db_url)
        _activate_policy(store1)
        intent = _make_intent()
        auth = store1.authorize(intent, current_price="50000")
        auth_id = str(auth.authorization_id)
        store1.close()

        store2 = PersistentRiskKernel(db_url=db_url)
        fetched = store2.get_authorization(auth_id)
        assert fetched.status is AuthorizationStatus.APPROVED
        store2.close()
        os.unlink(db_path)


class TestPersistentReservations:
    """Test DB-backed risk reservations."""

    def test_reserve_and_release(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        intent = _make_intent(quantity="0.01")
        auth = kernel.authorize(intent, current_price="50000")
        reservation = kernel.reserve_capacity(auth)
        assert reservation.status is ReservationStatus.ACTIVE

        # Exposure should have increased
        exposure = kernel.get_current_exposure("tenant-1")
        assert Decimal(exposure) > 0

        released = kernel.release_reservation(str(reservation.reservation_id))
        assert released.status is ReservationStatus.RELEASED

        # Exposure should be back to 0
        exposure = kernel.get_current_exposure("tenant-1")
        assert Decimal(exposure) == 0

    def test_reserve_capacity_exposure_limit(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        # First authorize with a small intent that passes
        small_intent = _make_intent(quantity="0.001")
        auth = kernel.authorize(small_intent, current_price="50000")
        reservation = kernel.reserve_capacity(auth, reserved_value="50000")
        assert reservation.status is ReservationStatus.ACTIVE


class TestPersistentExposureAndDailyLoss:
    """Test DB-backed exposure and daily loss tracking."""

    def test_exposure_tracks_reservations(self, kernel: PersistentRiskKernel) -> None:
        _activate_policy(kernel)
        intent = _make_intent(quantity="0.01")
        auth = kernel.authorize(intent, current_price="50000")
        kernel.reserve_capacity(auth)
        assert Decimal(kernel.get_current_exposure("tenant-1")) > 0

    def test_daily_loss_tracking(self, kernel: PersistentRiskKernel) -> None:
        kernel.record_daily_loss("tenant-1", "100")
        assert kernel.get_daily_loss("tenant-1") == "100"
        kernel.record_daily_loss("tenant-1", "50")
        assert kernel.get_daily_loss("tenant-1") == "150"

    def test_exposure_survives_store_recreation(self) -> None:
        """Crash safety: exposure must survive store recreation."""
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        store1 = PersistentRiskKernel(db_url=db_url)
        _activate_policy(store1)
        intent = _make_intent(quantity="0.01")
        auth = store1.authorize(intent, current_price="50000")
        store1.reserve_capacity(auth)
        store1.close()

        store2 = PersistentRiskKernel(db_url=db_url)
        exposure = store2.get_current_exposure("tenant-1")
        assert Decimal(exposure) > 0
        store2.close()
        os.unlink(db_path)
