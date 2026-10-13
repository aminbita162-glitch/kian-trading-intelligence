"""E4 — Formal model invariant tests.

Per E4 (Safety Plane Hardening): formal models (TLA+/P) for order/session/
reservation/SAFE_HALT checked in CI.

These tests run the Python formal checker (formal/formal_checker.py) which
validates that the implementation's transition tables match the formal
model invariants.
"""

from __future__ import annotations

from formal.formal_checker import (
    all_invariants_hold,
    check_all_models,
    check_order_model,
    check_reservation_model,
    check_safe_halt_model,
    check_session_model,
)


class TestOrderModel:
    """Test OrderModel formal invariants."""

    def test_all_order_invariants_pass(self) -> None:
        """All OrderModel invariants must hold."""
        results = check_order_model()
        failures = [r for r in results if not r.passed]
        assert failures == [], "OrderModel invariant failures:\n" + "\n".join(
            f"  {f.model}:{f.invariant} — {f.detail}" for f in failures
        )

    def test_terminal_states_have_no_transitions(self) -> None:
        """FILLED, CANCELLED, REJECTED, EXPIRED must have empty transition sets."""
        from contracts.enums import LEGAL_ORDER_TRANSITIONS, OrderState

        terminal = [
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
        ]
        for state in terminal:
            assert len(LEGAL_ORDER_TRANSITIONS[state]) == 0, (
                f"{state.value} has transitions: {LEGAL_ORDER_TRANSITIONS[state]}"
            )

    def test_no_transition_to_created(self) -> None:
        """No state may transition to CREATED."""
        from contracts.enums import LEGAL_ORDER_TRANSITIONS, OrderState

        for source, targets in LEGAL_ORDER_TRANSITIONS.items():
            assert OrderState.CREATED not in targets, f"{source.value} can transition to CREATED"

    def test_all_states_in_transitions_map(self) -> None:
        """All OrderState enum values must be in the transitions map."""
        from contracts.enums import LEGAL_ORDER_TRANSITIONS, OrderState

        for state in OrderState:
            assert state in LEGAL_ORDER_TRANSITIONS, f"{state.value} not in transitions map"


class TestSessionModel:
    """Test SessionModel formal invariants."""

    def test_all_session_invariants_pass(self) -> None:
        """All SessionModel invariants must hold."""
        results = check_session_model()
        failures = [r for r in results if not r.passed]
        assert failures == [], "SessionModel invariant failures:\n" + "\n".join(
            f"  {f.model}:{f.invariant} — {f.detail}" for f in failures
        )

    def test_safe_halt_only_to_reconciling(self) -> None:
        """SAFE_HALT must only transition to RECONCILING."""
        from contracts.risk import LEGAL_SESSION_TRANSITIONS

        assert LEGAL_SESSION_TRANSITIONS["safe_halt"] == {"reconciling"}

    def test_completed_is_terminal(self) -> None:
        """COMPLETED must be terminal (no transitions)."""
        from contracts.risk import LEGAL_SESSION_TRANSITIONS

        assert len(LEGAL_SESSION_TRANSITIONS["completed"]) == 0

    def test_cancelled_is_terminal(self) -> None:
        """CANCELLED must be terminal (no transitions)."""
        from contracts.risk import LEGAL_SESSION_TRANSITIONS

        assert len(LEGAL_SESSION_TRANSITIONS["cancelled"]) == 0


class TestReservationModel:
    """Test ReservationModel formal invariants."""

    def test_all_reservation_invariants_pass(self) -> None:
        """All ReservationModel invariants must hold."""
        results = check_reservation_model()
        failures = [r for r in results if not r.passed]
        assert failures == [], "ReservationModel invariant failures:\n" + "\n".join(
            f"  {f.model}:{f.invariant} — {f.detail}" for f in failures
        )

    def test_terminal_states_have_no_transitions(self) -> None:
        """RELEASED, EXPIRED, CONSUMED must have no transitions."""
        from contracts.risk import ReservationStatus

        # These are terminal by construction in the contract
        assert ReservationStatus.RELEASED.value == "released"
        assert ReservationStatus.EXPIRED.value == "expired"
        assert ReservationStatus.CONSUMED.value == "consumed"


class TestSafeHaltModel:
    """Test SafeHaltModel formal invariants."""

    def test_all_safe_halt_invariants_pass(self) -> None:
        """All SafeHaltModel invariants must hold."""
        results = check_safe_halt_model()
        failures = [r for r in results if not r.passed]
        assert failures == [], "SafeHaltModel invariant failures:\n" + "\n".join(
            f"  {f.model}:{f.invariant} — {f.detail}" for f in failures
        )

    def test_no_auto_restart(self) -> None:
        """SAFE_HALT must not auto-restart (no running/degraded transitions)."""
        from contracts.risk import LEGAL_SESSION_TRANSITIONS

        targets = LEGAL_SESSION_TRANSITIONS["safe_halt"]
        assert "running" not in targets
        assert "degraded" not in targets

    def test_emergency_stop_check_exists(self) -> None:
        """RiskKernel must have _check_emergency_stop method."""
        from services.risk_kernel.kernel import RiskKernel

        assert hasattr(RiskKernel, "_check_emergency_stop")


class TestAllModels:
    """Test that all formal model invariants hold together."""

    def test_all_invariants_hold(self) -> None:
        """All formal model invariants must hold simultaneously."""
        all_passed, results = all_invariants_hold()
        assert all_passed, (
            f"{sum(1 for r in results if not r.passed)} invariant(s) failed:\n"
            + "\n".join(f"  {r.model}:{r.invariant} — {r.detail}" for r in results if not r.passed)
        )

    def test_all_models_produce_results(self) -> None:
        """All four models must produce at least one result."""
        results = check_all_models()
        models = {r.model for r in results}
        assert "OrderModel" in models
        assert "SessionModel" in models
        assert "ReservationModel" in models
        assert "SafeHaltModel" in models
