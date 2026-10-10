"""Tests for strategy versioning contracts — Phase 06 deliverable 4.

Per AD-012: strategy validation pipeline.
Per deliverable 4: strategy versioning with immutable parameters.
"""

from __future__ import annotations

import pytest

from contracts.strategy import (
    LEGAL_STRATEGY_TRANSITIONS,
    StrategyId,
    StrategyParameters,
    StrategyStatus,
    StrategyVersion,
    StrategyVersionId,
)


class TestStrategyParameters:
    """Test immutable strategy parameters."""

    def test_valid_parameters(self) -> None:
        params = StrategyParameters(
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
            entry_signal="sma_cross",
            exit_signal="sma_cross_exit",
        )
        assert params.symbol == "BTC/USDT"
        assert params.side == "buy"

    def test_invalid_side(self) -> None:
        with pytest.raises(ValueError, match="Invalid side"):
            StrategyParameters(
                symbol="BTC/USDT",
                side="invalid",
                quantity="1.0",
                entry_signal="test",
                exit_signal="test",
            )

    def test_invalid_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity must be positive"):
            StrategyParameters(
                symbol="BTC/USDT",
                side="buy",
                quantity="0",
                entry_signal="test",
                exit_signal="test",
            )

    def test_negative_stop_loss(self) -> None:
        with pytest.raises(ValueError, match="stop_loss_pct"):
            StrategyParameters(
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
                entry_signal="test",
                exit_signal="test",
                stop_loss_pct="-1.0",
            )

    def test_is_frozen(self) -> None:
        params = StrategyParameters(
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
            entry_signal="test",
            exit_signal="test",
        )
        with pytest.raises(AttributeError):
            params.symbol = "ETH/USDT"  # type: ignore[misc]


class TestStrategyVersion:
    """Test strategy version lifecycle."""

    def test_create_strategy(self) -> None:
        params = StrategyParameters(
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
            entry_signal="test",
            exit_signal="test",
        )
        strategy = StrategyVersion.create(
            tenant_id="tenant-1",
            name="SMA Cross",
            parameters=params,
        )
        assert strategy.status is StrategyStatus.DRAFT
        assert strategy.version == 1
        assert strategy.parameters is not None

    def test_version_must_be_positive(self) -> None:
        params = StrategyParameters(
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
            entry_signal="test",
            exit_signal="test",
        )
        with pytest.raises(ValueError, match="Version must be >= 1"):
            StrategyVersion(
                version_id=StrategyVersionId.generate(),
                strategy_id=StrategyId.generate(),
                tenant_id="t1",
                version=0,
                name="test",
                parameters=params,
            )

    def test_legal_transitions(self) -> None:
        """Verify the strategy validation pipeline transitions."""
        assert StrategyStatus.BACKTESTING in LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.DRAFT]
        assert (
            StrategyStatus.OUT_OF_SAMPLE in LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.BACKTESTING]
        )
        assert (
            StrategyStatus.WALK_FORWARD in LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.OUT_OF_SAMPLE]
        )
        assert (
            StrategyStatus.PAPER_TRADING in LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.WALK_FORWARD]
        )
        assert StrategyStatus.VALIDATED in LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.PAPER_TRADING]
        assert StrategyStatus.ACTIVE in LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.VALIDATED]

    def test_illegal_transition(self) -> None:
        params = StrategyParameters(
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
            entry_signal="test",
            exit_signal="test",
        )
        strategy = StrategyVersion.create(
            tenant_id="t1",
            name="test",
            parameters=params,
        )
        with pytest.raises(ValueError, match="Illegal strategy transition"):
            strategy.transition_to(StrategyStatus.ACTIVE)  # skip stages

    def test_legal_transition_chain(self) -> None:
        params = StrategyParameters(
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
            entry_signal="test",
            exit_signal="test",
        )
        strategy = StrategyVersion.create(
            tenant_id="t1",
            name="test",
            parameters=params,
        )
        bt = strategy.transition_to(StrategyStatus.BACKTESTING)
        assert bt.status is StrategyStatus.BACKTESTING
        oos = bt.transition_to(StrategyStatus.OUT_OF_SAMPLE)
        assert oos.status is StrategyStatus.OUT_OF_SAMPLE
        wf = oos.transition_to(StrategyStatus.WALK_FORWARD)
        assert wf.status is StrategyStatus.WALK_FORWARD
        pt = wf.transition_to(StrategyStatus.PAPER_TRADING)
        assert pt.status is StrategyStatus.PAPER_TRADING
        val = pt.transition_to(StrategyStatus.VALIDATED)
        assert val.status is StrategyStatus.VALIDATED
        active = val.transition_to(StrategyStatus.ACTIVE)
        assert active.status is StrategyStatus.ACTIVE
        assert active.activated_at is not None

    def test_rejected_is_terminal(self) -> None:
        assert len(LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.REJECTED]) == 0

    def test_superseded_is_terminal(self) -> None:
        assert len(LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.SUPERSEDED]) == 0

    def test_active_can_only_supersede(self) -> None:
        transitions = LEGAL_STRATEGY_TRANSITIONS[StrategyStatus.ACTIVE]
        assert StrategyStatus.SUPERSEDED in transitions
        assert StrategyStatus.DRAFT not in transitions
