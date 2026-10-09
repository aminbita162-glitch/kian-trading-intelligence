"""Tests for order state transitions (AD-014, Section 05.2).

Verifies that all legal transitions are defined and that illegal
transitions are rejected.
"""


from contracts.enums import LEGAL_ORDER_TRANSITIONS, OrderState


class TestOrderStates:
    def test_all_states_have_transition_map(self) -> None:
        """Every OrderState member must appear in the transition map."""
        for state in OrderState:
            assert state in LEGAL_ORDER_TRANSITIONS, f"Missing state in transition map: {state}"

    def test_terminal_states_have_no_outgoing_transitions(self) -> None:
        terminal_states = {
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
        }
        for state in terminal_states:
            assert LEGAL_ORDER_TRANSITIONS[state] == set(), (
                f"Terminal state {state} should have no outgoing transitions"
            )

    def test_created_can_transition_to_validated(self) -> None:
        assert OrderState.VALIDATED in LEGAL_ORDER_TRANSITIONS[OrderState.CREATED]

    def test_created_can_transition_to_rejected(self) -> None:
        assert OrderState.REJECTED in LEGAL_ORDER_TRANSITIONS[OrderState.CREATED]

    def test_created_can_transition_to_cancelled(self) -> None:
        assert OrderState.CANCELLED in LEGAL_ORDER_TRANSITIONS[OrderState.CREATED]

    def test_risk_approved_is_required_before_submission(self) -> None:
        """Per AD-004: no exposure-increasing order bypasses risk authorization."""
        assert OrderState.SUBMISSION_PENDING in LEGAL_ORDER_TRANSITIONS[OrderState.RISK_APPROVED]
        # CREATED should not jump directly to SUBMISSION_PENDING
        assert OrderState.SUBMISSION_PENDING not in LEGAL_ORDER_TRANSITIONS[OrderState.CREATED]

    def test_safe_halt_can_reach_reconciliation(self) -> None:
        assert OrderState.RECONCILIATION_REQUIRED in LEGAL_ORDER_TRANSITIONS[OrderState.SAFE_HALT]

    def test_unknown_outcome_requires_reconciliation(self) -> None:
        """Per Section 05.3: unknown outcomes require exchange reconciliation."""
        assert (
            OrderState.RECONCILIATION_REQUIRED
            in LEGAL_ORDER_TRANSITIONS[OrderState.UNKNOWN_OUTCOME]
        )
        assert OrderState.SAFE_HALT in LEGAL_ORDER_TRANSITIONS[OrderState.UNKNOWN_OUTCOME]

    def test_no_state_can_transition_to_created(self) -> None:
        """CREATED is an entry state — no state transitions to it."""
        for state, targets in LEGAL_ORDER_TRANSITIONS.items():
            assert OrderState.CREATED not in targets, (
                f"State {state} should not transition to CREATED"
            )

    def test_thirteen_states_exist(self) -> None:
        """Per Section 05.2: exactly 13 order states."""
        assert len(list(OrderState)) == 13
