"""Deterministic agent orchestrator for Kian Trading Intelligence.

Per deliverable 3: deterministic orchestration — agents are coordinated in a
fixed deterministic pipeline. The orchestrator does NOT make decisions; it
sequences the four agents in a fixed order and enforces that risk authorization
is obtained before any order execution.

Per AD-004: the Risk Kernel is NOT an agent. It is an independent deterministic
safety service. The orchestrator delegates to it but does not control it.

Per AD-020: policy-governed agent orchestration with typed contracts,
explicit permissions, and deterministic cross-verification.

Per AD-022: decision traceability — every orchestrated pipeline run
produces a complete decision trace.

The pipeline:
1. Market Intelligence Agent → observe market, compute features
2. Strategy & Portfolio Agent → evaluate strategy, propose position
3. Risk Kernel → assess and authorize (NOT an agent — independent)
4. Execution & Supervisor Agent → submit order through exchange
5. (Mining Operations Agent is separate — for mining simulations)

No agent may skip the Risk Kernel. No agent may authorize another agent's
execution. The orchestrator enforces this by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from contracts.agents import (
    AgentResult,
    AgentType,
    DecisionTraceId,
)
from contracts.llm_gateway import LLMGateway
from contracts.market_data import Candle
from contracts.order import OrderIntent
from contracts.risk import RiskAssessment
from contracts.strategy import StrategyVersion
from contracts.trading import TradingSession
from services.agents.execution_supervisor import ExecutionSupervisorAgent
from services.agents.market_intelligence import MarketIntelligenceAgent
from services.agents.mining_operations import (
    MiningOperationsAgent,
    MiningSimulationInput,
)
from services.agents.strategy_portfolio import StrategyPortfolioAgent
from services.risk_kernel.kernel import RiskKernel


@dataclass
class OrchestratorResult:
    """Result of a full orchestrated agent pipeline run.

    Per deliverable 12: decision traceability — the full trace is preserved.
    """

    trace_id: DecisionTraceId
    success: bool
    market_result: AgentResult | None = None
    strategy_result: AgentResult | None = None
    risk_assessment: RiskAssessment | None = None
    execution_result: AgentResult | None = None
    error: str = ""
    steps: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


class AgentOrchestrator:
    """Deterministic agent orchestrator (deliverable 3).

    Coordinates the four agents in a fixed deterministic pipeline:
    1. Market Intelligence → observe and compute features
    2. Strategy & Portfolio → evaluate and propose
    3. Risk Kernel → assess and authorize (independent, NOT an agent)
    4. Execution & Supervisor → submit through exchange

    The orchestrator does NOT make financial decisions. It sequences
    agents and enforces that the Risk Kernel is consulted before
    execution. No agent may skip the kernel.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        market_agent: MarketIntelligenceAgent,
        strategy_agent: StrategyPortfolioAgent,
        execution_agent: ExecutionSupervisorAgent,
        risk_kernel: RiskKernel,
        llm_gateway: LLMGateway | None = None,
        mining_agent: MiningOperationsAgent | None = None,
    ) -> None:
        self._market_agent = market_agent
        self._strategy_agent = strategy_agent
        self._execution_agent = execution_agent
        self._risk_kernel = risk_kernel
        self._llm_gateway = llm_gateway
        self._mining_agent = mining_agent

    def run_trading_pipeline(  # noqa: PLR0913
        self,
        *,
        tenant_id: str,
        profile_id: str,
        candles: list[Candle],
        strategy: StrategyVersion,
        current_price: str,
        session: TradingSession | None = None,
    ) -> OrchestratorResult:
        """Run the full deterministic trading pipeline.

        Per deliverable 3: deterministic orchestration.
        Per AD-004: the Risk Kernel is consulted between strategy
        proposal and execution — no agent may bypass it.
        """
        trace_id = DecisionTraceId.generate()
        steps: list[str] = []
        result = OrchestratorResult(trace_id=trace_id, success=False)

        # ── Step 1: Market Intelligence ──
        steps.append("market_intelligence")
        market_ctx = self._market_agent.create_context(
            tenant_id=tenant_id,
            profile_id=profile_id,
        )
        market_result = self._market_agent.observe_market(market_ctx, candles)
        result.market_result = market_result

        if not market_result.success:
            result.error = f"Market intelligence failed: {market_result.error}"
            result.steps = steps
            return result

        # ── Step 2: Strategy & Portfolio — evaluate ──
        steps.append("strategy_evaluation")
        strategy_ctx = self._strategy_agent.create_context(
            tenant_id=tenant_id,
            profile_id=profile_id,
        )
        strategy_result = self._strategy_agent.evaluate_strategy(
            strategy_ctx,
            strategy,
            candles,
        )
        result.strategy_result = strategy_result

        if not strategy_result.success:
            result.error = f"Strategy evaluation failed: {strategy_result.error}"
            result.steps = steps
            return result

        # ── Step 3: Strategy & Portfolio — propose position ──
        steps.append("strategy_proposal")
        proposal_result = self._strategy_agent.propose_position(
            strategy_ctx,
            strategy,
            current_price,
        )

        if not proposal_result.success:
            result.error = f"Position proposal failed: {proposal_result.error}"
            result.steps = steps
            return result

        # ── Step 4: Risk Kernel — assess (NOT an agent) ──
        # Per AD-004: the Risk Kernel is independent. The orchestrator
        # delegates to it but does NOT control its decision.
        steps.append("risk_kernel_assessment")
        result = self._assess_and_execute(
            tenant_id=tenant_id,
            profile_id=profile_id,
            strategy=strategy,
            current_price=current_price,
            session=session,
            result=result,
            steps=steps,
        )
        return result

    def _assess_and_execute(  # noqa: PLR0913
        self,
        *,
        tenant_id: str,
        profile_id: str,
        strategy: StrategyVersion,
        current_price: str,
        session: TradingSession | None,
        result: OrchestratorResult,
        steps: list[str],
    ) -> OrchestratorResult:
        """Run risk assessment and execution (steps 4-5).

        Extracted from run_trading_pipeline to keep return count
        under ruff PLR0911.
        """
        if strategy.parameters is None:
            result.error = "Strategy has no parameters."
            result.steps = steps
            return result

        intent = OrderIntent.create(
            tenant_id=tenant_id,
            profile_id=profile_id,
            symbol=strategy.parameters.symbol,
            side=strategy.parameters.side,
            quantity=strategy.parameters.quantity,
        )

        assessment = self._risk_kernel.assess(
            intent,
            current_price=current_price,
            session=session,
        )
        result.risk_assessment = assessment

        if not assessment.authorized:
            result.error = f"Risk kernel denied: {assessment.reason}"
            result.steps = steps
            return result

        # ── Step 5: Execution & Supervisor — submit ──
        steps.append("execution_submit")
        exec_ctx = self._execution_agent.create_context(
            tenant_id=tenant_id,
            profile_id=profile_id,
        )
        exec_result = self._execution_agent.submit_order(
            exec_ctx,
            intent,
            current_price=current_price,
            session=session,
        )
        result.execution_result = exec_result

        if not exec_result.success:
            result.error = f"Execution failed: {exec_result.error}"
            result.steps = steps
            return result

        result.success = True
        result.steps = steps
        return result

    def run_mining_pipeline(
        self,
        *,
        tenant_id: str,
        profile_id: str,
        inputs: MiningSimulationInput,
        btc_price: str,
    ) -> AgentResult:
        """Run the mining simulation pipeline.

        Per AD-015: mining simulation. The Mining Operations Agent
        simulates profitability. No real hardware access.
        """
        if self._mining_agent is None:
            return AgentResult.failure(
                agent_type=AgentType.MINING_OPERATIONS,
                error="Mining agent not configured.",
            )

        ctx = self._mining_agent.create_context(
            tenant_id=tenant_id,
            profile_id=profile_id,
        )
        return self._mining_agent.simulate_mining(ctx, inputs, btc_price)

    @property
    def market_agent(self) -> MarketIntelligenceAgent:
        return self._market_agent

    @property
    def strategy_agent(self) -> StrategyPortfolioAgent:
        return self._strategy_agent

    @property
    def execution_agent(self) -> ExecutionSupervisorAgent:
        return self._execution_agent

    @property
    def risk_kernel(self) -> RiskKernel:
        return self._risk_kernel

    @property
    def mining_agent(self) -> MiningOperationsAgent | None:
        return self._mining_agent
