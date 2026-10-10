"""Mining Operations Agent for Kian Trading Intelligence.

Per Section 04.4: Mining Operations Agent.
- Responsibilities: Mining simulation; profitability assessment; pool/hardware
  integration coordination; safety telemetry and reporting.
- Prohibited: Unrestricted trading-account access.

Per AD-015: mining simulation and profitability validation. Real hardware
and pool integration require explicit approval and safety controls.

Per AD-020: typed agent contracts with explicit permissions.

The Mining Operations Agent simulates mining profitability. It does NOT
access trading accounts beyond what is needed for profitability reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

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


@dataclass
class MiningSimulationInput:
    """Inputs for a mining profitability simulation.

    Per AD-015: model hash rate; network difficulty; expected rewards;
    pool fees; electricity costs; equipment efficiency; hardware
    depreciation; temperature; downtime; net profitability and uncertainty.
    """

    hash_rate_th: str  # Terahash per second
    network_difficulty: str  # Current network difficulty
    block_reward_btc: str  # Reward per block in BTC
    pool_fee_pct: str  # Pool fee as percentage
    electricity_cost_kwh: str  # Cost per kWh in fiat
    power_consumption_w: str  # Power draw in watts
    uptime_pct: str  # Expected uptime as percentage (0-100)


@dataclass
class MiningProfitabilityResult:
    """Result of a mining profitability simulation."""

    daily_revenue_btc: str
    daily_electricity_cost: str
    daily_net_btc: str
    daily_net_fiat: str
    is_profitable: bool
    break_even_btc_price: str


class MiningOperationsAgent:
    """Mining Operations Agent (Section 04.4).

    Simulates mining profitability and reports safety telemetry.
    Does NOT access trading accounts beyond what is needed for
    profitability reporting.

    Prohibited: UNRESTRICTED_TRADING_ACCOUNT_ACCESS.
    """

    def __init__(self) -> None:
        self._simulations: dict[str, MiningProfitabilityResult] = {}

    def simulate_mining(
        self,
        ctx: AgentContext,
        inputs: MiningSimulationInput,
        btc_price: str,
    ) -> AgentResult:
        """Simulate mining profitability.

        Per AD-015: mining simulation with hash rate, difficulty, rewards,
        pool fees, electricity costs, and net profitability.
        Per AD-023: deterministic simulation.
        """
        ctx.check_permission(AgentPermission.SIMULATE_MINING)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        hash_rate = Decimal(inputs.hash_rate_th)
        difficulty = Decimal(inputs.network_difficulty)
        reward = Decimal(inputs.block_reward_btc)
        pool_fee = Decimal(inputs.pool_fee_pct) / Decimal(100)
        elec_cost = Decimal(inputs.electricity_cost_kwh)
        power_w = Decimal(inputs.power_consumption_w)
        uptime = Decimal(inputs.uptime_pct) / Decimal(100)

        # Daily revenue calculation (deterministic)
        # Expected blocks per day = hash_rate / difficulty * 86400 / 2^32
        # Simplified deterministic model:
        SECONDS_PER_DAY = 86400
        HASH_FACTOR = Decimal("1000000")
        blocks_per_day = (hash_rate * HASH_FACTOR / difficulty) * Decimal(SECONDS_PER_DAY)
        gross_daily_btc = blocks_per_day * reward
        pool_fee_btc = gross_daily_btc * pool_fee
        daily_revenue_btc = gross_daily_btc - pool_fee_btc

        # Daily electricity cost
        kwh_per_day = (power_w / Decimal(1000)) * Decimal(SECONDS_PER_DAY / 3600) * uptime
        daily_electricity_cost = kwh_per_day * elec_cost

        # Net profit in BTC and fiat
        daily_net_btc = daily_revenue_btc
        daily_revenue_fiat = daily_revenue_btc * Decimal(btc_price)
        daily_net_fiat = daily_revenue_fiat - daily_electricity_cost

        is_profitable = daily_net_fiat > Decimal(0)

        # Break-even BTC price
        if daily_revenue_btc > 0:
            break_even = daily_electricity_cost / daily_revenue_btc
        else:
            break_even = Decimal(0)

        result = MiningProfitabilityResult(
            daily_revenue_btc=str(daily_revenue_btc),
            daily_electricity_cost=str(daily_electricity_cost),
            daily_net_btc=str(daily_net_btc),
            daily_net_fiat=str(daily_net_fiat),
            is_profitable=is_profitable,
            break_even_btc_price=str(break_even),
        )

        trace.add_entry(
            DecisionTraceEntry(
                step="simulate_mining",
                agent_type=ctx.agent_type,
                permission=AgentPermission.SIMULATE_MINING,
                timestamp=datetime.now(UTC),
                detail=f"profitable={is_profitable}, net_fiat={result.daily_net_fiat}",
                data={
                    "hash_rate_th": inputs.hash_rate_th,
                    "btc_price": btc_price,
                    "is_simulation": "true",
                    "real_hardware_requires_approval": "true",
                },
            )
        )
        trace.complete("Mining simulation complete", authorized=True)

        sim_id = str(trace.trace_id)
        self._simulations[sim_id] = result

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={
                "daily_revenue_btc": result.daily_revenue_btc,
                "daily_electricity_cost": result.daily_electricity_cost,
                "daily_net_btc": result.daily_net_btc,
                "daily_net_fiat": result.daily_net_fiat,
                "is_profitable": str(result.is_profitable),
                "break_even_btc_price": result.break_even_btc_price,
                "is_simulation": "true",
            },
            trace_id=trace.trace_id,
        )

    def assess_profitability(
        self,
        ctx: AgentContext,
        inputs: MiningSimulationInput,
        btc_price: str,
    ) -> AgentResult:
        """Assess mining profitability (alias for simulate with summary).

        Per AD-015: profitability assessment.
        """
        ctx.check_permission(AgentPermission.ASSESS_PROFITABILITY)

        result = self.simulate_mining(ctx, inputs, btc_price)
        if not result.success:
            return result

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={
                **result.data,
                "assessment": "profitable"
                if result.data.get("is_profitable") == "true"
                else "unprofitable",
            },
            trace_id=result.trace_id,
        )

    def report_safety_telemetry(
        self,
        ctx: AgentContext,
    ) -> AgentResult:
        """Report mining safety telemetry.

        Per Section 04.4: safety telemetry and reporting.
        """
        ctx.check_permission(AgentPermission.REPORT_SAFETY_TELEMETRY)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        trace.add_entry(
            DecisionTraceEntry(
                step="report_safety_telemetry",
                agent_type=ctx.agent_type,
                permission=AgentPermission.REPORT_SAFETY_TELEMETRY,
                timestamp=datetime.now(UTC),
                detail=f"simulations={len(self._simulations)}",
                data={
                    "simulations_run": str(len(self._simulations)),
                    "real_hardware_active": "false",
                },
            )
        )
        trace.complete("Safety telemetry reported", authorized=True)

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={
                "simulations_run": str(len(self._simulations)),
                "real_hardware_active": "false",
                "real_hardware_requires_approval": "true",
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
            agent_type=AgentType.MINING_OPERATIONS,
            tenant_id=tenant_id,
            profile_id=profile_id,
            session_id=session_id,
        )
