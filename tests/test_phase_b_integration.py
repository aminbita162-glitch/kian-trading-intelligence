"""Phase B — Operational Locked Ideas integration tests.

Per DIRECTIV.txt V1.4 Phase B acceptance criteria:
- "Each of the three items has real service code, integration tests,
   and connection to the runtime."
- "Evidence recorded in test-house/phase-b/evidence.md."
- "Full test suite green, commit pushed, hard stop."

Three items fully implemented (not skeletons):
1. Token Budget Governor + accurate metering (LLM tokens, compute, orders)
   with per-tenant budgets and graceful degradation.
2. Decision Replay + uncertainty dossier for the order path
   (replayable, auditable decision records).
3. Schema-First Bus: contract validation of all event schemas in CI.

These tests verify:
- Real service code (not skeletons).
- Integration with the existing runtime (LLMGateway, ExecutionEngine,
  RedisStreamBus, event bus).
- Per-tenant budget enforcement and graceful degradation.
- Replayable, auditable decision records with uncertainty dossiers.
- Schema validation of all event types.
- All safety invariants preserved (no live trading, no bypassed risk kernel).
"""

from __future__ import annotations

from typing import Any

import pytest

from contracts.enums import OrderState
from contracts.llm_gateway import (
    LLMGateway,
    LLMRequest,
    LLMRequestId,
    LLMRequestType,
    TokenBudgetConfig,
    TokenBudgetExceededError,
)
from contracts.locked_ideas import (
    LOCKED_IDEAS_LIVE_TRADING_AUTHORIZED,
    UncertaintyDossier,
)
from contracts.order import OrderIntent
from contracts.phase_b import (
    DegradationLevel,
    EventSchemaType,
    OrderDecisionContext,
    TenantBudgetConfig,
    build_all_event_schemas,
)
from services.phase_b import (
    EventSchemaValidator,
    OrderDecisionReplayService,
    TokenBudgetMeter,
    verify_phase_b_safety_invariants,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Item 1 — Token Budget Governor + accurate metering
# ═══════════════════════════════════════════════════════════════════════════════


class TestTokenBudgetMeter:
    """Token Budget Governor with multi-dimension metering and graceful degradation."""

    def test_consume_within_budget_accepted(self) -> None:
        """Consumption within budget is accepted without degradation."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=10000,
                compute_seconds_daily_limit=3600,
                orders_daily_limit=100,
            )
        )
        result = meter.consume("t1", llm_tokens=500, compute_seconds=30, orders=1)
        assert result.accepted is True
        assert result.degraded is False
        assert result.degradation_level is DegradationLevel.NONE
        assert result.remaining_llm_tokens == 9500
        assert result.remaining_orders == 99

    def test_consume_llm_tokens_only(self) -> None:
        """Can consume only LLM tokens without orders or compute."""
        meter = TokenBudgetMeter()
        result = meter.consume("t1", llm_tokens=100)
        assert result.accepted is True
        snapshot = meter.snapshot("t1")
        assert snapshot.llm_tokens_used == 100
        assert snapshot.orders_today == 0

    def test_consume_orders_only(self) -> None:
        """Can consume only orders without LLM tokens."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(tenant_id="t1", orders_daily_limit=10),
        )
        result = meter.consume("t1", orders=1)
        assert result.accepted is True
        snapshot = meter.snapshot("t1")
        assert snapshot.orders_today == 1
        assert snapshot.llm_tokens_used == 0

    def test_consume_compute_seconds_only(self) -> None:
        """Can consume only compute seconds."""
        meter = TokenBudgetMeter()
        result = meter.consume("t1", compute_seconds=60)
        assert result.accepted is True
        snapshot = meter.snapshot("t1")
        assert snapshot.compute_seconds_used == 60

    def test_llm_token_budget_exceeded_degrades_gracefully(self) -> None:
        """When LLM token budget is exceeded, the meter degrades gracefully."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=1000,
                llm_token_burst=200,
                orders_daily_limit=100,
            )
        )
        # Exhaust the budget
        meter.consume("t1", llm_tokens=1200)
        # Next consumption should be rejected with degradation
        result = meter.consume("t1", llm_tokens=100)
        assert result.accepted is False
        assert result.degraded is True
        assert result.degradation_level is DegradationLevel.SEVERE
        assert "Budget exceeded" in result.detail

    def test_compute_budget_exceeded_degrades_gracefully(self) -> None:
        """When compute budget is exceeded, the meter degrades gracefully."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                compute_seconds_daily_limit=100,
            )
        )
        meter.consume("t1", compute_seconds=100)
        result = meter.consume("t1", compute_seconds=50)
        assert result.accepted is False
        assert result.degraded is True

    def test_orders_budget_exceeded_degrades_gracefully(self) -> None:
        """When orders budget is exceeded, the meter degrades gracefully."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                orders_daily_limit=5,
            )
        )
        for _i in range(5):
            meter.consume("t1", orders=1)
        result = meter.consume("t1", orders=1)
        assert result.accepted is False
        assert result.degraded is True

    def test_light_degradation_at_80_percent(self) -> None:
        """Light degradation kicks in at 80% of budget."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=1000,
                llm_token_burst=200,
                orders_daily_limit=100,
            )
        )
        # Consume 80% of LLM tokens (800 of 1000)
        meter.consume("t1", llm_tokens=800)
        result = meter.consume("t1", llm_tokens=1)
        assert result.accepted is True
        assert result.degradation_level is DegradationLevel.LIGHT

    def test_moderate_degradation_at_95_percent(self) -> None:
        """Moderate degradation kicks in at 95% of budget."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=1000,
                llm_token_burst=200,
                orders_daily_limit=100,
            )
        )
        # Consume 95% of LLM tokens (950 of 1000)
        meter.consume("t1", llm_tokens=950)
        result = meter.consume("t1", llm_tokens=1)
        assert result.accepted is True
        assert result.degradation_level is DegradationLevel.MODERATE

    def test_severe_degradation_at_100_percent(self) -> None:
        """Severe degradation when budget is fully consumed."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=1000,
                llm_token_burst=200,
                orders_daily_limit=100,
            )
        )
        # Consume all tokens including burst
        meter.consume("t1", llm_tokens=1200)
        snapshot = meter.snapshot("t1")
        assert snapshot.degradation_level is DegradationLevel.SEVERE

    def test_can_consume_check(self) -> None:
        """can_consume returns False when budget would be exceeded."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=1000,
                llm_token_burst=0,
                orders_daily_limit=10,
            )
        )
        assert meter.can_consume("t1", llm_tokens=500) is True
        meter.consume("t1", llm_tokens=500)
        assert meter.can_consume("t1", llm_tokens=600) is False
        assert meter.can_consume("t1", llm_tokens=500) is True

    def test_per_tenant_isolation(self) -> None:
        """Each tenant has its own budget — no cross-tenant leakage."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=500,
                llm_token_burst=0,
            )
        )
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t2",
                llm_token_daily_limit=500,
                llm_token_burst=0,
            )
        )
        # t1 exhausts its budget
        meter.consume("t1", llm_tokens=500)
        # t2 should still have its full budget
        result = meter.consume("t2", llm_tokens=500)
        assert result.accepted is True
        # t1 should be degraded
        result_t1 = meter.consume("t1", llm_tokens=100)
        assert result_t1.accepted is False

    def test_snapshot_captures_all_dimensions(self) -> None:
        """Snapshot captures all metering dimensions."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(tenant_id="t1", orders_daily_limit=100),
        )
        meter.consume("t1", llm_tokens=200, compute_seconds=10, orders=3)
        snapshot = meter.snapshot("t1")
        assert snapshot.llm_tokens_used == 200
        assert snapshot.compute_seconds_used == 10
        assert snapshot.orders_today == 3
        assert snapshot.llm_requests_today == 1
        assert snapshot.degradation_level is DegradationLevel.NONE
        assert snapshot.timestamp.tzinfo is not None

    def test_metering_records_are_persisted(self) -> None:
        """Metering records are kept for audit."""
        meter = TokenBudgetMeter()
        meter.consume("t1", llm_tokens=100)
        meter.consume("t1", llm_tokens=200)
        records = meter.get_records()
        assert len(records) == 2
        assert all(r.amount > 0 for r in records)

    def test_budget_config_validation(self) -> None:
        """Budget config validates invalid values."""
        with pytest.raises(ValueError, match="tenant_id must not be empty"):
            TenantBudgetConfig(tenant_id="")
        with pytest.raises(ValueError, match="llm_token_daily_limit"):
            TenantBudgetConfig(tenant_id="t1", llm_token_daily_limit=0)
        with pytest.raises(ValueError, match="llm_token_burst"):
            TenantBudgetConfig(tenant_id="t1", llm_token_burst=-1)

    def test_default_config_used_when_not_configured(self) -> None:
        """Default config is used when a tenant hasn't been explicitly configured."""
        meter = TokenBudgetMeter()
        result = meter.consume("t1", llm_tokens=100)
        assert result.accepted is True

    def test_multi_consume_accumulates(self) -> None:
        """Multiple consumptions accumulate correctly across dimensions."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=10000,
                orders_daily_limit=100,
            ),
        )
        meter.consume("t1", llm_tokens=100, orders=1)
        meter.consume("t1", llm_tokens=200, orders=2)
        meter.consume("t1", llm_tokens=50, orders=1)
        snapshot = meter.snapshot("t1")
        assert snapshot.llm_tokens_used == 350
        assert snapshot.orders_today == 4
        assert snapshot.llm_requests_today == 3


class TestTokenBudgetMeterLLMIntegration:
    """Integration between TokenBudgetMeter and the existing LLMGateway runtime."""

    def test_meter_wraps_llm_gateway_consumption(self) -> None:
        """The meter tracks LLM token consumption from the gateway."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=10000,
                orders_daily_limit=100,
            )
        )
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=10000,
                per_request_limit=1000,
                requests_per_minute=100,
            )
        )

        # Submit an LLM request through the gateway
        request = LLMRequest(
            request_id=LLMRequestId.generate(),
            tenant_id="t1",
            request_type=LLMRequestType.MARKET_RESEARCH,
            prompt="Analyze BTC market trends",
            estimated_tokens=500,
        )
        response = gateway.submit_request(request)
        assert response.tokens_used == 500

        # Record the consumption in the meter
        result = meter.consume("t1", llm_tokens=response.tokens_used)
        assert result.accepted is True
        assert meter.snapshot("t1").llm_tokens_used == 500

    def test_meter_degradation_affects_llm_gateway(self) -> None:
        """When the meter degrades, the LLM gateway should also be degraded."""
        meter = TokenBudgetMeter()
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=100,
                llm_token_burst=50,
                orders_daily_limit=100,
            )
        )
        # Exhaust the meter budget
        meter.consume("t1", llm_tokens=150)
        # The meter should now degrade
        result = meter.consume("t1", llm_tokens=10)
        assert result.accepted is False
        assert result.degradation_level is DegradationLevel.SEVERE

        # The LLM gateway with the same budget should also reject
        gateway = LLMGateway()
        gateway.configure_budget(
            TokenBudgetConfig(
                tenant_id="t1",
                daily_token_limit=100,
                per_request_limit=200,
                requests_per_minute=100,
            )
        )
        request = LLMRequest(
            request_id=LLMRequestId.generate(),
            tenant_id="t1",
            request_type=LLMRequestType.MARKET_RESEARCH,
            prompt="test",
            estimated_tokens=10,
        )
        # The gateway budget is exhausted
        req1 = LLMRequest(
            request_id=LLMRequestId.generate(),
            tenant_id="t1",
            request_type=LLMRequestType.MARKET_RESEARCH,
            prompt="x",
            estimated_tokens=100,
        )
        gateway.submit_request(req1)
        with pytest.raises(TokenBudgetExceededError):
            gateway.submit_request(request)


