"""Tests for LLM gateway and token budgets — Phase 06 deliverables 9-11.

Per AD-003: LLM usage must remain bounded and nonauthoritative.
Per AD-011: LLM outputs must NEVER be authoritative for execution.
Per AD-025: enforce bounded LLM usage, tenant quotas, and rate limits.
Per deliverable 9: validated ML interfaces.
Per deliverable 10: limited LLM gateway.
Per deliverable 11: token budgets.
"""

from __future__ import annotations

import pytest

from contracts.llm_gateway import (
    FORBIDDEN_LLM_USES,
    LLMGateway,
    LLMRequest,
    LLMRequestId,
    LLMRequestType,
    LLMResponse,
    TokenBudget,
    TokenBudgetConfig,
    TokenBudgetExceededError,
)


class TestTokenBudget:
    """Deliverable 11: token budgets — bounded LLM usage."""

    def test_budget_creation(self) -> None:
        config = TokenBudgetConfig(
            tenant_id="tenant-1",
            daily_token_limit=1000,
            per_request_limit=100,
            requests_per_minute=10,
        )
        budget = TokenBudget(tenant_id="tenant-1", config=config)
        assert budget.remaining_tokens == 1000
        assert not budget.is_exhausted

    def test_budget_spend(self) -> None:
        config = TokenBudgetConfig(
            tenant_id="t1",
            daily_token_limit=1000,
            per_request_limit=100,
        )
        budget = TokenBudget(tenant_id="t1", config=config)
        assert budget.spend(100)
        assert budget.remaining_tokens == 900

    def test_budget_exhausted(self) -> None:
        config = TokenBudgetConfig(
            tenant_id="t1",
            daily_token_limit=100,
            per_request_limit=100,
        )
        budget = TokenBudget(tenant_id="t1", config=config)
        budget.spend(100)
        assert budget.is_exhausted
        assert not budget.spend(10)

    def test_budget_per_request_limit(self) -> None:
        config = TokenBudgetConfig(
            tenant_id="t1",
            daily_token_limit=10000,
            per_request_limit=50,
        )
        budget = TokenBudget(tenant_id="t1", config=config)
        assert not budget.spend(51)  # exceeds per_request_limit

    def test_budget_rate_limit(self) -> None:
        config = TokenBudgetConfig(
            tenant_id="t1",
            daily_token_limit=10000,
            per_request_limit=100,
            requests_per_minute=2,
        )
        budget = TokenBudget(tenant_id="t1", config=config)
        assert budget.spend(10)
        assert budget.spend(10)
        assert not budget.spend(10)  # rate limited

    def test_budget_can_spend_does_not_consume(self) -> None:
        config = TokenBudgetConfig(
            tenant_id="t1",
            daily_token_limit=100,
            per_request_limit=50,
        )
        budget = TokenBudget(tenant_id="t1", config=config)
        assert budget.can_spend(50)
        assert budget.remaining_tokens == 100  # can_spend doesn't consume

    def test_config_validation(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            TokenBudgetConfig(tenant_id="")

    def test_config_daily_limit_minimum(self) -> None:
        with pytest.raises(ValueError, match="daily_token_limit"):
            TokenBudgetConfig(tenant_id="t1", daily_token_limit=0)


class TestLLMGateway:
    """Deliverable 10: limited LLM gateway — bounded and nonauthoritative."""

    def test_gateway_submit_request(self) -> None:
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=10000,
                per_request_limit=1000,
            )
        )
        request = LLMRequest(
            request_id=LLMRequestId.generate(),
            tenant_id="t1",
            request_type=LLMRequestType.MARKET_RESEARCH,
            prompt="Analyze BTC trend",
            estimated_tokens=100,
        )
        response = gateway.submit_request(request)
        assert response.tokens_used == 100
        assert not response.is_authoritative  # AD-011

    def test_gateway_response_is_nonauthoritative(self) -> None:
        """Per AD-011: LLM responses must NEVER be authoritative."""
        gateway = LLMGateway()
        gateway.configure_budget(TokenBudgetConfig(tenant_id="t1"))
        request = LLMRequest(
            request_id=LLMRequestId.generate(),
            tenant_id="t1",
            request_type=LLMRequestType.STRATEGY_ANALYSIS,
            prompt="Analyze strategy",
            estimated_tokens=50,
        )
        response = gateway.submit_request(request)
        assert not response.is_authoritative

    def test_response_rejects_authoritative(self) -> None:
        """LLMResponse must not allow is_authoritative=True."""
        with pytest.raises(ValueError, match="NOT be authoritative"):
            LLMResponse(
                request_id=LLMRequestId.generate(),
                text="test",
                is_authoritative=True,
            )

    def test_gateway_token_budget_exceeded(self) -> None:
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=50,
                per_request_limit=50,
            )
        )
        request = LLMRequest(
            request_id=LLMRequestId.generate(),
            tenant_id="t1",
            request_type=LLMRequestType.MARKET_RESEARCH,
            prompt="test",
            estimated_tokens=100,
        )
        with pytest.raises(TokenBudgetExceededError):
            gateway.submit_request(request)

    def test_gateway_rate_limit(self) -> None:
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=10000,
                per_request_limit=100,
                requests_per_minute=2,
            )
        )
        for _ in range(2):
            gateway.submit_request(
                LLMRequest(
                    request_id=LLMRequestId.generate(),
                    tenant_id="t1",
                    request_type=LLMRequestType.MARKET_RESEARCH,
                    prompt="test",
                    estimated_tokens=10,
                )
            )
        with pytest.raises(TokenBudgetExceededError):
            gateway.submit_request(
                LLMRequest(
                    request_id=LLMRequestId.generate(),
                    tenant_id="t1",
                    request_type=LLMRequestType.MARKET_RESEARCH,
                    prompt="test",
                    estimated_tokens=10,
                )
            )

    def test_gateway_get_remaining_tokens(self) -> None:
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=1000,
            )
        )
        assert gateway.get_remaining_tokens("t1") == 1000
        gateway.submit_request(
            LLMRequest(
                request_id=LLMRequestId.generate(),
                tenant_id="t1",
                request_type=LLMRequestType.MARKET_RESEARCH,
                prompt="test",
                estimated_tokens=100,
            )
        )
        assert gateway.get_remaining_tokens("t1") == 900

    def test_forbidden_uses_set_not_empty(self) -> None:
        """Per AD-011: forbidden LLM uses must be defined."""
        assert len(FORBIDDEN_LLM_USES) > 0
        assert "risk_authorization" in FORBIDDEN_LLM_USES
        assert "trade_execution" in FORBIDDEN_LLM_USES
        assert "price_authoritative" in FORBIDDEN_LLM_USES

    def test_request_types_are_research_only(self) -> None:
        """Per AD-003: only research/analysis types are allowed."""
        for rt in LLMRequestType:
            assert "research" in rt.value or "analysis" in rt.value or "summary" in rt.value

    def test_gateway_default_budget(self) -> None:
        """Gateway creates a default budget if not configured."""
        gateway = LLMGateway()
        budget = gateway.get_budget("new-tenant")
        assert budget.tenant_id == "new-tenant"
        assert budget.remaining_tokens > 0

    def test_request_requires_prompt(self) -> None:
        with pytest.raises(ValueError, match="prompt"):
            LLMRequest(
                request_id=LLMRequestId.generate(),
                tenant_id="t1",
                request_type=LLMRequestType.MARKET_RESEARCH,
                prompt="",
            )

    def test_request_requires_tenant(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            LLMRequest(
                request_id=LLMRequestId.generate(),
                tenant_id="",
                request_type=LLMRequestType.MARKET_RESEARCH,
                prompt="test",
            )
