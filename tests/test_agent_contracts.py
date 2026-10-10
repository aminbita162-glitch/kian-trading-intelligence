"""Tests for agent contracts — Phase 06 deliverables 1, 2, 12.

Per AD-004: exactly four specialized agents plus a separate Risk Kernel.
Per AD-020: typed agent contracts with explicit permissions.
Per deliverable 2: agent permission boundaries.
Per deliverable 12: decision traceability.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from contracts.agents import (
    AGENT_PERMISSIONS,
    AGENT_PROHIBITIONS,
    ALL_AGENT_TYPES,
    AgentContext,
    AgentId,
    AgentPermission,
    AgentProhibition,
    AgentResult,
    AgentType,
    DecisionTrace,
    DecisionTraceEntry,
    DecisionTraceId,
)

# ── Deliverable 1: Four specialized agent contracts ──


class TestFourAgentTypes:
    """Verify exactly four agent types exist per AD-004."""

    def test_exactly_four_agent_types(self) -> None:
        assert len(ALL_AGENT_TYPES) == 4

    def test_agent_types_are_correct(self) -> None:
        assert AgentType.MARKET_INTELLIGENCE in ALL_AGENT_TYPES
        assert AgentType.STRATEGY_PORTFOLIO in ALL_AGENT_TYPES
        assert AgentType.EXECUTION_SUPERVISOR in ALL_AGENT_TYPES
        assert AgentType.MINING_OPERATIONS in ALL_AGENT_TYPES

    def test_risk_kernel_is_not_an_agent(self) -> None:
        """Per AD-004: the Risk Kernel is NOT an agent."""
        assert "risk_kernel" not in {at.value for at in ALL_AGENT_TYPES}
        assert "risk_safety_kernel" not in {at.value for at in ALL_AGENT_TYPES}


# ── Deliverable 2: Agent permission boundaries ──


class TestAgentPermissions:
    """Verify each agent has exactly its allowed permissions and no more."""

    def test_market_intelligence_permissions(self) -> None:
        perms = AGENT_PERMISSIONS[AgentType.MARKET_INTELLIGENCE]
        assert AgentPermission.OBSERVE_MARKET in perms
        assert AgentPermission.COMPUTE_FEATURES in perms
        assert AgentPermission.RESEARCH_SUMMARY in perms
        assert AgentPermission.SUBMIT_ORDER not in perms
        assert AgentPermission.EVALUATE_STRATEGY not in perms
        assert AgentPermission.SIMULATE_MINING not in perms

    def test_strategy_portfolio_permissions(self) -> None:
        perms = AGENT_PERMISSIONS[AgentType.STRATEGY_PORTFOLIO]
        assert AgentPermission.EVALUATE_STRATEGY in perms
        assert AgentPermission.PROPOSE_POSITION in perms
        assert AgentPermission.VERSION_TRADE_INTENT in perms
        assert AgentPermission.SUBMIT_ORDER not in perms
        assert AgentPermission.OBSERVE_MARKET not in perms

    def test_execution_supervisor_permissions(self) -> None:
        perms = AGENT_PERMISSIONS[AgentType.EXECUTION_SUPERVISOR]
        assert AgentPermission.SUBMIT_ORDER in perms
        assert AgentPermission.CANCEL_ORDER in perms
        assert AgentPermission.RECONCILE_ORDER in perms
        assert AgentPermission.EVALUATE_STRATEGY not in perms
        assert AgentPermission.SIMULATE_MINING not in perms

    def test_mining_operations_permissions(self) -> None:
        perms = AGENT_PERMISSIONS[AgentType.MINING_OPERATIONS]
        assert AgentPermission.SIMULATE_MINING in perms
        assert AgentPermission.ASSESS_PROFITABILITY in perms
        assert AgentPermission.COORDINATE_POOL in perms
        assert AgentPermission.REPORT_SAFETY_TELEMETRY in perms
        assert AgentPermission.SUBMIT_ORDER not in perms
        assert AgentPermission.OBSERVE_MARKET not in perms

    def test_no_agent_has_all_permissions(self) -> None:
        """No single agent should have all permissions — separation of duties."""
        all_perms = set(AgentPermission)
        for agent_type in ALL_AGENT_TYPES:
            agent_perms = set(AGENT_PERMISSIONS[agent_type])
            assert agent_perms != all_perms
            assert len(agent_perms) < len(all_perms)

    def test_all_permissions_assigned(self) -> None:
        """Every permission is assigned to at least one agent."""
        for perm in AgentPermission:
            assigned = any(perm in AGENT_PERMISSIONS[at] for at in ALL_AGENT_TYPES)
            assert assigned, f"Permission {perm.value} is not assigned to any agent."


class TestAgentProhibitions:
    """Verify each agent has its correct prohibitions."""

    def test_market_intelligence_prohibitions(self) -> None:
        prohibs = AGENT_PROHIBITIONS[AgentType.MARKET_INTELLIGENCE]
        assert AgentProhibition.DIRECT_TRADE_EXECUTION in prohibs

    def test_strategy_portfolio_prohibitions(self) -> None:
        prohibs = AGENT_PROHIBITIONS[AgentType.STRATEGY_PORTFOLIO]
        assert AgentProhibition.RISK_OVERRIDE in prohibs
        assert AgentProhibition.SELF_AUTHORIZED_EXECUTION in prohibs

    def test_execution_supervisor_prohibitions(self) -> None:
        prohibs = AGENT_PROHIBITIONS[AgentType.EXECUTION_SUPERVISOR]
        assert AgentProhibition.BYPASS_RISK_AUTHORIZATION in prohibs

    def test_mining_operations_prohibitions(self) -> None:
        prohibs = AGENT_PROHIBITIONS[AgentType.MINING_OPERATIONS]
        assert AgentProhibition.UNRESTRICTED_TRADING_ACCOUNT_ACCESS in prohibs

    def test_all_agents_prohibited_from_granting_permissions(self) -> None:
        for agent_type in ALL_AGENT_TYPES:
            assert AgentProhibition.GRANT_PERMISSIONS in AGENT_PROHIBITIONS[agent_type]

    def test_all_agents_prohibited_from_bypassing_token_budget(self) -> None:
        for agent_type in ALL_AGENT_TYPES:
            assert AgentProhibition.BYPASS_TOKEN_BUDGET in AGENT_PROHIBITIONS[agent_type]


class TestAgentContext:
    """Test agent context construction and permission enforcement."""

    def test_context_defaults_to_agent_permissions(self) -> None:
        ctx = AgentContext(
            agent_id=AgentId.generate(),
            agent_type=AgentType.MARKET_INTELLIGENCE,
            tenant_id="tenant-1",
            profile_id="profile-1",
        )
        assert ctx.permissions == AGENT_PERMISSIONS[AgentType.MARKET_INTELLIGENCE]

    def test_context_rejects_extra_permissions(self) -> None:
        with pytest.raises(ValueError, match="cannot have permissions"):
            AgentContext(
                agent_id=AgentId.generate(),
                agent_type=AgentType.MARKET_INTELLIGENCE,
                tenant_id="tenant-1",
                profile_id="profile-1",
                permissions=frozenset(
                    {
                        AgentPermission.OBSERVE_MARKET,
                        AgentPermission.SUBMIT_ORDER,  # Not allowed for this agent
                    }
                ),
            )

    def test_check_permission_allowed(self) -> None:
        ctx = AgentContext(
            agent_id=AgentId.generate(),
            agent_type=AgentType.MARKET_INTELLIGENCE,
            tenant_id="tenant-1",
            profile_id="profile-1",
        )
        ctx.check_permission(AgentPermission.OBSERVE_MARKET)  # should not raise

    def test_check_permission_denied(self) -> None:
        ctx = AgentContext(
            agent_id=AgentId.generate(),
            agent_type=AgentType.MARKET_INTELLIGENCE,
            tenant_id="tenant-1",
            profile_id="profile-1",
        )
        with pytest.raises(PermissionError, match="lacks permission"):
            ctx.check_permission(AgentPermission.SUBMIT_ORDER)

    def test_check_not_prohibited_passes(self) -> None:
        ctx = AgentContext(
            agent_id=AgentId.generate(),
            agent_type=AgentType.STRATEGY_PORTFOLIO,
            tenant_id="tenant-1",
            profile_id="profile-1",
        )
        # Strategy agent is NOT prohibited from DIRECT_TRADE_EXECUTION
        ctx.check_not_prohibited(AgentProhibition.DIRECT_TRADE_EXECUTION)

    def test_check_not_prohibited_raises(self) -> None:
        ctx = AgentContext(
            agent_id=AgentId.generate(),
            agent_type=AgentType.MARKET_INTELLIGENCE,
            tenant_id="tenant-1",
            profile_id="profile-1",
        )
        with pytest.raises(PermissionError, match="prohibited from"):
            ctx.check_not_prohibited(AgentProhibition.DIRECT_TRADE_EXECUTION)

    def test_context_requires_tenant_id(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            AgentContext(
                agent_id=AgentId.generate(),
                agent_type=AgentType.MARKET_INTELLIGENCE,
                tenant_id="",
                profile_id="profile-1",
            )

    def test_context_requires_profile_id(self) -> None:
        with pytest.raises(ValueError, match="profile_id"):
            AgentContext(
                agent_id=AgentId.generate(),
                agent_type=AgentType.MARKET_INTELLIGENCE,
                tenant_id="tenant-1",
                profile_id="",
            )


# ── Deliverable 12: Decision traceability ──


class TestDecisionTrace:
    """Test decision trace entries and completion."""

    def test_trace_creation(self) -> None:
        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id="tenant-1",
        )
        assert trace.entry_count == 0
        assert not trace.is_complete

    def test_trace_add_entry(self) -> None:
        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id="tenant-1",
        )
        entry = DecisionTraceEntry(
            step="test_step",
            agent_type=AgentType.MARKET_INTELLIGENCE,
            permission=AgentPermission.OBSERVE_MARKET,
            timestamp=datetime.now(UTC),
            detail="test detail",
        )
        trace.add_entry(entry)
        assert trace.entry_count == 1

    def test_trace_complete(self) -> None:
        trace = DecisionTrace(
            trace_id=DecisionTraceId.generate(),
            tenant_id="tenant-1",
        )
        trace.complete("All checks passed", authorized=True)
        assert trace.is_complete
        assert trace.final_decision == "All checks passed"
        assert trace.final_authorized

    def test_trace_entry_requires_timezone(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            DecisionTraceEntry(
                step="test",
                agent_type=AgentType.MARKET_INTELLIGENCE,
                permission=None,
                timestamp=datetime.now(),  # noqa: DTZ005 — intentionally naive
            )

    def test_trace_requires_tenant_id(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            DecisionTrace(
                trace_id=DecisionTraceId.generate(),
                tenant_id="",
            )


class TestAgentResult:
    """Test AgentResult construction."""

    def test_result_ok(self) -> None:
        result = AgentResult.ok(
            agent_type=AgentType.MARKET_INTELLIGENCE,
            data={"key": "value"},
        )
        assert result.success
        assert result.data["key"] == "value"

    def test_result_failure(self) -> None:
        result = AgentResult.failure(
            agent_type=AgentType.MARKET_INTELLIGENCE,
            error="Something went wrong",
        )
        assert not result.success
        assert result.error == "Something went wrong"

    def test_result_timestamp_is_timezone_aware(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            AgentResult(
                agent_type=AgentType.MARKET_INTELLIGENCE,
                success=True,
                timestamp=datetime.now(),  # noqa: DTZ005 — intentionally naive
            )
