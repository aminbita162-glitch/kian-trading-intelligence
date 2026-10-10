"""Strategy & Portfolio Agent for Kian Trading Intelligence.

Per Section 04.2: Strategy & Portfolio Agent.
- Responsibilities: Strategy evaluation; portfolio analysis; position
  proposals; versioned trade intents.
- Prohibited: Risk override or self-authorized execution.

Per AD-012: strategy validation pipeline — backtesting, out-of-sample,
walk-forward, paper trading.
Per AD-020: typed agent contracts with explicit permissions.
Per AD-022: decision traceability.

The Strategy & Portfolio Agent evaluates strategies through the full
validation pipeline (backtest → out-of-sample → walk-forward → paper trading)
and proposes position changes. Proposals are NOT executable orders; they
must pass through the Risk Kernel before reaching the Execution Agent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from contracts.agents import (
    AgentContext,
    AgentId,
    AgentPermission,
    AgentResult,
    AgentType,
    DecisionTrace,
    DecisionTraceEntry,
    DecisionTraceId,
)
from contracts.market_data import Candle
from contracts.order import OrderIntent
from contracts.strategy import (
    StrategyId,
    StrategyParameters,
    StrategyStatus,
    StrategyVersion,
)
from contracts.validation import (
    ValidationStage,
    ValidationStatus,
    run_backtest,
    run_out_of_sample,
    run_paper_trading,
    run_walk_forward,
)


class StrategyPortfolioAgent:
    """Strategy & Portfolio Agent (Section 04.2).

    Evaluates strategies and proposes positions. Proposals are NOT
    executable orders — they must pass through the Risk Kernel.

    Prohibited: RISK_OVERRIDE, SELF_AUTHORIZED_EXECUTION.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyVersion] = {}
        self._strategy_versions: dict[str, list[StrategyVersion]] = {}

    def evaluate_strategy(
        self,
        ctx: AgentContext,
        strategy: StrategyVersion,
        candles: list[Candle],
    ) -> AgentResult:
        """Evaluate a strategy through the full validation pipeline.

        Per AD-012: backtesting, out-of-sample, walk-forward, paper trading.
        Per deliverable 3: deterministic orchestration.
        """
        ctx.check_permission(AgentPermission.EVALUATE_STRATEGY)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        if strategy.parameters is None:
            trace.complete("Strategy has no parameters", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error="Strategy has no parameters.",
                trace_id=trace.trace_id,
            )

        MIN_CANDLES_FOR_EVAL = 10
        if not candles or len(candles) < MIN_CANDLES_FOR_EVAL:
            trace.complete("Insufficient candles for evaluation", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error=f"Need >= {MIN_CANDLES_FOR_EVAL} candles for evaluation.",
                trace_id=trace.trace_id,
            )

        # If already VALIDATED or ACTIVE, the strategy has passed the pipeline —
        # no re-validation needed. Just verify and return.
        if strategy.status in (StrategyStatus.VALIDATED, StrategyStatus.ACTIVE):
            self._strategies[str(strategy.version_id)] = strategy
            trace.complete("Strategy already validated", authorized=True)
            return AgentResult.ok(
                agent_type=ctx.agent_type,
                data={
                    "strategy_status": strategy.status.value,
                    "is_guaranteed_profitable": "false",
                },
                trace_id=trace.trace_id,
            )

        # DRAFT strategy — run the full validation pipeline with state transitions
        validated_strategy, stage_result = self._run_validation_stages(
            ctx, strategy, candles, trace
        )
        if stage_result is not None:
            return stage_result

        # All stages passed — promote PAPER_TRADING → VALIDATED
        assert validated_strategy is not None
        validated = validated_strategy.transition_to(StrategyStatus.VALIDATED)
        self._strategies[str(validated.version_id)] = validated

        trace.complete("Strategy validated through full pipeline", authorized=True)
        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={
                "strategy_status": validated.status.value,
                "is_guaranteed_profitable": "false",
            },
            trace_id=trace.trace_id,
        )

    def _run_validation_stages(
        self,
        ctx: AgentContext,
        strategy: StrategyVersion,
        candles: list[Candle],
        trace: DecisionTrace,
    ) -> tuple[StrategyVersion | None, AgentResult | None]:
        """Run the four validation pipeline stages with state transitions.

        Returns (final_strategy, None) if all stages passed — the strategy is
        in PAPER_TRADING state, ready for promotion to VALIDATED. Returns
        (None, failure_result) if any stage failed. Each stage transitions
        the strategy through the legal state path: DRAFT → BACKTESTING →
        OUT_OF_SAMPLE → WALK_FORWARD → PAPER_TRADING.
        """
        assert strategy.parameters is not None  # checked by caller
        side = strategy.parameters.side

        # Stage 1: Backtest (DRAFT → BACKTESTING)
        strategy = strategy.transition_to(StrategyStatus.BACKTESTING)
        bt_result = run_backtest(strategy.version_id, candles, side)
        trace.add_entry(
            DecisionTraceEntry(
                step="backtest",
                agent_type=ctx.agent_type,
                permission=AgentPermission.EVALUATE_STRATEGY,
                timestamp=datetime.now(UTC),
                detail=f"status={bt_result.status.value}, return={bt_result.total_return_pct}",
                data={"stage": ValidationStage.BACKTEST.value},
            )
        )

        if bt_result.status is not ValidationStatus.PASSED:
            trace.complete("Backtest failed", authorized=False)
            return None, AgentResult.failure(
                agent_type=ctx.agent_type,
                error=f"Backtest failed: {bt_result.total_return_pct}% return.",
                trace_id=trace.trace_id,
            )

        # Stage 2: Out-of-sample (BACKTESTING → OUT_OF_SAMPLE)
        strategy = strategy.transition_to(StrategyStatus.OUT_OF_SAMPLE)
        oos_result = run_out_of_sample(strategy.version_id, candles, side)
        trace.add_entry(
            DecisionTraceEntry(
                step="out_of_sample",
                agent_type=ctx.agent_type,
                permission=AgentPermission.EVALUATE_STRATEGY,
                timestamp=datetime.now(UTC),
                detail=f"status={oos_result.status.value}, return={oos_result.total_return_pct}",
                data={"stage": ValidationStage.OUT_OF_SAMPLE.value},
            )
        )

        if oos_result.status is not ValidationStatus.PASSED:
            trace.complete("Out-of-sample failed", authorized=False)
            return None, AgentResult.failure(
                agent_type=ctx.agent_type,
                error=f"Out-of-sample failed: {oos_result.total_return_pct}% return.",
                trace_id=trace.trace_id,
            )

        # Stage 3: Walk-forward (OUT_OF_SAMPLE → WALK_FORWARD)
        strategy = strategy.transition_to(StrategyStatus.WALK_FORWARD)
        wf_result = run_walk_forward(strategy.version_id, candles, side)
        trace.add_entry(
            DecisionTraceEntry(
                step="walk_forward",
                agent_type=ctx.agent_type,
                permission=AgentPermission.EVALUATE_STRATEGY,
                timestamp=datetime.now(UTC),
                detail=f"passed={wf_result.passed}, avg_test={wf_result.avg_test_return_pct}",
                data={"stage": ValidationStage.WALK_FORWARD.value},
            )
        )

        if not wf_result.passed:
            trace.complete("Walk-forward failed", authorized=False)
            return None, AgentResult.failure(
                agent_type=ctx.agent_type,
                error=f"Walk-forward failed: avg test return {wf_result.avg_test_return_pct}%.",
                trace_id=trace.trace_id,
            )

        # Stage 4: Paper trading (WALK_FORWARD → PAPER_TRADING)
        strategy = strategy.transition_to(StrategyStatus.PAPER_TRADING)
        pt_result = run_paper_trading(strategy.version_id, candles, side)
        trace.add_entry(
            DecisionTraceEntry(
                step="paper_trading",
                agent_type=ctx.agent_type,
                permission=AgentPermission.EVALUATE_STRATEGY,
                timestamp=datetime.now(UTC),
                detail=f"status={pt_result.status.value}, return={pt_result.total_return_pct}",
                data={"stage": ValidationStage.PAPER_TRADING.value},
            )
        )

        if pt_result.status is not ValidationStatus.PASSED:
            trace.complete("Paper trading failed", authorized=False)
            return None, AgentResult.failure(
                agent_type=ctx.agent_type,
                error=f"Paper trading failed: {pt_result.total_return_pct}% return.",
                trace_id=trace.trace_id,
            )

        return strategy, None

    def propose_position(
        self,
        ctx: AgentContext,
        strategy: StrategyVersion,
        current_price: str,
    ) -> AgentResult:
        """Propose a position based on a validated strategy.

        Per Section 04.2: position proposals — NOT executable orders.
        Per deliverable 12: decision traceability.
        """
        ctx.check_permission(AgentPermission.PROPOSE_POSITION)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        if (
            strategy.status is not StrategyStatus.VALIDATED
            and strategy.status is not StrategyStatus.ACTIVE
        ):
            trace.complete("Strategy not validated", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error=f"Strategy status is {strategy.status.value}, must be validated or active.",
                trace_id=trace.trace_id,
            )

        if strategy.parameters is None:
            trace.complete("Strategy has no parameters", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error="Strategy has no parameters.",
                trace_id=trace.trace_id,
            )

        params = strategy.parameters
        trace.add_entry(
            DecisionTraceEntry(
                step="propose_position",
                agent_type=ctx.agent_type,
                permission=AgentPermission.PROPOSE_POSITION,
                timestamp=datetime.now(UTC),
                detail=f"symbol={params.symbol}, side={params.side}, qty={params.quantity}",
                data={
                    "requires_risk_authorization": "true",
                    "is_self_authorized": "false",
                },
            )
        )

        # Create a trade intent — NOT an order. This must pass through
        # the Risk Kernel before the Execution Agent can submit it.
        intent = OrderIntent.create(
            tenant_id=ctx.tenant_id,
            profile_id=ctx.profile_id,
            symbol=params.symbol,
            side=params.side,
            quantity=params.quantity,
        )

        trace.complete(
            "Position proposed — requires Risk Kernel authorization",
            authorized=False,  # proposal is NOT an authorization
        )

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={
                "intent_id": str(intent.intent_id),
                "symbol": params.symbol,
                "side": params.side,
                "quantity": params.quantity,
                "requires_risk_authorization": "true",
                "is_self_authorized": "false",
            },
            trace_id=trace.trace_id,
        )

    def version_trade_intent(
        self,
        ctx: AgentContext,
        tenant_id: str,
        name: str,
        parameters: StrategyParameters,
        strategy_id: StrategyId | None = None,
    ) -> AgentResult:
        """Create a new versioned strategy with immutable parameters.

        Per deliverable 4: strategy versioning.
        """
        ctx.check_permission(AgentPermission.VERSION_TRADE_INTENT)

        strategy = StrategyVersion.create(
            tenant_id=tenant_id,
            name=name,
            parameters=parameters,
            strategy_id=strategy_id if strategy_id is not None else None,
        )

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )
        trace.add_entry(
            DecisionTraceEntry(
                step="version_trade_intent",
                agent_type=ctx.agent_type,
                permission=AgentPermission.VERSION_TRADE_INTENT,
                timestamp=datetime.now(UTC),
                detail=f"version={strategy.version}, name={name}",
            )
        )
        trace.complete("Strategy version created", authorized=True)

        key = str(strategy.version_id)
        self._strategies[key] = strategy
        if tenant_id not in self._strategy_versions:
            self._strategy_versions[tenant_id] = []
        self._strategy_versions[tenant_id].append(strategy)

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={
                "version_id": key,
                "strategy_id": str(strategy.strategy_id),
                "version": str(strategy.version),
                "status": strategy.status.value,
            },
            trace_id=trace.trace_id,
        )

    def get_strategy(self, version_id: str) -> StrategyVersion | None:
        """Get a strategy version by ID."""
        return self._strategies.get(version_id)

    def create_context(
        self,
        tenant_id: str,
        profile_id: str,
        agent_id: AgentId | None = None,
        session_id: str = "",
    ) -> AgentContext:
        """Create an agent context for this agent type."""
        return AgentContext(
            agent_id=agent_id or AgentId.generate(),
            agent_type=AgentType.STRATEGY_PORTFOLIO,
            tenant_id=tenant_id,
            profile_id=profile_id,
            session_id=session_id,
        )
