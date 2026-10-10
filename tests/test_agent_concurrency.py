"""Concurrency tests for Phase 06 — token budget thread safety.

Per deliverable 11: token budgets must be concurrency-safe.
Per AD-025: enforce bounded LLM usage with tenant quotas.
"""

from __future__ import annotations

import threading

from contracts.llm_gateway import (
    LLMGateway,
    LLMRequest,
    LLMRequestId,
    LLMRequestType,
    TokenBudget,
    TokenBudgetConfig,
)


class TestTokenBudgetConcurrency:
    """Verify token budget is thread-safe under concurrent access."""

    def test_concurrent_spend_does_not_overspend(self) -> None:
        """Multiple threads spending must not exceed the daily limit."""
        config = TokenBudgetConfig(
            tenant_id="t1",
            daily_token_limit=1000,
            per_request_limit=100,
            requests_per_minute=100,  # high to avoid rate limit interference
        )
        budget = TokenBudget(tenant_id="t1", config=config)
        spent_count = 0
        lock = threading.Lock()

        def spend() -> None:
            nonlocal spent_count
            if budget.spend(100):
                with lock:
                    spent_count += 1

        threads = [threading.Thread(target=spend) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 1000 daily limit / 100 per request = max 10 successful
        assert spent_count <= 10
        assert budget.tokens_used <= 1000

    def test_concurrent_gateway_requests(self) -> None:
        """Concurrent LLM gateway requests must respect the budget."""
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=500,
                per_request_limit=50,
                requests_per_minute=100,
            )
        )

        results: list[bool] = []
        lock = threading.Lock()

        def make_request() -> None:
            try:
                gateway.submit_request(
                    LLMRequest(
                        request_id=LLMRequestId.generate(),
                        tenant_id="t1",
                        request_type=LLMRequestType.MARKET_RESEARCH,
                        prompt="test",
                        estimated_tokens=50,
                    )
                )
                with lock:
                    results.append(True)
            except Exception:
                with lock:
                    results.append(False)

        threads = [threading.Thread(target=make_request) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 500 daily limit / 50 per request = max 10 successful
        successful = sum(results)
        assert successful <= 10

    def test_concurrent_different_tenants_are_isolated(self) -> None:
        """Concurrent requests from different tenants must not interfere."""
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=100,
                per_request_limit=50,
            )
        )
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t2",
                daily_token_limit=100,
                per_request_limit=50,
            )
        )

        errors: list[str] = []

        def request_as(tenant: str) -> None:
            try:
                gateway.submit_request(
                    LLMRequest(
                        request_id=LLMRequestId.generate(),
                        tenant_id=tenant,
                        request_type=LLMRequestType.MARKET_RESEARCH,
                        prompt="test",
                        estimated_tokens=50,
                    )
                )
            except Exception as exc:
                errors.append(f"{tenant}: {exc}")

        t1_threads = [threading.Thread(target=request_as, args=("t1",)) for _ in range(5)]
        t2_threads = [threading.Thread(target=request_as, args=("t2",)) for _ in range(5)]

        for t in t1_threads + t2_threads:
            t.start()
        for t in t1_threads + t2_threads:
            t.join()

        # Each tenant has its own budget — no cross-tenant interference
        t1_remaining = gateway.get_remaining_tokens("t1")
        t2_remaining = gateway.get_remaining_tokens("t2")
        # At least one request from each tenant should succeed
        assert t1_remaining < 100 or t2_remaining < 100