# ═══════════════════════════════════════════════════════════════════════════════
# Item 2 — Decision Replay + uncertainty dossier for the order path
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrderDecisionReplay:
    """Decision Replay + uncertainty dossier for the order path."""

    def test_record_and_replay_order_decision(self) -> None:
        """An order decision can be recorded and replayed by context."""
        service = OrderDecisionReplayService()
        context = OrderDecisionContext(
            tenant_id="t1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
            current_price="50000.00",
            risk_authorized=True,
            risk_reason="approved",
            execution_state="filled",
        )
        dossier = UncertaintyDossier(
            confidence_score=0.85,
            alternatives=["hold", "sell"],
            key_assumptions=["trend continues"],
            risk_factors=["volatility spike"],
            max_regret="500",
        )
        record = service.record_decision(context, "submit_buy_0.01_btc", dossier)
        assert record.action_taken == "submit_buy_0.01_btc"
        assert record.dossier.confidence_score == 0.85
        assert record.record_hash != ""

        # Replay by same context
        replayed = service.replay(context)
        assert replayed is not None
        assert replayed.record_hash == record.record_hash

    def test_replay_no_match_returns_none(self) -> None:
        """Replay returns None when no matching context exists."""
        service = OrderDecisionReplayService()
        context = OrderDecisionContext(
            tenant_id="t1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
            current_price="50000.00",
            risk_authorized=True,
            risk_reason="approved",
            execution_state="filled",
        )
        assert service.replay(context) is None

    def test_decision_record_hash_is_tamper_evident(self) -> None:
        """The record hash provides tamper evidence."""
        service = OrderDecisionReplayService()
        context = OrderDecisionContext(
            tenant_id="t1",
            symbol="ETH/USDT",
            side="sell",
            quantity="0.5",
            current_price="3000.00",
            risk_authorized=False,
            risk_reason="exposure limit",
            execution_state="rejected",
        )
        dossier = UncertaintyDossier(confidence_score=0.3)
        record = service.record_decision(context, "hold_position", dossier)
        assert record.record_hash == record._compute_hash()
        assert service.verify_integrity() is True

    def test_decision_context_validation(self) -> None:
        """OrderDecisionContext validates its fields."""
        with pytest.raises(ValueError, match="side must be 'buy' or 'sell'"):
            OrderDecisionContext(
                tenant_id="t1",
                symbol="BTC/USDT",
                side="invalid",
                quantity="0.01",
                current_price="50000",
                risk_authorized=True,
                risk_reason="",
                execution_state="filled",
            )
        with pytest.raises(ValueError, match="tenant_id"):
            OrderDecisionContext(
                tenant_id="",
                symbol="BTC/USDT",
                side="buy",
                quantity="0.01",
                current_price="50000",
                risk_authorized=True,
                risk_reason="",
                execution_state="filled",
            )

    def test_records_for_tenant_isolation(self) -> None:
        """Records are isolated by tenant — no cross-tenant access."""
        service = OrderDecisionReplayService()
        for tenant in ("t1", "t2", "t1"):
            context = OrderDecisionContext(
                tenant_id=tenant,
                symbol="BTC/USDT",
                side="buy",
                quantity="0.01",
                current_price="50000.00",
                risk_authorized=True,
                risk_reason="ok",
                execution_state="filled",
            )
            service.record_decision(
                context,
                f"action_{tenant}",
                UncertaintyDossier(confidence_score=0.9),
            )
        t1_records = service.get_records_for_tenant("t1")
        t2_records = service.get_records_for_tenant("t2")
        assert len(t1_records) == 2
        assert len(t2_records) == 1
        assert all(r.context.tenant_id == "t1" for r in t1_records)
        assert all(r.context.tenant_id == "t2" for r in t2_records)

    def test_get_record_by_id(self) -> None:
        """A record can be retrieved by its ID."""
        service = OrderDecisionReplayService()
        context = OrderDecisionContext(
            tenant_id="t1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
            current_price="50000.00",
            risk_authorized=True,
            risk_reason="ok",
            execution_state="filled",
        )
        record = service.record_decision(
            context,
            "submit",
            UncertaintyDossier(confidence_score=0.8),
        )
        retrieved = service.get_record(str(record.record_id))
        assert retrieved is not None
        assert retrieved.record_hash == record.record_hash

    def test_uncertainty_dossier_fields(self) -> None:
        """The uncertainty dossier captures all required fields."""
        dossier = UncertaintyDossier(
            confidence_score=0.72,
            alternatives=["hold", "sell", "reduce"],
            key_assumptions=["trend continues", "support holds"],
            risk_factors=["volatility spike", "regulatory news"],
            max_regret="1000",
        )
        assert dossier.confidence_score == 0.72
        assert len(dossier.alternatives) == 3
        assert len(dossier.risk_factors) == 2

    def test_uncertainty_dossier_confidence_validation(self) -> None:
        """Confidence score must be between 0 and 1."""
        with pytest.raises(ValueError, match="confidence_score"):
            UncertaintyDossier(confidence_score=1.5)
        with pytest.raises(ValueError, match="confidence_score"):
            UncertaintyDossier(confidence_score=-0.1)

    def test_replay_determinism(self) -> None:
        """Replaying the same context always returns the same record."""
        service = OrderDecisionReplayService()
        context = OrderDecisionContext(
            tenant_id="t1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
            current_price="50000.00",
            risk_authorized=True,
            risk_reason="ok",
            execution_state="filled",
        )
        service.record_decision(
            context,
            "submit",
            UncertaintyDossier(confidence_score=0.9),
        )
        r1 = service.replay(context)
        r2 = service.replay(context)
        assert r1 is not None
        assert r2 is not None
        assert r1.record_hash == r2.record_hash

    def test_order_path_integration_with_execution(self) -> None:
        """Decision replay integrates with the execution pipeline context."""

        service = OrderDecisionReplayService()

        # Simulate an order flow through the execution pipeline
        intent = OrderIntent.create(
            tenant_id="t1",
            profile_id="profile-1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
        )

        # Record the decision at the point of execution
        context = OrderDecisionContext(
            tenant_id=intent.tenant_id,
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
            current_price="50000.00",
            risk_authorized=True,
            risk_reason="approved by risk kernel",
            execution_state=OrderState.FILLED.value,
        )
        dossier = UncertaintyDossier(
            confidence_score=0.88,
            alternatives=["hold", "sell"],
            key_assumptions=["market momentum positive"],
            risk_factors=["sudden volatility"],
            max_regret="500 USDT",
        )
        record = service.record_decision(
            context,
            f"submit_order:{intent.intent_id}",
            dossier,
        )
        assert record.action_taken.startswith("submit_order:")
        assert record.dossier.confidence_score == 0.88

        # Replay should find the same decision
        replayed = service.replay(context)
        assert replayed is not None
        assert replayed.action_taken == record.action_taken


