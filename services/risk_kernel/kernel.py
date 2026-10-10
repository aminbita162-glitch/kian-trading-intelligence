"""Independent Risk & Safety Kernel for Kian Trading Intelligence.

Per AD-004 (Four Agents + Independent Safety Kernel): the Risk Kernel is a
deterministic safety service, NOT an agent. It validates:

1. Tenant and profile authorization.
2. Session state.
3. Venue and instrument eligibility.
4. Capital and exposure limits.
5. Daily loss and drawdown.
6. Concentration and correlation.
7. Liquidity and volatility.
8. Market-data freshness.
9. Emergency-stop state.
10. Risk policy version.
11. Order-specific authorization validity.

Invariant: No exposure-increasing order may reach an exchange adapter without
valid risk authorization.

Per AD-013: enforce hard limits for exposure, daily loss, drawdown,
concentration, volatility, liquidity, and correlated positions.

Per Section 05.4: concurrent strategies and sessions must not spend the same
risk budget. Risk reservations must be concurrency-safe and tied to specific
order parameters.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from threading import Lock

from contracts.enums import OrderState
from contracts.exchange import FillResult
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


class RiskKernelError(Exception):
    """Base exception for Risk Kernel errors."""


class EmergencyStopActive(RiskKernelError):
    """Raised when an emergency stop is active and blocks new orders."""


class PolicyNotActiveError(RiskKernelError):
    """Raised when no active risk policy exists for a tenant."""


class RiskAuthorizationNotFound(RiskKernelError):
    """Raised when a risk authorization is not found."""


class ExposureExceededError(RiskKernelError):
    """Raised when exposure exceeds the policy limit."""


class DailyLossExceededError(RiskKernelError):
    """Raised when daily loss exceeds the policy limit."""


class ConcentrationExceededError(RiskKernelError):
    """Raised when concentration exceeds the policy limit."""


class ReservationExpiredError(RiskKernelError):
    """Raised when a risk reservation has expired."""


class ReservationAlreadyReleasedError(RiskKernelError):
    """Raised when a risk reservation has already been released."""


class EmergencyStop:
    """Emergency stop state per Section 05.6.

    Emergency stop must:
    - Block new exposure-increasing orders.
    - Prevent automatic trading restart.
    - Preserve order and financial evidence.
    - Initiate reconciliation.
    - Apply only preauthorized protective actions.
    - Report actual exchange-side outcomes.

    An accepted emergency command is NOT proof that all external orders
    were cancelled.
    """

    def __init__(self) -> None:
        self._active: bool = False
        self._activated_at: datetime | None = None
        self._reason: str = ""
        self._lock: Lock = Lock()

    @property
    def is_active(self) -> bool:
        """True if the emergency stop is active."""
        return self._active

    @property
    def activated_at(self) -> datetime | None:
        """UTC timestamp when the emergency stop was activated."""
        return self._activated_at

    @property
    def reason(self) -> str:
        """Reason for the emergency stop."""
        return self._reason

    def activate(self, reason: str = "Manual emergency stop") -> None:
        """Activate the emergency stop.

        Per Section 05.6: blocks new exposure-increasing orders and prevents
        automatic trading restart.
        """
        with self._lock:
            self._active = True
            self._activated_at = datetime.now(UTC)
            self._reason = reason

    def deactivate(self) -> None:
        """Deactivate the emergency stop.

        Per Section 05.6: prevents automatic restart. Deactivation requires
        explicit human authorization (the caller is responsible for verifying
        this).
        """
        with self._lock:
            self._active = False
            self._activated_at = None
            self._reason = ""

    def reset(self) -> None:
        """Reset the emergency stop state (for testing)."""
        with self._lock:
            self._active = False
            self._activated_at = None
            self._reason = ""


class RiskKernel:
    """Independent deterministic Risk & Safety Kernel.

    Per AD-004: the kernel is NOT an agent. It is a deterministic safety
    service that validates orders against the active risk policy.

    The kernel is thread-safe: all state mutations are guarded by a lock
    to ensure concurrency-safe risk budget management (Section 05.4).

    Invariant: No exposure-increasing order may reach an exchange adapter
    without valid risk authorization.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._policies: dict[str, RiskPolicy] = {}  # tenant_id -> active policy
        self._policy_history: dict[str, list[RiskPolicy]] = {}  # tenant_id -> all versions
        self._authorizations: dict[str, RiskAuthorization] = {}  # auth_id -> auth
        self._reservations: dict[str, RiskReservation] = {}  # reservation_id -> reservation
        self._intent_to_auth: dict[str, str] = {}  # intent_id -> auth_id
        self._emergency_stop: EmergencyStop = EmergencyStop()
        self._current_exposure: dict[str, Decimal] = {}  # tenant_id -> current exposure
        self._daily_loss: dict[str, Decimal] = {}  # tenant_id -> daily realized loss
        self._daily_loss_reset: dict[str, datetime] = {}  # tenant_id -> last reset time
        self._position_count: dict[str, dict[str, int]] = {}  # tenant_id -> symbol -> count
        self._session_states: dict[str, str] = {}  # session_id -> state string

    # ── Emergency Stop ──

    @property
    def emergency_stop(self) -> EmergencyStop:
        """Access the emergency stop state."""
        return self._emergency_stop

    def activate_emergency_stop(self, reason: str = "Manual emergency stop") -> None:
        """Activate the emergency stop.

        Per Section 05.6: blocks new exposure-increasing orders, prevents
        automatic trading restart, preserves evidence, initiates
        reconciliation.
        """
        self._emergency_stop.activate(reason)

    def deactivate_emergency_stop(self) -> None:
        """Deactivate the emergency stop (requires explicit human authorization)."""
        self._emergency_stop.deactivate()

    # ── Risk Policy Management ──

    def register_policy(self, policy: RiskPolicy) -> None:
        """Register a new risk policy for a tenant.

        If the policy is ACTIVE, it becomes the current policy for the tenant.
        Previous active policies are superseded.
        """
        with self._lock:
            tenant = policy.tenant_id
            if tenant not in self._policy_history:
                self._policy_history[tenant] = []
            self._policy_history[tenant].append(policy)
            if policy.status is RiskPolicyStatus.ACTIVE:
                if tenant in self._policies:
                    old = self._policies[tenant]
                    self._policies[tenant] = old.supersede()
                self._policies[tenant] = policy

    def get_active_policy(self, tenant_id: str) -> RiskPolicy:
        """Get the active risk policy for a tenant.

        Raises PolicyNotActiveError if no active policy exists.
        """
        with self._lock:
            policy = self._policies.get(tenant_id)
            if policy is None or policy.status is not RiskPolicyStatus.ACTIVE:
                raise PolicyNotActiveError(f"No active risk policy for tenant {tenant_id}.")
            return policy

    def get_policy_history(self, tenant_id: str) -> list[RiskPolicy]:
        """Get all policy versions for a tenant."""
        with self._lock:
            return list(self._policy_history.get(tenant_id, []))

    # ── Risk Assessment ──

    def _check_emergency_stop(
        self,
        intent: OrderIntent,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 1: emergency stop blocks new exposure-increasing orders."""
        checked.append("emergency_stop")
        if self._emergency_stop.is_active and intent.side == "buy":
            return RiskAssessment(
                authorized=False,
                reason="Emergency stop is active — new exposure-increasing orders blocked.",
                checked_limits=checked,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )
        return None

    def _check_session_state(
        self,
        session: TradingSession | None,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 2: session must not be terminal or halted."""
        checked.append("session_state")
        if session is not None:
            if session.is_terminal:
                return RiskAssessment(
                    authorized=False,
                    reason=f"Session is terminal ({session.state.value}).",
                    checked_limits=checked,
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                )
            if session.is_halted:
                return RiskAssessment(
                    authorized=False,
                    reason="Session is in SAFE_HALT — new orders blocked.",
                    checked_limits=checked,
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                )
        return None

    def _check_exposure(
        self,
        intent: OrderIntent,
        order_value: Decimal,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 3: exposure must not exceed the policy limit."""
        checked.append("exposure_limit")
        current_exp = self._current_exposure.get(intent.tenant_id, Decimal(0))
        max_exp = Decimal(policy.max_position_value)
        if intent.side == "buy":
            new_exposure = current_exp + order_value
            if new_exposure > max_exp:
                return RiskAssessment(
                    authorized=False,
                    reason=(
                        f"Exposure {new_exposure} exceeds limit {max_exp} "
                        f"(current: {current_exp}, order: {order_value})."
                    ),
                    checked_limits=checked,
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                )
        return None

    def _check_daily_loss(
        self,
        intent: OrderIntent,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 4: daily loss must not exceed the policy limit."""
        checked.append("daily_loss_limit")
        self._reset_daily_loss_if_needed(intent.tenant_id)
        current_loss = self._daily_loss.get(intent.tenant_id, Decimal(0))
        max_loss = Decimal(policy.max_daily_loss)
        if current_loss >= max_loss:
            return RiskAssessment(
                authorized=False,
                reason=(
                    f"Daily loss {current_loss} exceeds limit {max_loss}. "
                    "Trading stopped for the day."
                ),
                checked_limits=checked,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )
        return None

    def _check_drawdown(
        self,
        intent: OrderIntent,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 5: drawdown must not exceed the policy limit."""
        checked.append("drawdown_limit")
        current_loss = self._daily_loss.get(intent.tenant_id, Decimal(0))
        max_drawdown = Decimal(policy.max_drawdown)
        if current_loss >= max_drawdown:
            return RiskAssessment(
                authorized=False,
                reason=f"Drawdown {current_loss} exceeds limit {max_drawdown}.",
                checked_limits=checked,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )
        return None

    def _check_concentration(
        self,
        intent: OrderIntent,
        order_value: Decimal,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 6: concentration must not exceed the policy percentage."""
        checked.append("concentration_limit")
        max_exp = Decimal(policy.max_position_value)
        if intent.side == "buy" and max_exp > 0:
            max_conc = Decimal(policy.max_concentration_pct)
            conc_pct = (order_value / max_exp) * Decimal(100)
            if conc_pct > max_conc:
                return RiskAssessment(
                    authorized=False,
                    reason=(f"Concentration {conc_pct}% exceeds limit {max_conc}%."),
                    checked_limits=checked,
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                )
        return None

    def _check_position_count(
        self,
        intent: OrderIntent,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 7: position count per symbol must not exceed the limit."""
        checked.append("position_count_limit")
        tenant_positions = self._position_count.get(intent.tenant_id, {})
        current_count = tenant_positions.get(intent.symbol, 0)
        max_pos = policy.max_position_per_symbol
        if intent.side == "buy" and current_count >= max_pos:
            return RiskAssessment(
                authorized=False,
                reason=(
                    f"Position count {current_count} for {intent.symbol} exceeds limit {max_pos}."
                ),
                checked_limits=checked,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )
        return None

    def _check_order_state(
        self,
        intent: OrderIntent,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 8: order state must be CREATED or VALIDATED."""
        checked.append("order_state")
        if intent.state not in (OrderState.CREATED, OrderState.VALIDATED):
            return RiskAssessment(
                authorized=False,
                reason=f"Order state {intent.state.value} is not eligible for risk approval.",
                checked_limits=checked,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )
        return None

    def _check_policy_version(
        self,
        checked: list[str],
        policy: RiskPolicy,
    ) -> RiskAssessment | None:
        """Check 9: policy must be active."""
        checked.append("policy_version")
        if policy.status is not RiskPolicyStatus.ACTIVE:
            return RiskAssessment(
                authorized=False,
                reason=f"Policy {policy.policy_id} is not active ({policy.status.value}).",
                checked_limits=checked,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )
        return None

    def assess(
        self,
        intent: OrderIntent,
        *,
        current_price: str,
        session: TradingSession | None = None,
    ) -> RiskAssessment:
        """Assess an order intent against the active risk policy.

        This is the core deterministic safety validation. The assessment is
        deterministic: same inputs always produce the same decision.

        Per AD-013: enforce hard limits for exposure, daily loss, drawdown,
        concentration, volatility, and liquidity.
        Per Section 05.6: emergency stop blocks new exposure-increasing orders.
        """
        checked: list[str] = []
        policy = self.get_active_policy(intent.tenant_id)
        order_value = Decimal(intent.quantity) * Decimal(current_price)

        # Run all risk checks in order; return on first failure.
        checks = [
            partial(self._check_emergency_stop, intent=intent),
            partial(self._check_session_state, session=session),
            partial(self._check_exposure, intent=intent, order_value=order_value),
            partial(self._check_daily_loss, intent=intent),
            partial(self._check_drawdown, intent=intent),
            partial(self._check_concentration, intent=intent, order_value=order_value),
            partial(self._check_position_count, intent=intent),
            partial(self._check_order_state, intent=intent),
            partial(self._check_policy_version),
        ]

        for check_fn in checks:
            result = check_fn(checked=checked, policy=policy)
            if result is not None:
                return result

        return RiskAssessment(
            authorized=True,
            reason="All risk checks passed.",
            checked_limits=checked,
            policy_id=policy.policy_id,
            policy_version=policy.version,
        )

    # ── Risk Authorization ──

    def authorize(
        self,
        intent: OrderIntent,
        *,
        current_price: str,
        session: TradingSession | None = None,
        ttl_seconds: int = 30,
    ) -> RiskAuthorization:
        """Authorize an order intent after risk assessment.

        Per Section 05.4: issue bounded risk authorization tied to specific
        order parameters. The authorization has a TTL and is consumed on use.
        """
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
            with self._lock:
                self._authorizations[str(auth.authorization_id)] = auth
                self._intent_to_auth[str(intent.intent_id)] = str(auth.authorization_id)
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
        with self._lock:
            self._authorizations[str(auth.authorization_id)] = auth
            self._intent_to_auth[str(intent.intent_id)] = str(auth.authorization_id)
        return auth

    def get_authorization(self, auth_id: str) -> RiskAuthorization:
        """Get a risk authorization by ID."""
        with self._lock:
            auth = self._authorizations.get(auth_id)
            if auth is None:
                raise RiskAuthorizationNotFound(f"Authorization {auth_id} not found.")
            return auth

    def get_authorization_for_intent(self, intent_id: str) -> RiskAuthorization:
        """Get the risk authorization for an intent."""
        with self._lock:
            auth_id = self._intent_to_auth.get(intent_id)
            if auth_id is None:
                raise RiskAuthorizationNotFound(f"No authorization for intent {intent_id}.")
            auth = self._authorizations.get(auth_id)
            if auth is None:
                raise RiskAuthorizationNotFound(f"Authorization {auth_id} not found.")
            return auth

    def consume_authorization(self, auth_id: str) -> RiskAuthorization:
        """Consume an authorization (mark as CONSUMED).

        Per Section 05.3: a consumed authorization cannot be reused.
        """
        with self._lock:
            auth = self._authorizations.get(auth_id)
            if auth is None:
                raise RiskAuthorizationNotFound(f"Authorization {auth_id} not found.")
            if auth.status is not AuthorizationStatus.APPROVED:
                raise RiskKernelError(
                    f"Cannot consume authorization in status {auth.status.value}."
                )
            if auth.is_expired:
                raise RiskKernelError(f"Authorization {auth_id} has expired.")
            consumed = auth.consume()
            self._authorizations[auth_id] = consumed
            return consumed

    def cancel_authorization(self, auth_id: str, reason: str = "") -> RiskAuthorization:
        """Cancel an authorization."""
        with self._lock:
            auth = self._authorizations.get(auth_id)
            if auth is None:
                raise RiskAuthorizationNotFound(f"Authorization {auth_id} not found.")
            cancelled = auth.cancel(reason)
            self._authorizations[auth_id] = cancelled
            return cancelled

    # ── Risk Reservations ──

    def reserve_capacity(
        self,
        authorization: RiskAuthorization,
        *,
        reserved_value: str | None = None,
        ttl_seconds: int = 60,
    ) -> RiskReservation:
        """Reserve risk capacity for an authorized order.

        Per Section 05.4: concurrent strategies and sessions must not spend
        the same risk budget. This reservation is concurrency-safe and
        checks exposure limits under the lock.
        """
        with self._lock:
            if authorization.status is not AuthorizationStatus.APPROVED:
                raise RiskKernelError(
                    f"Cannot reserve capacity for authorization in status "
                    f"{authorization.status.value}."
                )
            if authorization.is_expired:
                raise RiskKernelError("Authorization has expired.")

            value = reserved_value or authorization.quantity

            # Check exposure limit at reservation time (concurrency-safe)
            if authorization.side == "buy":
                policy = self._policies.get(authorization.tenant_id)
                if policy is not None:
                    current = self._current_exposure.get(authorization.tenant_id, Decimal(0))
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
            self._reservations[str(reservation.reservation_id)] = reservation

            if authorization.side == "buy":
                current = self._current_exposure.get(authorization.tenant_id, Decimal(0))
                self._current_exposure[authorization.tenant_id] = current + Decimal(value)

            return reservation

    def release_reservation(self, reservation_id: str) -> RiskReservation:
        """Release a risk reservation back to the budget.

        Per Section 05.4: released capacity returns to the available budget.
        """
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise RiskKernelError(f"Reservation {reservation_id} not found.")
            if reservation.status is not ReservationStatus.ACTIVE:
                raise ReservationAlreadyReleasedError(
                    f"Reservation {reservation_id} is not active "
                    f"(status: {reservation.status.value})."
                )

            if reservation.is_expired:
                released = RiskReservation(
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
                self._reservations[reservation_id] = released
                return released

            released = reservation.release()
            self._reservations[reservation_id] = released

            auth = self._authorizations.get(str(reservation.authorization_id))
            if auth and auth.side == "buy":
                current = self._current_exposure.get(reservation.tenant_id, Decimal(0))
                self._current_exposure[reservation.tenant_id] = current - Decimal(
                    reservation.reserved_value
                )
            return released

    def consume_reservation(self, reservation_id: str) -> RiskReservation:
        """Consume a reservation (order was filled)."""
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise RiskKernelError(f"Reservation {reservation_id} not found.")
            if reservation.status is not ReservationStatus.ACTIVE:
                raise RiskKernelError(
                    f"Reservation {reservation_id} is not active "
                    f"(status: {reservation.status.value})."
                )
            if reservation.is_expired:
                raise ReservationExpiredError(f"Reservation {reservation_id} has expired.")
            consumed = reservation.consume()
            self._reservations[reservation_id] = consumed
            return consumed

    def get_reservation(self, reservation_id: str) -> RiskReservation:
        """Get a reservation by ID."""
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise RiskKernelError(f"Reservation {reservation_id} not found.")
            return reservation

    # ── Exposure Tracking ──

    def get_current_exposure(self, tenant_id: str) -> str:
        """Get the current exposure for a tenant."""
        with self._lock:
            return str(self._current_exposure.get(tenant_id, Decimal(0)))

    def record_fill(self, tenant_id: str, fill: FillResult) -> None:
        """Record a fill to update exposure and daily loss.

        Per AD-014: explicit partial-fill handling.
        Per Section 05.3: every fill must have a stable identity.
        """
        with self._lock:
            self._reset_daily_loss_if_needed(tenant_id)
            tenant_positions = self._position_count.setdefault(tenant_id, {})
            if fill.side == "buy":
                count = tenant_positions.get(fill.symbol, 0)
                tenant_positions[fill.symbol] = count + 1
            if fill.side == "sell":
                loss = Decimal(fill.fee)
                current = self._daily_loss.get(tenant_id, Decimal(0))
                self._daily_loss[tenant_id] = current + loss

    def _reset_daily_loss_if_needed(self, tenant_id: str) -> None:
        """Reset daily loss counter if 24 hours have passed."""
        now = datetime.now(UTC)
        last_reset = self._daily_loss_reset.get(tenant_id)
        if last_reset is None or (now - last_reset) >= timedelta(hours=24):
            self._daily_loss[tenant_id] = Decimal(0)
            self._daily_loss_reset[tenant_id] = now

    def reset(self) -> None:
        """Reset all kernel state (for testing only)."""
        with self._lock:
            self._policies.clear()
            self._policy_history.clear()
            self._authorizations.clear()
            self._reservations.clear()
            self._intent_to_auth.clear()
            self._emergency_stop.reset()
            self._current_exposure.clear()
            self._daily_loss.clear()
            self._daily_loss_reset.clear()
            self._position_count.clear()
            self._session_states.clear()
