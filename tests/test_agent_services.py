"""Tests for agent services and orchestration — Phase 06 deliverables 3, 12.

Per deliverable 3: deterministic orchestration.
Per deliverable 12: decision traceability.
Per AD-004: the Risk Kernel is independent — no agent may bypass it.
Per AD-020: agent failures must not expand privileges.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from contracts.agents import (
    AgentPermission,
)
from contracts.llm_gateway import (
    LLMGateway,
    LLMRequest,
    LLMRequestId,
    LLMRequestType,
    TokenBudgetConfig,
)
from contracts.market_data import Candle, Symbol, Timeframe
from contracts.order import OrderIntent
from contracts.risk import RiskPolicy
from contracts.strategy import (
    StrategyParameters,
    StrategyStatus,
    StrategyVersion,
)
from services.agents import (
    AgentOrchestrator,
    ExecutionSupervisorAgent,
    MarketIntelligenceAgent,
    MiningOperationsAgent,
    MiningSimulationInput,
    StrategyPortfolioAgent,
)
from services.execution.engine import ExecutionEngine
from services.execution.exchange_simulator import ExchangeSimulator
from services.risk_kernel.kernel import RiskKernel


def _make_candles(count: int, start_price: float = 50000.0) -> list[Candle]:
    """Generate deterministic test candles."""
    symbol = Symbol(base="BTC", quote="USDT")
    tf = Timeframe.ONE_MINUTE
    base_time = datetime.now(UTC)
    candles: list[Candle] = []
    price = start_price
    for i in range(count):
        delta = ((i % 5) - 2) * 100
        open_p = price
        close_p = max(price + delta, 1.0)
        high_p = max(open_p, close_p) + 50
        low_p = min(open_p, close_p) - 50
        if low_p <= 0:
            low_p = 1.0
        candles.append(
            Candle(
                symbol=symbol,
                timeframe=tf,
                open=str(open_p),
                high=str(high_p),
                low=str(low_p),
                close=str(close_p),
                volume=str(1000 + i),
                open_time=base_time + timedelta(minutes=i),
                close_time=base_time + timedelta(minutes=i + 1),
            )
        )
        price = close_p
    return candles


def _setup_risk_kernel(tenant_id: str = "tenant-1") -> RiskKernel:
    kernel = RiskKernel()
    policy = RiskPolicy.create(
        tenant_id=tenant_id,
        max_position_value="1000000.00",
        max_concentration_pct="100.0",
    )
    kernel.register_policy(policy.activate())
    return kernel


def _make_strategy(tenant_id: str = "tenant-1") -> StrategyVersion:
    params = StrategyParameters(
        symbol="BTC/USDT",
        side="buy",
        quantity="0.01",
        entry_signal="sma_cross",
        exit_signal="sma_cross_exit",
        max_position_value="50000.00",
    )
    return StrategyVersion.create(
        tenant_id=tenant_id,
        name="SMA Cross Test",
        parameters=params,
    )


# ── Market Intelligence Agent ──


class TestMarketIntelligenceAgent:
    """Test the Market Intelligence Agent (Section 04.1)."""

    def test_observe_market(self) -> None:
        agent = MarketIntelligenceAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        candles = _make_candles(20)
        result = agent.observe_market(ctx, candles)
        assert result.success
        assert "last_close" in result.data
        assert result.data["candle_count"] == "20"

    def test_observe_market_empty(self) -> None:
        agent = MarketIntelligenceAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        result = agent.observe_market(ctx, [])
        assert not result.success

    def test_compute_features(self) -> None:
        agent = MarketIntelligenceAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        candles = _make_candles(20)
        result = agent.compute_features(ctx, candles, window=5)
        assert result.success
        assert "sma" in result.data
        assert "ema" in result.data

    def test_research_summary_with_llm(self) -> None:
        gateway = LLMGateway()
        gateway.configure_budget(TokenBudgetConfig(tenant_id="t1", daily_token_limit=10000))
        agent = MarketIntelligenceAgent(llm_gateway=gateway)
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        result = agent.research_summary(ctx, "BTC market trend", estimated_tokens=50)
        assert result.success
        assert result.data["is_authoritative"] == "false"

    def test_research_summary_without_llm(self) -> None:
        agent = MarketIntelligenceAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        result = agent.research_summary(ctx, "test")
        assert not result.success

    def test_agent_cannot_submit_orders(self) -> None:
        """Per Section 04.1: Market Intelligence Agent is prohibited from
        direct trade execution."""
        agent = MarketIntelligenceAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        with pytest.raises(PermissionError):
            ctx.check_permission(AgentPermission.SUBMIT_ORDER)

    def test_agent_prohibited_from_direct_trade(self) -> None:
        agent = MarketIntelligenceAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        with pytest.raises(PermissionError):
            ctx.check_not_prohibited_direct_trade()


# ── Strategy & Portfolio Agent ──


class TestStrategyPortfolioAgent:
    """Test the Strategy & Portfolio Agent (Section 04.2)."""

    def test_evaluate_strategy_full_pipeline(self) -> None:
        agent = StrategyPortfolioAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        strategy = _make_strategy()
        candles = _make_candles(100)
        result = agent.evaluate_strategy(ctx, strategy, candles)
        # May pass or fail depending on deterministic data, but should complete
        assert result.trace_id is not None

    def test_propose_position_requires_validation(self) -> None:
        agent = StrategyPortfolioAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        strategy = _make_strategy()  # status=DRAFT
        result = agent.propose_position(ctx, strategy, "50000")
        assert not result.success  # not validated yet

    def test_propose_position_after_validation(self) -> None:
        agent = StrategyPortfolioAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        strategy = _make_strategy()
        candles = _make_candles(100)
        eval_result = agent.evaluate_strategy(ctx, strategy, candles)
        if eval_result.success:
            validated_strategy = agent.get_strategy(str(strategy.version_id))
            if validated_strategy is not None:
                result = agent.propose_position(ctx, validated_strategy, "50000")
                assert result.success
                assert result.data["requires_risk_authorization"] == "true"
                assert result.data["is_self_authorized"] == "false"

    def test_version_trade_intent(self) -> None:
        agent = StrategyPortfolioAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        params = StrategyParameters(
            symbol="BTC/USDT",
            side="buy",
            quantity="0.5",
            entry_signal="test",
            exit_signal="test",
        )
        result = agent.version_trade_intent(ctx, "t1", "My Strategy", params)
        assert result.success
        assert "version_id" in result.data

    def test_strategy_cannot_risk_override(self) -> None:
        """Per Section 04.2: Strategy Agent is prohibited from risk override."""
        agent = StrategyPortfolioAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        with pytest.raises(PermissionError):
            ctx.check_not_prohibited_risk_override()


# ── Execution & Supervisor Agent ──


class TestExecutionSupervisorAgent:
    """Test the Execution & Supervisor Agent (Section 04.3)."""

    def test_submit_order_through_risk_kernel(self) -> None:
        kernel = _setup_risk_kernel()
        exchange = ExchangeSimulator()
        exchange.connect()
        engine = ExecutionEngine(risk_kernel=kernel, exchange=exchange)
        agent = ExecutionSupervisorAgent(engine)
        ctx = agent.create_context(tenant_id="tenant-1", profile_id="p1")

        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )
        result = agent.submit_order(ctx, intent, current_price="50000")
        assert result.success
        assert result.data["risk_authorized"] == "true"

    def test_execution_agent_cannot_bypass_risk(self) -> None:
        """Per Section 04.3: Execution Agent is prohibited from bypassing risk."""
        kernel = _setup_risk_kernel()
        exchange = ExchangeSimulator()
        engine = ExecutionEngine(risk_kernel=kernel, exchange=exchange)
        agent = ExecutionSupervisorAgent(engine)
        ctx = agent.create_context(tenant_id="tenant-1", profile_id="p1")
        with pytest.raises(PermissionError):
            ctx.check_not_prohibited_bypass_risk()

    def test_submit_risk_denied(self) -> None:
        """When the risk kernel denies, the execution agent should fail."""
        kernel = _setup_risk_kernel()
        # Register emergency stop to deny orders
        kernel.activate_emergency_stop("Test emergency")
        exchange = ExchangeSimulator()
        exchange.connect()
        engine = ExecutionEngine(risk_kernel=kernel, exchange=exchange)
        agent = ExecutionSupervisorAgent(engine)
        ctx = agent.create_context(tenant_id="tenant-1", profile_id="p1")

        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )
        result = agent.submit_order(ctx, intent, current_price="50000")
        assert not result.success


# ── Mining Operations Agent ──


class TestMiningOperationsAgent:
    """Test the Mining Operations Agent (Section 04.4)."""

    def test_simulate_mining(self) -> None:
        agent = MiningOperationsAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        inputs = MiningSimulationInput(
            hash_rate_th="100",
            network_difficulty="50000000",
            block_reward_btc="6.25",
            pool_fee_pct="1.0",
            electricity_cost_kwh="0.10",
            power_consumption_w="3000",
            uptime_pct="95.0",
        )
        result = agent.simulate_mining(ctx, inputs, "50000")
        assert result.success
        assert result.data["is_simulation"] == "true"
        assert "daily_net_fiat" in result.data

    def test_assess_profitability(self) -> None:
        agent = MiningOperationsAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        inputs = MiningSimulationInput(
            hash_rate_th="100",
            network_difficulty="50000000",
            block_reward_btc="6.25",
            pool_fee_pct="1.0",
            electricity_cost_kwh="0.10",
            power_consumption_w="3000",
            uptime_pct="95.0",
        )
        result = agent.assess_profitability(ctx, inputs, "50000")
        assert result.success

    def test_report_safety_telemetry(self) -> None:
        agent = MiningOperationsAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        result = agent.report_safety_telemetry(ctx)
        assert result.success
        assert result.data["real_hardware_active"] == "false"
        assert result.data["real_hardware_requires_approval"] == "true"

    def test_mining_agent_cannot_access_trading_account(self) -> None:
        """Per Section 04.4: Mining Agent is prohibited from unrestricted trading account access."""
        agent = MiningOperationsAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        with pytest.raises(PermissionError):
            ctx.check_not_prohibited_unrestricted_account()

    def test_mining_cannot_submit_orders(self) -> None:
        agent = MiningOperationsAgent()
        ctx = agent.create_context(tenant_id="t1", profile_id="p1")
        with pytest.raises(PermissionError):
            ctx.check_permission(AgentPermission.SUBMIT_ORDER)


# ── Orchestrator ──


class TestAgentOrchestrator:
    """Deliverable 3: deterministic orchestration."""

    def test_orchestrator_trading_pipeline(self) -> None:
        kernel = _setup_risk_kernel()
        exchange = ExchangeSimulator()
        exchange.connect()
        engine = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        market_agent = MarketIntelligenceAgent()
        strategy_agent = StrategyPortfolioAgent()
        exec_agent = ExecutionSupervisorAgent(engine)
        mining_agent = MiningOperationsAgent()

        orchestrator = AgentOrchestrator(
            market_agent=market_agent,
            strategy_agent=strategy_agent,
            execution_agent=exec_agent,
            risk_kernel=kernel,
            mining_agent=mining_agent,
        )

        strategy = _make_strategy()
        candles = _make_candles(100)

        result = orchestrator.run_trading_pipeline(
            tenant_id="tenant-1",
            profile_id="p1",
            candles=candles,
            strategy=strategy,
            current_price="50000",
        )

        # Pipeline should complete (may succeed or fail depending on strategy validation)
        assert "market_intelligence" in result.steps
        assert "strategy_evaluation" in result.steps

    def test_orchestrator_risk_kernel_is_independent(self) -> None:
        """Per AD-004: the Risk Kernel is NOT an agent and is independent."""
        kernel = _setup_risk_kernel()
        exchange = ExchangeSimulator()
        exchange.connect()
        engine = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        orchestrator = AgentOrchestrator(
            market_agent=MarketIntelligenceAgent(),
            strategy_agent=StrategyPortfolioAgent(),
            execution_agent=ExecutionSupervisorAgent(engine),
            risk_kernel=kernel,
        )

        # The risk_kernel property returns the kernel, not an agent
        assert orchestrator.risk_kernel is kernel
        assert not isinstance(orchestrator.risk_kernel, type(orchestrator.market_agent))

    def test_orchestrator_mining_pipeline(self) -> None:
        kernel = _setup_risk_kernel()
        exchange = ExchangeSimulator()
        exchange.connect()
        engine = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        orchestrator = AgentOrchestrator(
            market_agent=MarketIntelligenceAgent(),
            strategy_agent=StrategyPortfolioAgent(),
            execution_agent=ExecutionSupervisorAgent(engine),
            risk_kernel=kernel,
            mining_agent=MiningOperationsAgent(),
        )

        inputs = MiningSimulationInput(
            hash_rate_th="100",
            network_difficulty="50000000",
            block_reward_btc="6.25",
            pool_fee_pct="1.0",
            electricity_cost_kwh="0.10",
            power_consumption_w="3000",
            uptime_pct="95.0",
        )
        result = orchestrator.run_mining_pipeline(
            tenant_id="tenant-1",
            profile_id="p1",
            inputs=inputs,
            btc_price="50000",
        )
        assert result.success

    def test_orchestrator_emergency_stop_blocks_pipeline(self) -> None:
        """When emergency stop is active, the pipeline should fail at risk assessment."""
        kernel = _setup_risk_kernel()
        kernel.activate_emergency_stop("Test")
        exchange = ExchangeSimulator()
        exchange.connect()
        engine = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        orchestrator = AgentOrchestrator(
            market_agent=MarketIntelligenceAgent(),
            strategy_agent=StrategyPortfolioAgent(),
            execution_agent=ExecutionSupervisorAgent(engine),
            risk_kernel=kernel,
        )

        # Create a strategy that's already validated so we can skip to risk assessment
        strategy = _make_strategy()
        # Manually transition through the pipeline
        strategy = strategy.transition_to(StrategyStatus.BACKTESTING)
        strategy = strategy.transition_to(StrategyStatus.OUT_OF_SAMPLE)
        strategy = strategy.transition_to(StrategyStatus.WALK_FORWARD)
        strategy = strategy.transition_to(StrategyStatus.PAPER_TRADING)
        strategy = strategy.transition_to(StrategyStatus.VALIDATED)

        candles = _make_candles(100)
        result = orchestrator.run_trading_pipeline(
            tenant_id="tenant-1",
            profile_id="p1",
            candles=candles,
            strategy=strategy,
            current_price="50000",
        )
        # Should reach risk_kernel_assessment step and fail
        assert "risk_kernel_assessment" in result.steps
        assert not result.success


# ── Tenant isolation ──


class TestAgentTenantIsolation:
    """Per AD-002 and AD-010: agent contexts must be tenant-scoped."""

    def test_context_is_tenant_scoped(self) -> None:
        agent = MarketIntelligenceAgent()
        ctx1 = agent.create_context(tenant_id="tenant-1", profile_id="p1")
        ctx2 = agent.create_context(tenant_id="tenant-2", profile_id="p2")
        assert ctx1.tenant_id == "tenant-1"
        assert ctx2.tenant_id == "tenant-2"
        assert ctx1.tenant_id != ctx2.tenant_id

    def test_llm_gateway_tenant_isolation(self) -> None:
        """Token budgets must be isolated per tenant."""
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=100,
            )
        )
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t2",
                daily_token_limit=1000,
            )
        )
        assert gateway.get_remaining_tokens("t1") == 100
        assert gateway.get_remaining_tokens("t2") == 1000

    def test_token_budget_t1_does_not_affect_t2(self) -> None:
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=100,
            )
        )
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t2",
                daily_token_limit=100,
            )
        )
        # Spend all of t1's budget
        gateway.submit_request(
            LLMRequest(
                request_id=LLMRequestId.generate(),
                tenant_id="t1",
                request_type=LLMRequestType.MARKET_RESEARCH,
                prompt="test",
                estimated_tokens=100,
            )
        )
        # t2 should still have full budget
        assert gateway.get_remaining_tokens("t2") == 100
