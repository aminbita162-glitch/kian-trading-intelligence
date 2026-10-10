"""Agent services for Kian Trading Intelligence.

Per AD-004 (Four Agents + Independent Safety Kernel): exactly four
specialized agents plus a separate deterministic Risk & Safety Kernel.

Agents:
1. MarketIntelligenceAgent — observations, features, bounded research.
2. StrategyPortfolioAgent — evaluation, portfolio, proposals.
3. ExecutionSupervisorAgent — order lifecycle, reconciliation.
4. MiningOperationsAgent — simulation, profitability, safety telemetry.

The Risk Kernel (services.risk_kernel.kernel.RiskKernel) is NOT an agent.
"""

from services.agents.execution_supervisor import ExecutionSupervisorAgent
from services.agents.market_intelligence import MarketIntelligenceAgent
from services.agents.mining_operations import (
    MiningOperationsAgent,
    MiningSimulationInput,
)
from services.agents.orchestrator import AgentOrchestrator, OrchestratorResult
from services.agents.strategy_portfolio import StrategyPortfolioAgent

__all__ = [
    "AgentOrchestrator",
    "ExecutionSupervisorAgent",
    "MarketIntelligenceAgent",
    "MiningOperationsAgent",
    "MiningSimulationInput",
    "OrchestratorResult",
    "StrategyPortfolioAgent",
]
