"""Execution & Supervisor Agent for Kian Trading Intelligence.

Per Section 04.3: Execution & Supervisor Agent.
- Responsibilities: Authorized order lifecycle coordination; exchange adapter
  orchestration; execution-state monitoring; reconciliation coordination.
- Prohibited: Bypassing independent risk authorization.

Per AD-004: the Execution Agent may NOT bypass the Risk Kernel. No
exposure-increasing order may reach an exchange adapter without valid
risk authorization.
Per AD-014: deterministic execution and reconciliation.
Per AD-020: typed agent contracts with explicit permissions.

The Execution Agent wraps the existing ExecutionEngine but enforces that
every order passes through the Risk Kernel's authorization before reaching
the exchange adapter. It does NOT issue risk authorizations itself.
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
from contracts.exchange import (
    ClientOrderId,
    OrderType,
)
from contracts.order import OrderIntent
from contracts.trading import TradingSession
from services.execution.engine import ExecutionEngine


class ExecutionSupervisorAgent:
    """Execution & Supervisor Agent (Section 04.3).

    Coordinates authorized order lifecycle through the ExecutionEngine.
    Wraps the existing engine but enforces that no order bypasses the
    Risk Kernel.

    Prohibited: BYPASS_RISK_AUTHORIZATION.
    """

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine

    def submit_order(  # noqa: PLR0913, PLR0917
        self,
        ctx: AgentContext,
        intent: OrderIntent,
        current_price: str,
        session: TradingSession | None = None,
        order_type: OrderType = OrderType.MARKET,
        price: str | None = None,
    ) -> AgentResult:
        """Submit an order through the full execution pipeline.

        Per AD-004: the ExecutionEngine internally calls the Risk Kernel
        for authorization. This agent does NOT bypass that — it delegates
        to the engine which enforces the invariant.
        """
        ctx.check_permission(AgentPermission.SUBMIT_ORDER)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        trace.add_entry(
            DecisionTraceEntry(
                step="submit_order.start",
                agent_type=ctx.agent_type,
                permission=AgentPermission.SUBMIT_ORDER,
                timestamp=datetime.now(UTC),
                detail=f"symbol={intent.symbol}, side={intent.side}, qty={intent.quantity}",
                data={
                    "risk_kernel_required": "true",
                    "agent_does_not_authorize": "true",
                },
            )
        )

        try:
            result = self._engine.execute_order(
                intent,
                current_price=current_price,
                session=session,
                order_type=order_type,
                price=price,
            )
        except Exception as exc:
            trace.complete(f"Execution failed: {exc}", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error=str(exc),
                trace_id=trace.trace_id,
            )

        trace.add_entry(
            DecisionTraceEntry(
                step="submit_order.complete",
                agent_type=ctx.agent_type,
                permission=AgentPermission.SUBMIT_ORDER,
                timestamp=datetime.now(UTC),
                detail=f"state={result.state.value}",
                data={
                    "risk_authorized": "true",
                    "order_state": result.state.value,
                },
            )
        )
        trace.complete(
            f"Order submitted — state={result.state.value}",
            authorized=True,
        )

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={
                "client_order_id": str(result.client_order_id),
                "order_state": result.state.value,
                "fills": str(len(result.fills)),
                "risk_authorized": "true",
            },
            trace_id=trace.trace_id,
        )

    def cancel_order(
        self,
        ctx: AgentContext,
        client_order_id: ClientOrderId,
    ) -> AgentResult:
        """Cancel an order on the exchange.

        Per AD-014: cancellation is idempotent.
        """
        ctx.check_permission(AgentPermission.CANCEL_ORDER)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        try:
            order = self._engine.cancel_order(client_order_id)
        except Exception as exc:
            trace.complete(f"Cancel failed: {exc}", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error=str(exc),
                trace_id=trace.trace_id,
            )

        trace.add_entry(
            DecisionTraceEntry(
                step="cancel_order",
                agent_type=ctx.agent_type,
                permission=AgentPermission.CANCEL_ORDER,
                timestamp=datetime.now(UTC),
                detail=f"state={order.state.value}",
            )
        )
        trace.complete(f"Order cancelled — state={order.state.value}", authorized=True)

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={"order_state": order.state.value},
            trace_id=trace.trace_id,
        )

    def reconcile_order(
        self,
        ctx: AgentContext,
        client_order_id: ClientOrderId,
    ) -> AgentResult:
        """Reconcile an order with an unknown outcome.

        Per AD-014: unknown outcomes require reconciliation.
        Per Section 05.3: no blind retries.
        """
        ctx.check_permission(AgentPermission.RECONCILE_ORDER)

        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id=ctx.tenant_id,
        )

        try:
            order = self._engine.reconcile_order(client_order_id)
        except Exception as exc:
            trace.complete(f"Reconciliation failed: {exc}", authorized=False)
            return AgentResult.failure(
                agent_type=ctx.agent_type,
                error=str(exc),
                trace_id=trace.trace_id,
            )

        trace.add_entry(
            DecisionTraceEntry(
                step="reconcile_order",
                agent_type=ctx.agent_type,
                permission=AgentPermission.RECONCILE_ORDER,
                timestamp=datetime.now(UTC),
                detail=f"state={order.state.value}",
            )
        )
        trace.complete(
            f"Order reconciled — state={order.state.value}",
            authorized=True,
        )

        return AgentResult.ok(
            agent_type=ctx.agent_type,
            data={"order_state": order.state.value},
            trace_id=trace.trace_id,
        )

    @property
    def engine(self) -> ExecutionEngine:
        """Access the underlying execution engine."""
        return self._engine

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
            agent_type=AgentType.EXECUTION_SUPERVISOR,
            tenant_id=tenant_id,
            profile_id=profile_id,
            session_id=session_id,
        )
