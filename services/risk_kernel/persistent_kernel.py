"""Persistent risk kernel store for Kian Trading Intelligence (E2 — Durable Core).

Architecture Decisions: AD-004 (Independent Risk Kernel), AD-013 (hard
limits), AD-031 (PostgreSQL for durable records).

Provides ``PersistentRiskKernel``, which replaces the in-memory state of
``RiskKernel`` with a SQLAlchemy-backed store. The database is the
authoritative state; in-memory dicts are not used.

Per E2 scope: "Remove authoritative in-memory state." The persistent
kernel stores policies, authorizations, reservations, exposure, and
daily-loss in the database. The ``EmergencyStop`` state remains in-memory
because it is a transient operational flag, not an authoritative aggregate.
"""

from __future__ import annotations

import contextlib
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Lock
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
)
from sqlalchemy.pool import StaticPool

from contracts.enums import OrderState
from contracts.order import OrderIntent
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
from contracts.trading import TradingSession
from services.risk_kernel.kernel import (
    ExposureExceededError,
    PolicyNotActiveError,
    ReservationAlreadyReleasedError,
    ReservationExpiredError,
    RiskAuthorizationNotFound,
    RiskKernel,
    RiskKernelError,
)


class RiskPersistenceError(Exception):
    """Raised when risk persistence operations fail."""


class RiskConfigurationError(RiskPersistenceError):
    """Raised when the risk persistence layer is misconfigured (fail-closed)."""


# ── SQLAlchemy models ──


class RiskBase(DeclarativeBase):
    """Declarative base for all risk kernel tables."""


class RiskPolicyRow(RiskBase):
    __tablename__ = "risk_policies"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_risk_policy_version_positive"),)

    policy_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    max_position_value: Mapped[str] = mapped_column(String(40), default="100000.00")
    max_daily_loss: Mapped[str] = mapped_column(String(40), default="5000.00")
    max_drawdown: Mapped[str] = mapped_column(String(40), default="10000.00")
    max_concentration_pct: Mapped[str] = mapped_column(String(40), default="25.0")
    max_position_per_symbol: Mapped[int] = mapped_column(Integer, default=10)
    min_liquidity_usd: Mapped[str] = mapped_column(String(40), default="10000.00")
    max_volatility: Mapped[str] = mapped_column(String(40), default="0.05")
    created_at: Mapped[str] = mapped_column(String(40))
    activated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class RiskAuthorizationRow(RiskBase):
    __tablename__ = "risk_authorizations"
    __table_args__ = (UniqueConstraint("intent_id", name="uq_risk_auth_intent"),)

    authorization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    policy_id: Mapped[str] = mapped_column(String(36))
    policy_version: Mapped[int] = mapped_column(Integer)
    intent_id: Mapped[str] = mapped_column(String(255))
    symbol: Mapped[str] = mapped_column(String(50))
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[str] = mapped_column(String(40))
    max_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    consumed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(String(500), default="")


class RiskReservationRow(RiskBase):
    __tablename__ = "risk_reservations"

    reservation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    authorization_id: Mapped[str] = mapped_column(String(36))
    intent_id: Mapped[str] = mapped_column(String(255))
    reserved_value: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    released_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class RiskExposureRow(RiskBase):
    """Current exposure per tenant — singleton row per tenant."""

    __tablename__ = "risk_exposure"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_risk_exposure_tenant"),)

    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exposure: Mapped[str] = mapped_column(String(40), default="0")


class RiskDailyLossRow(RiskBase):
    """Daily loss tracking per tenant."""

    __tablename__ = "risk_daily_loss"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_risk_daily_loss_tenant"),)

    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loss: Mapped[str] = mapped_column(String(40), default="0")
    reset_at: Mapped[str] = mapped_column(String(40))


class RiskSchemaVersionRow(RiskBase):
    __tablename__ = "risk_schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(500))
    applied_at: Mapped[str] = mapped_column(String(40))


# ── Helpers ──


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _now_str() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_db_url() -> str:
    url = os.environ.get("KTI_DATABASE_URL", "")
    if os.environ.get("KTI_ENVIRONMENT", "").lower() == "production":
        if not url:
            raise RiskConfigurationError(
                "KTI_DATABASE_URL is not set. In production, a PostgreSQL "
                "connection URL is required."
            )
        if not url.startswith("postgresql"):
            raise RiskConfigurationError("KTI_DATABASE_URL must be a PostgreSQL URL in production.")
        return url
    if not url:
        return "sqlite:///:memory:"
    return url