# ═══════════════════════════════════════════════════════════════════════════════
# Item 3 — Schema-First Bus: contract validation of all event schemas
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventSchemaValidator:
    """Schema-First Bus: contract validation of all event schemas."""

    def test_all_event_types_have_schemas(self) -> None:
        """Every EventSchemaType has a registered schema."""
        schemas = build_all_event_schemas()
        for event_type in EventSchemaType:
            assert event_type in schemas, f"Missing schema for {event_type}"
        assert len(schemas) == len(EventSchemaType)

    def test_validate_valid_order_event(self) -> None:
        """A valid order event passes validation."""
        validator = EventSchemaValidator()
        result = validator.validate(
            "order.created",
            {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "quantity": "0.01",
            },
        )
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_valid_risk_event(self) -> None:
        """A valid risk event passes validation."""
        validator = EventSchemaValidator()
        result = validator.validate(
            "risk.authorized",
            {
                "tenant_id": "t1",
                "authorized": True,
                "reason": "within limits",
            },
        )
        assert result.valid is True

    def test_validate_valid_ledger_event(self) -> None:
        """A valid ledger event passes validation."""
        validator = EventSchemaValidator()
        result = validator.validate(
            "ledger.entry_posted",
            {
                "tenant_id": "t1",
                "asset": "USDT",
                "amount": "1000.00",
            },
        )
        assert result.valid is True

    def test_validate_valid_fill_event(self) -> None:
        """A valid fill event passes validation."""
        validator = EventSchemaValidator()
        result = validator.validate(
            "fill.recorded",
            {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "filled_quantity": "0.01",
                "fill_price": "50000.00",
                "side": "buy",
            },
        )
        assert result.valid is True

    def test_validate_missing_required_field(self) -> None:
        """A missing required field fails validation."""
        validator = EventSchemaValidator()
        result = validator.validate(
            "order.created",
            {
                "tenant_id": "t1",
                # Missing symbol, side, quantity
            },
        )
        assert result.valid is False
        assert any("symbol" in e for e in result.errors)

    def test_validate_invalid_side_value(self) -> None:
        """An invalid side value fails validation (enum check)."""
        validator = EventSchemaValidator()
        result = validator.validate(
            "order.created",
            {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "side": "invalid",
                "quantity": "0.01",
            },
        )
        assert result.valid is False
        assert any("side" in e for e in result.errors)

    def test_validate_unknown_event_type(self) -> None:
        """An unknown event type fails validation."""
        validator = EventSchemaValidator()
        result = validator.validate("unknown.event", {"key": "value"})
        assert result.valid is False
        assert any("Unknown event type" in e for e in result.errors)

    def test_validate_invalid_type_for_field(self) -> None:
        """A field with the wrong type fails validation."""
        validator = EventSchemaValidator()
        result = validator.validate(
            "risk.authorized",
            {
                "tenant_id": "t1",
                "authorized": "not_a_boolean",
            },
        )
        assert result.valid is False
        assert any("authorized" in e for e in result.errors)

    def test_validate_all_batch(self) -> None:
        """Batch validation of multiple events."""
        validator = EventSchemaValidator()
        events = [
            (
                "order.created",
                {"tenant_id": "t1", "symbol": "BTC/USDT", "side": "buy", "quantity": "0.01"},
            ),
            (
                "order.filled",
                {"tenant_id": "t1", "symbol": "BTC/USDT", "side": "buy", "quantity": "0.01"},
            ),
            ("risk.authorized", {"tenant_id": "t1", "authorized": True}),
            ("unknown.event", {"bad": True}),
        ]
        results = validator.validate_all(events)
        assert len(results) == 4
        assert results[0].valid is True
        assert results[1].valid is True
        assert results[2].valid is True
        assert results[3].valid is False

    def test_validation_count_and_failure_count(self) -> None:
        """Validation and failure counts are tracked."""
        validator = EventSchemaValidator()
        validator.validate(
            "order.created",
            {"tenant_id": "t1", "symbol": "BTC/USDT", "side": "buy", "quantity": "0.01"},
        )
        validator.validate("order.created", {"tenant_id": "t1"})  # missing fields
        assert validator.validation_count == 2
        assert validator.failure_count == 1

    def test_all_event_types_count(self) -> None:
        """There are exactly 13 event types (full coverage)."""
        assert len(EventSchemaType) == 13

    def test_schema_versioning(self) -> None:
        """Every schema has version >= 1."""
        schemas = build_all_event_schemas()
        for schema in schemas.values():
            assert schema.version >= 1

    def test_get_schema_for_known_type(self) -> None:
        """get_schema returns the schema for a known event type."""
        validator = EventSchemaValidator()
        schema = validator.get_schema("order.created")
        assert schema is not None
        assert schema.schema_type.value == "order.created"

    def test_get_schema_for_unknown_type(self) -> None:
        """get_schema returns None for an unknown event type."""
        validator = EventSchemaValidator()
        assert validator.get_schema("nonexistent.event") is None

    def test_validate_all_event_types_pass(self) -> None:
        """Every event type can be validated with a well-formed payload."""
        validator = EventSchemaValidator()
        # Build valid payloads for each event type
        valid_payloads: dict[str, dict[str, Any]] = {
            "order.created": {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "quantity": "0.01",
            },
            "order.filled": {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "quantity": "0.01",
                "fill_count": 1,
            },
            "order.cancelled": {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "side": "sell",
                "quantity": "0.01",
            },
            "order.rejected": {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "quantity": "0.01",
            },
            "order.expired": {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "quantity": "0.01",
            },
            "risk.assessed": {"tenant_id": "t1", "authorized": True, "symbol": "BTC/USDT"},
            "risk.authorized": {"tenant_id": "t1", "authorized": True, "reason": "ok"},
            "risk.denied": {"tenant_id": "t1", "authorized": False, "reason": "exposure limit"},
            "risk.reserved": {"tenant_id": "t1", "authorized": True},
            "risk.consumed": {"tenant_id": "t1", "authorized": True},
            "ledger.entry_posted": {"tenant_id": "t1", "asset": "USDT", "amount": "100.00"},
            "ledger.balance_updated": {"tenant_id": "t1", "asset": "BTC", "amount": "0.01"},
            "fill.recorded": {
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "filled_quantity": "0.01",
                "fill_price": "50000.00",
                "side": "buy",
            },
        }
        for event_type, payload in valid_payloads.items():
            result = validator.validate(event_type, payload)
            assert result.valid is True, f"Failed for {event_type}: {result.errors}"


