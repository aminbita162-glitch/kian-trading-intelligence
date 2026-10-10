"""Tests for trading session state machine (Phase 04).

Per Section 06.2: session states and their legal transitions.
Per Section 06.3: scheduled events must not bypass authorization.
"""

import pytest

from contracts.enums import SessionState
from contracts.trading import (
    LEGAL_SESSION_TRANSITIONS,
    SessionId,
    TradingSession,
)


class TestSessionId:
    def test_generated_ids_are_unique(self) -> None:
        id1 = SessionId.generate()
        id2 = SessionId.generate()
        assert id1 != id2

    def test_str_representation(self) -> None:
        sid = SessionId.generate()
        assert str(sid) == str(sid.value)


class TestTradingSession:
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

    def test_create_session_in_draft(self) -> None:
        session = self._make_session()
        assert session.state is SessionState.DRAFT
        assert session.created_at.tzinfo is not None

    def test_invalid_capital_rejected(self) -> None:
        with pytest.raises(ValueError, match="capital_allocation must be positive"):
            TradingSession.create(
                tenant_id="t1",
                profile_id="p1",
                strategy_version="v1",
                exchange="sim",
                instruments=["BTC/USDT"],
                capital_allocation="0",
                risk_policy_id="p1",
            )

    def test_empty_instruments_rejected(self) -> None:
        with pytest.raises(ValueError, match="instruments must not be empty"):
            TradingSession.create(
                tenant_id="t1",
                profile_id="p1",
                strategy_version="v1",
                exchange="sim",
                instruments=[],
                capital_allocation="10000.00",
                risk_policy_id="p1",
            )

    def test_legal_transition_draft_to_scheduled(self) -> None:
        session = self._make_session()
        scheduled = session.transition_to(SessionState.SCHEDULED)
        assert scheduled.state is SessionState.SCHEDULED

    def test_illegal_transition_draft_to_running(self) -> None:
        session = self._make_session()
        with pytest.raises(ValueError, match="Illegal session transition"):
            session.transition_to(SessionState.RUNNING)

    def test_full_lifecycle(self) -> None:
        session = self._make_session()
        scheduled = session.transition_to(SessionState.SCHEDULED)
        preflight = scheduled.transition_to(SessionState.PREFLIGHT)
        awaiting = preflight.transition_to(SessionState.AWAITING_USER_APPROVAL)
        running = awaiting.transition_to(SessionState.RUNNING)
        assert running.started_at is not None
        completed = running.transition_to(SessionState.COMPLETED)
        assert completed.is_terminal
        assert completed.stopped_at is not None

    def test_safe_halt_lifecycle(self) -> None:
        session = self._make_session()
        scheduled = session.transition_to(SessionState.SCHEDULED)
        preflight = scheduled.transition_to(SessionState.PREFLIGHT)
        halted = preflight.transition_to(SessionState.SAFE_HALT)
        assert halted.is_halted
        # From SAFE_HALT, can only go to RECONCILING
        reconciling = halted.transition_to(SessionState.RECONCILING)
        # From RECONCILING, can go back to RUNNING or COMPLETED
        completed = reconciling.transition_to(SessionState.COMPLETED)
        assert completed.is_terminal

    def test_cannot_transition_from_terminal(self) -> None:
        session = self._make_session()
        scheduled = session.transition_to(SessionState.SCHEDULED)
        cancelled = scheduled.transition_to(SessionState.CANCELLED)
        assert cancelled.is_terminal
        with pytest.raises(ValueError, match="Illegal session transition"):
            cancelled.transition_to(SessionState.RUNNING)

    def test_with_error(self) -> None:
        session = self._make_session()
        errored = session.with_error("Test error")
        assert errored.error_detail == "Test error"
        assert errored.state is session.state


class TestSessionTransitions:
    def test_all_states_have_transition_map(self) -> None:
        """Every SessionState member must appear in the transition map."""
        for state in SessionState:
            assert state in LEGAL_SESSION_TRANSITIONS, f"Missing state in transition map: {state}"

    def test_terminal_states_have_no_outgoing(self) -> None:
        terminal = {SessionState.COMPLETED, SessionState.CANCELLED}
        for state in terminal:
            assert LEGAL_SESSION_TRANSITIONS[state] == set(), (
                f"Terminal state {state} should have no outgoing transitions"
            )

    def test_no_state_transitions_to_draft(self) -> None:
        """DRAFT is an entry state — no state transitions to it."""
        for state, targets in LEGAL_SESSION_TRANSITIONS.items():
            assert SessionState.DRAFT not in targets, (
                f"State {state} should not transition to DRAFT"
            )

    def test_ten_states_exist(self) -> None:
        """Per Section 06.2: exactly 10 session states."""
        assert len(list(SessionState)) == 10

    def test_safe_halt_only_to_reconciling(self) -> None:
        """Per Section 06.3: SAFE_HALT can only go to RECONCILING."""
        assert LEGAL_SESSION_TRANSITIONS[SessionState.SAFE_HALT] == {SessionState.RECONCILING}

    def test_running_can_degrade_and_halt(self) -> None:
        transitions = LEGAL_SESSION_TRANSITIONS[SessionState.RUNNING]
        assert SessionState.DEGRADED in transitions
        assert SessionState.SAFE_HALT in transitions
        assert SessionState.COMPLETED in transitions
