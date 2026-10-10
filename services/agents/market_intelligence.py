"""Market Intelligence Agent for Kian Trading Intelligence.

Per Section 04.1: Market Intelligence Agent.
- Responsibilities: Market observations; feature computation; market-condition
  analysis; bounded research summaries.
- Prohibited: Direct trade execution.

Per AD-003: routine indicators must not depend on LLM availability.
Per AD-011: LLM outputs must never be authoritative for prices.
Per AD-020: typed agent contracts with explicit permissions.

The Market Intelligence Agent observes market data and computes deterministic
features. It may request bounded LLM research summaries through the LLM gateway,
but the LLM output is advisory only — never authoritative.
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
from contracts.indicators import (
    exponential_moving_average,
    relative_strength_index,
    simple_moving_average,
    volatility,
)
from contracts.llm_gateway import LLMGateway, LLMRequest, LLMRequestId, LLMRequestType
from contracts.market_data import Candle


class MarketIntelligenceAgent:
    """Market Intelligence Agent (Section 04.1).

    Observes market data and computes deterministic features.
    May request bounded LLM research summaries.

    Prohibited: direct trade execution (AgentProhibition.DIRECT_TRADE_EXECUTION).
    """

    def __init__(self, llm_gateway: LLMGateway | None = None) -> None:
        self._llm_gateway = llm_gateway

    def observe_market(
        self,
        ctx: AgentContext,
        candles: list[Candle],
    ) -> AgentResult:
        """Observe market data and compute deterministic indicators.

        Per AD-003: deterministic — same candles = same result.
        """
        ctx.check_permission(AgentPermission.OBSERVE_MARKET)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        trace.add_entry(
            DecisionTraceEntry(
                step="observe_market.start",
                agent_type=ctx.agent_type,
                permission=AgentPermission.OBSERVE_MARKET,
                timestamp=datetime.now(UTC),
                detail=f"candles={len(candles)}",
            )
        )

        if not candles:
            trace.complete("No candles provided", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error="No candles provided for observation.",
                trace_id=trace.trace_id,
            )

        MIN_SMA_CANDLES = 5
        MIN_EMA_CANDLES = 10
        MIN_RSI_CANDLES = 15
        indicators: dict[str, str] = {}
        if len(candles) >= MIN_SMA_CANDLES:
            sma = simple_moving_average(candles, window=MIN_SMA_CANDLES)
            indicators["sma_5"] = sma.value
        if len(candles) >= MIN_EMA_CANDLES:
            ema = exponential_moving_average(candles, window=MIN_EMA_CANDLES)
            indicators["ema_10"] = ema.value
        if len(candles) >= MIN_RSI_CANDLES:
            rsi = relative_strength_index(candles, window=14)
            indicators["rsi_14"] = rsi.value
        if len(candles) >= MIN_SMA_CANDLES:
            vol = volatility(candles, window=MIN_SMA_CANDLES)
            indicators["vol_5"] = vol.value

        indicators["last_close"] = candles[-1].close
        indicators["candle_count"] = str(len(candles))

        trace.add_entry(
            DecisionTraceEntry(
                step="observe_market.complete",
                agent_type=ctx.agent_type,
                permission=AgentPermission.COMPUTE_FEATURES,
                timestamp=datetime.now(UTC),
                detail=f"indicators={len(indicators)}",
            )
        )
        trace.complete("Market observation complete", authorized=True)

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data=indicators,
            trace_id=trace.trace_id,
        )

    def compute_features(
        self,
        ctx: AgentContext,
        candles: list[Candle],
        window: int = 5,
    ) -> AgentResult:
        """Compute deterministic technical features.

        Per AD-003: deterministic — no LLM dependency.
        """
        ctx.check_permission(AgentPermission.COMPUTE_FEATURES)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        if not candles or len(candles) < window:
            trace.complete("Insufficient data for features", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error=f"Need >= {window} candles, got {len(candles)}.",
                trace_id=trace.trace_id,
            )

        sma = simple_moving_average(candles, window=window)
        ema = exponential_moving_average(candles, window=window)

        trace.add_entry(
            DecisionTraceEntry(
                step="compute_features",
                agent_type=ctx.agent_type,
                permission=AgentPermission.COMPUTE_FEATURES,
                timestamp=datetime.now(UTC),
                detail=f"window={window}",
            )
        )
        trace.complete("Features computed", authorized=True)

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={"sma": sma.value, "ema": ema.value},
            trace_id=trace.trace_id,
        )

    def research_summary(
        self,
        ctx: AgentContext,
        topic: str,
        estimated_tokens: int = 100,
    ) -> AgentResult:
        """Request a bounded LLM research summary.

        Per deliverable 10: LLM output is advisory only — NOT authoritative.
        Per deliverable 11: token budget enforced by the gateway.
        """
        ctx.check_permission(AgentPermission.RESEARCH_SUMMARY)

        if self._llm_gateway is None:
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error="LLM gateway not configured.",
            )

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        request = LLMRequest(
            request_id=LLMRequestId.generate(),
            tenant_id=ctx.tenant_id,
            request_type=LLMRequestType.MARKET_RESEARCH,
            prompt=f"Research summary: {topic}",
            estimated_tokens=estimated_tokens,
        )

        try:
            response = self._llm_gateway.submit_request(request)
        except Exception as exc:
            trace.complete(f"LLM request failed: {exc}", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error=str(exc),
                trace_id=trace.trace_id,
            )

        trace.add_entry(
            DecisionTraceEntry(
                step="research_summary.llm",
                agent_type=ctx.agent_type,
                permission=AgentPermission.RESEARCH_SUMMARY,
                timestamp=datetime.now(UTC),
                detail=f"tokens={response.tokens_used}",
                data={"is_authoritative": "false"},
            )
        )
        trace.complete("Research summary obtained (advisory only)", authorized=True)

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={
                "summary": response.text,
                "tokens_used": str(response.tokens_used),
                "is_authoritative": "false",
            },
            trace_id=trace.trace_id,
        )

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
            agent_type=AgentType.MARKET_INTELLIGENCE,
            tenant_id=tenant_id,
            profile_id=profile_id,
            session_id=session_id,
        )