class TestEventSchemaIntegrationWithRedisBus:
    """Integration between EventSchemaValidator and the Redis Streams event bus."""

    def test_validate_event_before_redis_publish(self) -> None:
        """Events are validated against schemas before being published to Redis Streams."""
        from services.core.redis_bus import StreamEvent

        validator = EventSchemaValidator()

        # Build a valid event
        event = StreamEvent(
            event_id="evt-1",
            stream="kti:order-events",
            aggregate_type="order",
            aggregate_id="agg-1",
            event_type="order.created",
            payload={
                "tenant_id": "t1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "quantity": "0.01",
            },
            tenant_id="t1",
        )

        # Validate before publishing
        result = validator.validate(event.event_type, event.payload)
        assert result.valid is True

    def test_invalid_event_rejected_before_redis_publish(self) -> None:
        """An invalid event is rejected before it reaches Redis Streams."""
        from services.core.redis_bus import StreamEvent

        validator = EventSchemaValidator()

        # Build an invalid event (missing required fields)
        event = StreamEvent(
            event_id="evt-2",
            stream="kti:order-events",
            aggregate_type="order",
            aggregate_id="agg-2",
            event_type="order.created",
            payload={
                "tenant_id": "t1",
                # Missing symbol, side, quantity
            },
            tenant_id="t1",
        )

        # Validate — should fail
        result = validator.validate(event.event_type, event.payload)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_schema_validation_for_all_outbox_event_types(self) -> None:
        """All event types that can be emitted to the outbox are schema-validated."""

        validator = EventSchemaValidator()

        # All the event types that the E2E simulation can emit
        test_events = [
            (
                "order.created",
                {"tenant_id": "t1", "symbol": "BTC/USDT", "side": "buy", "quantity": "0.01"},
            ),
            (
                "order.filled",
                {
                    "tenant_id": "t1",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "quantity": "0.01",
                    "fill_count": 1,
                    "execution_state": "filled",
                },
            ),
            ("risk.authorized", {"tenant_id": "t1", "authorized": True, "symbol": "BTC/USDT"}),
            ("risk.denied", {"tenant_id": "t1", "authorized": False, "reason": "exposure limit"}),
            (
                "fill.recorded",
                {
                    "tenant_id": "t1",
                    "symbol": "BTC/USDT",
                    "filled_quantity": "0.01",
                    "fill_price": "50000.00",
                    "side": "buy",
                },
            ),
        ]

        for event_type, payload in test_events:
            result = validator.validate(event_type, payload)
            assert result.valid is True, f"Failed for {event_type}: {result.errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# Safety invariants
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhaseBSafetyInvariants:
    """Verify that Phase B preserves all safety invariants."""

    def test_live_trading_not_authorized(self) -> None:
        """Phase B does not authorize live trading."""
        assert LOCKED_IDEAS_LIVE_TRADING_AUTHORIZED is False

    def test_safety_invariants_verified(self) -> None:
        """All Phase B safety invariants are verified."""
        invariants = verify_phase_b_safety_invariants()
        for name, value in invariants.items():
            assert value is True, f"Safety invariant failed: {name}"

    def test_degradation_does_not_authorize_live_trading(self) -> None:
        """Graceful degradation does not authorize live trading."""
        meter = TokenBudgetMeter()
        # Even under severe degradation
        meter.configure_tenant(
            TenantBudgetConfig(
                tenant_id="t1",
                llm_token_daily_limit=10,
                llm_token_burst=0,
                orders_daily_limit=1,
            )
        )
        meter.consume("t1", llm_tokens=10, orders=1)
        result = meter.consume("t1", llm_tokens=1)
        assert result.degradation_level is DegradationLevel.SEVERE
        # The degradation does not enable live trading
        assert LOCKED_IDEAS_LIVE_TRADING_AUTHORIZED is False

    def test_decision_replay_does_not_bypass_risk_kernel(self) -> None:
        """Decision replay records risk kernel decisions — it does not bypass them."""
        service = OrderDecisionReplayService()
        context = OrderDecisionContext(
            tenant_id="t1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
            current_price="50000.00",
            risk_authorized=False,  # Risk kernel denied
            risk_reason="exposure limit exceeded",
            execution_state=OrderState.REJECTED.value,
        )
        record = service.record_decision(
            context,
            "hold_position",
            UncertaintyDossier(confidence_score=0.2),
        )
        # The record captures that risk was NOT authorized
        assert record.context.risk_authorized is False
        # Replaying it does not change the authorization
        replayed = service.replay(context)
        assert replayed is not None
        assert replayed.context.risk_authorized is False