# ── Migrations ──

RISK_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        "Initial risk kernel schema — policies, authorizations, "
        "reservations, exposure, daily_loss, schema_version",
    ),
]

RISK_CURRENT_VERSION = len(RISK_MIGRATIONS)


def run_risk_migrations_up(engine: Any) -> int:
    """Apply all pending risk migrations."""
    RiskBase.metadata.create_all(engine, checkfirst=True)
    with Session(engine) as session:
        existing = session.get(RiskSchemaVersionRow, 1)
        if existing is None:
            for version, description in RISK_MIGRATIONS:
                session.add(
                    RiskSchemaVersionRow(
                        version=version,
                        description=description,
                        applied_at=_now_str(),
                    )
                )
            session.commit()
    return RISK_CURRENT_VERSION


def run_risk_migrations_down(engine: Any, target_version: int = 0) -> int:
    """Revert risk migrations down to *target_version*."""
    if target_version == 0:
        RiskBase.metadata.drop_all(engine)
    return target_version


# ── Persistent risk kernel ──


class PersistentRiskKernel(RiskKernel):
    """SQLAlchemy-backed risk kernel.

    The database is the authoritative state for policies, authorizations,
    reservations, exposure, and daily loss. The ``EmergencyStop`` flag
    remains in-memory (transient operational state, not an aggregate).

    Per E2 scope: "Remove authoritative in-memory state."
    """

    _instances: list[PersistentRiskKernel] = []
    _instances_lock = Lock()

    def __init__(self, db_url: str | None = None) -> None:
        url = db_url or _resolve_db_url()
        self._url = url
        is_sqlite = url.startswith("sqlite")
        self._engine = create_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False} if is_sqlite else {},
            poolclass=StaticPool if is_sqlite else None,
        )
        self._plock = Lock()
        run_risk_migrations_up(self._engine)
        # Initialize parent in-memory state, then clear — DB is authoritative.
        super().__init__()
        self._policies.clear()
        self._policy_history.clear()
        self._authorizations.clear()
        self._reservations.clear()
        self._intent_to_auth.clear()
        self._current_exposure.clear()
        self._daily_loss.clear()
        self._daily_loss_reset.clear()
        with PersistentRiskKernel._instances_lock:
            PersistentRiskKernel._instances.append(self)

    def close(self) -> None:
        self._engine.dispose()
        with PersistentRiskKernel._instances_lock, contextlib.suppress(ValueError):
            PersistentRiskKernel._instances.remove(self)

    @property
    def engine(self) -> Any:
        return self._engine

    # ── Row ↔ Domain conversion ──

    def _row_to_policy(self, row: RiskPolicyRow) -> RiskPolicy:
        return RiskPolicy(
            policy_id=RiskPolicyId(UUID(row.policy_id)),
            tenant_id=row.tenant_id,
            version=row.version,
            status=RiskPolicyStatus(row.status),
            max_position_value=row.max_position_value,
            max_daily_loss=row.max_daily_loss,
            max_drawdown=row.max_drawdown,
            max_concentration_pct=row.max_concentration_pct,
            max_position_per_symbol=row.max_position_per_symbol,
            min_liquidity_usd=row.min_liquidity_usd,
            max_volatility=row.max_volatility,
            created_at=_str_to_dt(row.created_at),
            activated_at=_str_to_dt(row.activated_at) if row.activated_at else None,
        )

    def _row_to_auth(self, row: RiskAuthorizationRow) -> RiskAuthorization:
        return RiskAuthorization(
            authorization_id=RiskAuthorizationId(UUID(row.authorization_id)),
            tenant_id=row.tenant_id,
            policy_id=RiskPolicyId(UUID(row.policy_id)),
            policy_version=row.policy_version,
            intent_id=row.intent_id,
            symbol=row.symbol,
            side=row.side,
            quantity=row.quantity,
            max_price=row.max_price,
            status=AuthorizationStatus(row.status),
            created_at=_str_to_dt(row.created_at),
            expires_at=_str_to_dt(row.expires_at),
            consumed_at=_str_to_dt(row.consumed_at) if row.consumed_at else None,
            reason=row.reason,
        )

    def _row_to_reservation(self, row: RiskReservationRow) -> RiskReservation:
        return RiskReservation(
            reservation_id=ReservationId(UUID(row.reservation_id)),
            tenant_id=row.tenant_id,
            authorization_id=RiskAuthorizationId(UUID(row.authorization_id)),
            intent_id=row.intent_id,
            reserved_value=row.reserved_value,
            status=ReservationStatus(row.status),
            created_at=_str_to_dt(row.created_at),
            expires_at=_str_to_dt(row.expires_at),
            released_at=_str_to_dt(row.released_at) if row.released_at else None,
        )

    def _auth_to_row(self, auth: RiskAuthorization) -> RiskAuthorizationRow:
        return RiskAuthorizationRow(
            authorization_id=str(auth.authorization_id),
            tenant_id=auth.tenant_id,
            policy_id=str(auth.policy_id),
            policy_version=auth.policy_version,
            intent_id=auth.intent_id,
            symbol=auth.symbol,
            side=auth.side,
            quantity=auth.quantity,
            max_price=auth.max_price,
            status=auth.status.value,
            created_at=_dt_to_str(auth.created_at),
            expires_at=_dt_to_str(auth.expires_at),
            consumed_at=_dt_to_str(auth.consumed_at) if auth.consumed_at else None,
            reason=auth.reason,
        )

    # ── Policy Management ──

    def register_policy(self, policy: RiskPolicy) -> None:
        """Register a new risk policy, persisting to DB."""
        with self._plock, Session(self._engine) as session:
            # If policy is ACTIVE, supersede existing active policies.
            if policy.status is RiskPolicyStatus.ACTIVE:
                existing = session.execute(
                    text(
                        "SELECT policy_id FROM risk_policies "
                        "WHERE tenant_id = :tid AND status = 'active'"
                    ),
                    {"tid": policy.tenant_id},
                ).all()
                for row in existing:
                    orm_row = session.get(RiskPolicyRow, row.policy_id)
                    if orm_row is not None:
                        orm_row.status = "superseded"
            session.add(
                RiskPolicyRow(
                    policy_id=str(policy.policy_id),
                    tenant_id=policy.tenant_id,
                    version=policy.version,
                    status=policy.status.value,
                    max_position_value=policy.max_position_value,
                    max_daily_loss=policy.max_daily_loss,
                    max_drawdown=policy.max_drawdown,
                    max_concentration_pct=policy.max_concentration_pct,
                    max_position_per_symbol=policy.max_position_per_symbol,
                    min_liquidity_usd=policy.min_liquidity_usd,
                    max_volatility=policy.max_volatility,
                    created_at=_dt_to_str(policy.created_at),
                    activated_at=_dt_to_str(policy.activated_at) if policy.activated_at else None,
                )
            )
            session.commit()

    def get_active_policy(self, tenant_id: str) -> RiskPolicy:
        """Get the active risk policy for a tenant from the DB."""
        with Session(self._engine) as session:
            row = session.execute(
                text(
                    "SELECT * FROM risk_policies "
                    "WHERE tenant_id = :tid AND status = 'active' "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"tid": tenant_id},
            ).first()
            if row is None:
                raise PolicyNotActiveError(f"No active risk policy for tenant {tenant_id}.")
            orm_row = session.get(RiskPolicyRow, row.policy_id)
            assert orm_row is not None
            return self._row_to_policy(orm_row)

    def get_policy_history(self, tenant_id: str) -> list[RiskPolicy]:
        with Session(self._engine) as session:
            rows = (
                session.query(RiskPolicyRow)
                .filter(RiskPolicyRow.tenant_id == tenant_id)
                .order_by(RiskPolicyRow.version)
                .all()
            )
            return [self._row_to_policy(r) for r in rows]

    # ── Risk Assessment (DB-backed) ──

    def _deny(
        self,
        reason: str,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment:
        """Create a denied assessment."""
        return RiskAssessment(
            authorized=False,
            reason=reason,
            checked_limits=checked,
            policy_id=policy.policy_id,
            policy_version=policy.version,
        )

    def _ok(
        self,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment:
        """Create an approved assessment."""
        return RiskAssessment(
            authorized=True,
            reason="All risk checks passed.",
            checked_limits=checked,
            policy_id=policy.policy_id,
            policy_version=policy.version,
        )

    def assess(  # noqa: PLR0911
        self,
        intent: OrderIntent,
        *,
        current_price: str,
        session: TradingSession | None = None,
    ) -> RiskAssessment:
        """Assess an order intent — reads all state from DB."""
        checked: list[str] = []
        policy = self.get_active_policy(intent.tenant_id)
        order_value = Decimal(intent.quantity) * Decimal(current_price)

        # Check 1: emergency stop (in-memory transient flag)
        checked.append("emergency_stop")
        if self._emergency_stop.is_active and intent.side == "buy":
            return self._deny(
                "Emergency stop is active — new exposure-increasing orders blocked.",
                checked,
                policy,
            )

        # Check 2: session state
        checked.append("session_state")
        if session is not None:
            if session.is_terminal:
                return self._deny(f"Session is terminal ({session.state.value}).", checked, policy)
            if session.is_halted:
                return self._deny("Session is in SAFE_HALT — new orders blocked.", checked, policy)

        # Check 3: exposure limit (DB-backed)
        checked.append("exposure_limit")
        current_exp = Decimal(self.get_current_exposure(intent.tenant_id))
        max_exp = Decimal(policy.max_position_value)
        if intent.side == "buy":
            new_exposure = current_exp + order_value
            if new_exposure > max_exp:
                return self._deny(
                    f"Exposure {new_exposure} exceeds limit {max_exp} "
                    f"(current: {current_exp}, order: {order_value}).",
                    checked,
                    policy,
                )

        # Check 4: daily loss (DB-backed)
        checked.append("daily_loss_limit")
        current_loss = Decimal(self.get_daily_loss(intent.tenant_id))
        max_loss = Decimal(policy.max_daily_loss)
        if current_loss >= max_loss:
            return self._deny(
                f"Daily loss {current_loss} exceeds limit {max_loss}. Trading stopped for the day.",
                checked,
                policy,
            )

        # Check 5: drawdown
        checked.append("drawdown_limit")
        max_drawdown = Decimal(policy.max_drawdown)
        if current_loss >= max_drawdown:
            return self._deny(
                f"Drawdown {current_loss} exceeds limit {max_drawdown}.",
                checked,
                policy,
            )

        # Check 6: concentration
        checked.append("concentration_limit")
        if intent.side == "buy" and max_exp > 0:
            max_conc = Decimal(policy.max_concentration_pct)
            conc_pct = (order_value / max_exp) * Decimal(100)
            if conc_pct > max_conc:
                return self._deny(
                    f"Concentration {conc_pct}% exceeds limit {max_conc}%.",
                    checked,
                    policy,
                )

        # Check 7: order state
        checked.append("order_state")
        if intent.state not in (OrderState.CREATED, OrderState.VALIDATED):
            return self._deny(
                f"Order state {intent.state.value} is not eligible for risk approval.",
                checked,
                policy,
            )

        # Check 8: policy version
        checked.append("policy_version")
        if policy.status is not RiskPolicyStatus.ACTIVE:
            return self._deny(
                f"Policy {policy.policy_id} is not active ({policy.status.value}).",
                checked,
                policy,
            )

        return self._ok(checked, policy)

    # ── Risk Authorization (DB-backed) ──

    def authorize(
        self,
        intent: OrderIntent,
        *,
        current_price: str,
        session: TradingSession | None = None,
        ttl_seconds: int = 30,
    ) -> RiskAuthorization:
        """Authorize an order intent — persists to DB."""
        assessment = self.assess(intent, current_price=current_price, session=session)

        if not assessment.authorized:
            auth = RiskAuthorization(
                authorization_id=RiskAuthorizationId.generate(),
                tenant_id=intent.tenant_id,
                policy_id=assessment.policy_id or RiskPolicyId.generate(),
                policy_version=assessment.policy_version,
                intent_id=str(intent.intent_id),
                symbol=intent.symbol,
                side=intent.side,
                quantity=intent.quantity,
                status=AuthorizationStatus.DENIED,
                reason=assessment.reason,
            )
            with self._plock, Session(self._engine) as db_session:
                db_session.add(self._auth_to_row(auth))
                db_session.commit()
            return auth

        max_price = current_price if intent.side == "buy" else None
        auth = RiskAuthorization(
            authorization_id=RiskAuthorizationId.generate(),
            tenant_id=intent.tenant_id,
            policy_id=assessment.policy_id,  # type: ignore[arg-type]
            policy_version=assessment.policy_version,
            intent_id=str(intent.intent_id),
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            max_price=max_price,
            status=AuthorizationStatus.APPROVED,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        with self._plock, Session(self._engine) as db_session:
            db_session.add(self._auth_to_row(auth))
            db_session.commit()
        return auth

    def get_authorization(self, auth_id: str) -> RiskAuthorization:
        with Session(self._engine) as session:
            row = session.get(RiskAuthorizationRow, auth_id)
            if row is None:
                raise RiskAuthorizationNotFound(f"Authorization {auth_id} not found.")
            return self._row_to_auth(row)

    def get_authorization_for_intent(self, intent_id: str) -> RiskAuthorization:
        with Session(self._engine) as session:
            row = session.execute(
                text("SELECT * FROM risk_authorizations WHERE intent_id = :iid LIMIT 1"),
                {"iid": intent_id},
            ).first()
            if row is None:
                raise RiskAuthorizationNotFound(f"No authorization for intent {intent_id}.")
            orm_row = session.get(RiskAuthorizationRow, row.authorization_id)
            assert orm_row is not None
            return self._row_to_auth(orm_row)

    def consume_authorization(self, auth_id: str) -> RiskAuthorization:
        with self._plock, Session(self._engine) as session:
            row = session.get(RiskAuthorizationRow, auth_id)
            if row is None:
                raise RiskAuthorizationNotFound(f"Authorization {auth_id} not found.")
            auth = self._row_to_auth(row)
            if auth.status is not AuthorizationStatus.APPROVED:
                raise RiskKernelError(
                    f"Cannot consume authorization in status {auth.status.value}."
                )
            if auth.is_expired:
                raise RiskKernelError(f"Authorization {auth_id} has expired.")
            consumed = auth.consume()
            row.status = "consumed"
            row.consumed_at = _now_str()
            session.commit()
            return consumed

    def cancel_authorization(self, auth_id: str, reason: str = "") -> RiskAuthorization:
        with self._plock, Session(self._engine) as session:
            row = session.get(RiskAuthorizationRow, auth_id)
            if row is None:
                raise RiskAuthorizationNotFound(f"Authorization {auth_id} not found.")
            auth = self._row_to_auth(row)
            cancelled = auth.cancel(reason)
            row.status = "cancelled"
            row.reason = reason or "Cancelled"
            session.commit()
            return cancelled

    # ── Risk Reservations (DB-backed) ──

    def reserve_capacity(
        self,
        authorization: RiskAuthorization,
        *,
        reserved_value: str | None = None,
        ttl_seconds: int = 60,
    ) -> RiskReservation:
        """Reserve risk capacity — checks exposure limit under lock in DB."""
        with self._plock, Session(self._engine) as session:
            if authorization.status is not AuthorizationStatus.APPROVED:
                raise RiskKernelError(
                    f"Cannot reserve capacity for authorization in status "
                    f"{authorization.status.value}."
                )
            if authorization.is_expired:
                raise RiskKernelError("Authorization has expired.")

            value = reserved_value or authorization.quantity

            if authorization.side == "buy":
                policy = self.get_active_policy(authorization.tenant_id)
                exp_row = session.get(RiskExposureRow, authorization.tenant_id)
                current = Decimal(exp_row.exposure) if exp_row is not None else Decimal(0)
                new_exposure = current + Decimal(value)
                max_exp = Decimal(policy.max_position_value)
                if new_exposure > max_exp:
                    raise ExposureExceededError(
                        f"Reservation would exceed exposure limit: {new_exposure} > {max_exp}."
                    )

            reservation = RiskReservation(
                reservation_id=ReservationId.generate(),
                tenant_id=authorization.tenant_id,
                authorization_id=authorization.authorization_id,
                intent_id=authorization.intent_id,
                reserved_value=value,
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            )
            session.add(
                RiskReservationRow(
                    reservation_id=str(reservation.reservation_id),
                    tenant_id=authorization.tenant_id,
                    authorization_id=str(authorization.authorization_id),
                    intent_id=authorization.intent_id,
                    reserved_value=value,
                    status="active",
                    created_at=_dt_to_str(reservation.created_at),
                    expires_at=_dt_to_str(reservation.expires_at),
                )
            )
            if authorization.side == "buy":
                exp_row = session.get(RiskExposureRow, authorization.tenant_id)
                if exp_row is None:
                    session.add(
                        RiskExposureRow(
                            tenant_id=authorization.tenant_id,
                            exposure=value,
                        )
                    )
                else:
                    exp_row.exposure = str(Decimal(exp_row.exposure) + Decimal(value))
            session.commit()
            return reservation

    def release_reservation(self, reservation_id: str) -> RiskReservation:
        with self._plock, Session(self._engine) as session:
            row = session.get(RiskReservationRow, reservation_id)
            if row is None:
                raise RiskKernelError(f"Reservation {reservation_id} not found.")
            if row.status != "active":
                raise ReservationAlreadyReleasedError(
                    f"Reservation {reservation_id} is not active (status: {row.status})."
                )
            reservation = self._row_to_reservation(row)
            if reservation.is_expired:
                row.status = "expired"
                row.released_at = _now_str()
                session.commit()
                return RiskReservation(
                    reservation_id=reservation.reservation_id,
                    tenant_id=reservation.tenant_id,
                    authorization_id=reservation.authorization_id,
                    intent_id=reservation.intent_id,
                    reserved_value=reservation.reserved_value,
                    status=ReservationStatus.EXPIRED,
                    created_at=reservation.created_at,
                    expires_at=reservation.expires_at,
                    released_at=datetime.now(UTC),
                )
            released = reservation.release()
            row.status = "released"
            row.released_at = _now_str()
            # Reduce exposure.
            exp_row = session.get(RiskExposureRow, row.tenant_id)
            if exp_row is not None:
                exp_row.exposure = str(Decimal(exp_row.exposure) - Decimal(row.reserved_value))
            session.commit()
            return released

    def consume_reservation(self, reservation_id: str) -> RiskReservation:
        with self._plock, Session(self._engine) as session:
            row = session.get(RiskReservationRow, reservation_id)
            if row is None:
                raise RiskKernelError(f"Reservation {reservation_id} not found.")
            if row.status != "active":
                raise RiskKernelError(
                    f"Reservation {reservation_id} is not active (status: {row.status})."
                )
            reservation = self._row_to_reservation(row)
            if reservation.is_expired:
                raise ReservationExpiredError(f"Reservation {reservation_id} has expired.")
            consumed = reservation.consume()
            row.status = "consumed"
            row.released_at = _now_str()
            session.commit()
            return consumed

    def get_reservation(self, reservation_id: str) -> RiskReservation:
        with Session(self._engine) as session:
            row = session.get(RiskReservationRow, reservation_id)
            if row is None:
                raise RiskKernelError(f"Reservation {reservation_id} not found.")
            return self._row_to_reservation(row)

    # ── Exposure & Daily Loss (DB-backed) ──

    def get_current_exposure(self, tenant_id: str) -> str:
        with Session(self._engine) as session:
            row = session.get(RiskExposureRow, tenant_id)
            if row is None:
                return "0"
            return row.exposure

    def get_daily_loss(self, tenant_id: str) -> str:
        with Session(self._engine) as session:
            row = session.get(RiskDailyLossRow, tenant_id)
            if row is None:
                return "0"
            return row.loss

    def record_daily_loss(self, tenant_id: str, loss: str) -> None:
        with self._plock, Session(self._engine) as session:
            row = session.get(RiskDailyLossRow, tenant_id)
            if row is None:
                session.add(
                    RiskDailyLossRow(
                        tenant_id=tenant_id,
                        loss=loss,
                        reset_at=_now_str(),
                    )
                )
            else:
                row.loss = str(Decimal(row.loss) + Decimal(loss))
            session.commit()

    # ── Reset ──

    def reset(self) -> None:
        """Drop and recreate all risk tables."""
        with self._plock:
            RiskBase.metadata.drop_all(self._engine)
            run_risk_migrations_up(self._engine)
        self._emergency_stop.reset()


# ── Module-level store management ──

_kernel: PersistentRiskKernel | None = None
_kernel_lock = Lock()


def get_persistent_kernel() -> PersistentRiskKernel:
    global _kernel  # noqa: PLW0603
    with _kernel_lock:
        if _kernel is None:
            _kernel = PersistentRiskKernel()
        return _kernel


def reset_persistent_kernel() -> None:
    global _kernel  # noqa: PLW0603
    with _kernel_lock:
        _close_all_kernel_instances()
        _kernel = PersistentRiskKernel()


def _close_all_kernel_instances() -> None:
    with PersistentRiskKernel._instances_lock:
        instances = list(PersistentRiskKernel._instances)
        PersistentRiskKernel._instances.clear()
    for inst in instances:
        with contextlib.suppress(Exception):
            inst.close()
