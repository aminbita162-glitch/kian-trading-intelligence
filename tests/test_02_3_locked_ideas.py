"""Tests for Post-E10 residual task 02.3 — 10 approved locked ideas.

Per DIRECTIV.txt V1.3 Section 01.8 — all 10 ideas confirmed by the owner
for implementation as additive, non-breaking enhancements.

Verifies that each idea:
- Is implemented with contracts and a service.
- Preserves all existing invariants and safety controls.
- Has tests and evidence.
- Does NOT authorize live trading (Section 00.3).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from contracts.locked_ideas import (
    APPROVED_LOCKED_IDEAS,
    DEFAULT_CAPABILITY_TTL_SECONDS,
    LOCKED_IDEAS_LIVE_TRADING_AUTHORIZED,
    CapabilityCredential,
    CapabilityCredentialId,
    CapabilityScope,
    ChaosDrillReport,
    ChaosScenarioId,
    ChaosScenarioResult,
    ChaosScenarioType,
    DecisionType,
    DeltaEntry,
    DigestScope,
    DualControlAction,
    EventEnvelope,
    EventEnvelopeId,
    EventInvocationType,
    FeatureStoreEntry,
    FeatureStoreEntryId,
    InvocationResult,
    MeteringDimension,
    MeteringRecord,
    MeteringRecordId,
    ShadowLiveMode,
    ShadowLiveResult,
    TenantLifecycleAction,
    TenantLifecycleRequest,
    TenantLifecycleRequestId,
    TokenBudgetGovernorConfig,
    UncertaintyDossier,
    WebAuthnAssertion,
    WebAuthnCredentialType,
    compute_capability_secret_hash,
)
from services.locked_ideas import (
    CapabilityCredentialService,
    ContinuousChaosService,
    DecisionReplayService,
    DualControlService,
    DualLLMQuarantineService,
    EventInvocationService,
    FeatureStoreService,
    SchemaBusService,
    ShadowLiveService,
    StructuredDigestService,
    TenantEconomicsService,
    TenantLifecycleService,
    TokenBudgetGovernor,
    verify_safety_invariants,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Meta — 10 ideas exist and live trading is not authorized
# ═══════════════════════════════════════════════════════════════════════════════


def test_ten_approved_locked_ideas_listed() -> None:
    assert len(APPROVED_LOCKED_IDEAS) == 10


def test_live_trading_authorized_is_false() -> None:
    assert LOCKED_IDEAS_LIVE_TRADING_AUTHORIZED is False


def test_safety_invariants_verified() -> None:
    invariants = verify_safety_invariants()
    for name, value in invariants.items():
        assert value is True, f"Safety invariant failed: {name}"


def test_approved_locked_ideas_match_directive() -> None:
    expected = (
        "LLM metering + Token Budget Governor",
        "Structured digest + delta context",
        "Short-lived capability credentials + Dual-LLM quarantine",
        "Event-driven invocation",
        "Decision Replay + uncertainty dossier",
        "Dual Control (WebAuthn)",
        "Shadow-Live + point-in-time Feature Store",
        "Schema-First Bus + Eval-Driven Development",
        "Live Unit Economics + per-tenant kill/restart",
        "Continuous chaos for exchange scenarios + operator cockpit",
    )
    assert tuple(APPROVED_LOCKED_IDEAS) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 1 — LLM metering + Token Budget Governor
# ═══════════════════════════════════════════════════════════════════════════════


def test_token_budget_governor_consume() -> None:
    gov = TokenBudgetGovernor(
        TokenBudgetGovernorConfig(global_daily_token_limit=1000, per_tenant_token_limit=1000)
    )
    record = gov.consume("tenant-1", 100)
    assert record.amount == 100
    assert record.tenant_id == "tenant-1"
    assert record.dimension == MeteringDimension.LLM_TOKENS


def test_token_budget_governor_per_tenant_limit() -> None:
    config = TokenBudgetGovernorConfig(
        global_daily_token_limit=10000,
        per_tenant_token_limit=500,
        burst_allowance=0,
    )
    gov = TokenBudgetGovernor(config)
    gov.consume("tenant-1", 500)
    with pytest.raises(ValueError, match="budget exceeded"):
        gov.consume("tenant-1", 100)


def test_token_budget_governor_global_limit() -> None:
    config = TokenBudgetGovernorConfig(
        global_daily_token_limit=100,
        per_tenant_token_limit=100,
    )
    gov = TokenBudgetGovernor(config)
    gov.consume("tenant-1", 50)
    with pytest.raises(ValueError, match="Global token budget"):
        gov.consume("tenant-2", 100)


def test_token_budget_governor_can_consume() -> None:
    gov = TokenBudgetGovernor(
        TokenBudgetGovernorConfig(global_daily_token_limit=1000, per_tenant_token_limit=1000)
    )
    assert gov.can_consume("tenant-1", 100) is True
    gov.consume("tenant-1", 900)
    assert gov.can_consume("tenant-1", 200) is False
    assert gov.can_consume("tenant-1", 100) is True


def test_token_budget_governor_usage_tracking() -> None:
    gov = TokenBudgetGovernor(
        TokenBudgetGovernorConfig(global_daily_token_limit=1000, per_tenant_token_limit=1000)
    )
    gov.consume("tenant-1", 100)
    gov.consume("tenant-1", 50)
    assert gov.get_tenant_usage("tenant-1") == 150
    assert gov.get_global_usage() == 150


def test_token_budget_governor_config_validation() -> None:
    with pytest.raises(ValueError, match="per_tenant_token_limit"):
        TokenBudgetGovernorConfig(
            global_daily_token_limit=100,
            per_tenant_token_limit=200,
        )


def test_metering_record_validation() -> None:
    with pytest.raises(ValueError, match="amount must be non-negative"):
        MeteringRecord(
            record_id=MeteringRecordId.generate(),
            tenant_id="t1",
            dimension=MeteringDimension.LLM_TOKENS,
            amount=-1,
            timestamp=datetime.now(UTC),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 2 — Structured digest + delta context
# ═══════════════════════════════════════════════════════════════════════════════


def test_structured_digest_first_snapshot_no_deltas() -> None:
    service = StructuredDigestService()
    digest = service.produce_digest(
        DigestScope.TENANT,
        "tenant-1",
        {"exposure": "1000", "orders": "5"},
    )
    # First snapshot: all fields are "add" deltas from empty state
    assert len(digest.deltas) == 2
    assert all(d.change_type == "add" for d in digest.deltas)
    assert digest.previous_hash == ""
    assert digest.digest_hash != ""


def test_structured_digest_delta_detection() -> None:
    service = StructuredDigestService()
    service.produce_digest(
        DigestScope.TENANT,
        "tenant-1",
        {"exposure": "1000", "orders": "5"},
    )
    digest2 = service.produce_digest(
        DigestScope.TENANT,
        "tenant-1",
        {"exposure": "2000", "orders": "5", "new_field": "yes"},
    )
    assert len(digest2.deltas) == 2
    change_types = {d.change_type for d in digest2.deltas}
    assert change_types == {"update", "add"}
    assert digest2.previous_hash != ""


def test_structured_digest_hash_chain() -> None:
    service = StructuredDigestService()
    d1 = service.produce_digest(DigestScope.TENANT, "t1", {"a": "1"})
    d2 = service.produce_digest(DigestScope.TENANT, "t1", {"a": "2"})
    assert d2.previous_hash == d1.digest_hash
    assert d2.digest_hash != d1.digest_hash


def test_structured_digest_no_changes_no_deltas() -> None:
    service = StructuredDigestService()
    service.produce_digest(DigestScope.TENANT, "t1", {"a": "1"})
    d2 = service.produce_digest(DigestScope.TENANT, "t1", {"a": "1"})
    assert len(d2.deltas) == 0
    assert d2.previous_hash != ""


def test_delta_entry_validation() -> None:
    with pytest.raises(ValueError, match="change_type"):
        DeltaEntry(
            field_path="x",
            old_value="1",
            new_value="2",
            change_type="invalid",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 3 — Short-lived capability credentials + Dual-LLM quarantine
# ═══════════════════════════════════════════════════════════════════════════════


def test_capability_credential_issue_and_validate() -> None:
    service = CapabilityCredentialService()
    cred = service.issue_credential(
        "tenant-1",
        CapabilityScope.MARKET_DATA_READ,
        "my-secret",
    )
    assert cred.tenant_id == "tenant-1"
    assert cred.scope == CapabilityScope.MARKET_DATA_READ
    assert service.validate_credential(str(cred.credential_id), "my-secret") is True


def test_capability_credential_wrong_secret() -> None:
    service = CapabilityCredentialService()
    cred = service.issue_credential("t1", CapabilityScope.RISK_SUMMARIZE, "secret")
    assert service.validate_credential(str(cred.credential_id), "wrong") is False


def test_capability_credential_expired() -> None:
    now = datetime.now(UTC)
    cred = CapabilityCredential(
        credential_id=CapabilityCredentialId.generate(),
        tenant_id="t1",
        scope=CapabilityScope.MARKET_DATA_READ,
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        secret_hash=compute_capability_secret_hash("test"),
    )
    assert cred.is_expired is True


def test_capability_credential_ttl() -> None:
    now = datetime.now(UTC)
    cred = CapabilityCredential(
        credential_id=CapabilityCredentialId.generate(),
        tenant_id="t1",
        scope=CapabilityScope.MARKET_DATA_READ,
        issued_at=now,
        expires_at=now + timedelta(seconds=300),
        secret_hash=compute_capability_secret_hash("test"),
    )
    assert cred.ttl_seconds > 0
    assert cred.ttl_seconds <= 300


def test_capability_credential_default_ttl() -> None:
    assert DEFAULT_CAPABILITY_TTL_SECONDS == 300


def test_dual_llm_quarantine_agreement() -> None:
    service = DualLLMQuarantineService()
    assert service.quarantine("prompt", "BUY", "buy") is True


def test_dual_llm_quarantine_disagreement() -> None:
    service = DualLLMQuarantineService()
    assert service.quarantine("prompt", "BUY", "SELL") is False


def test_capability_credential_expires_before_issued_raises() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="expires_at must be after"):
        CapabilityCredential(
            credential_id=CapabilityCredentialId.generate(),
            tenant_id="t1",
            scope=CapabilityScope.MARKET_DATA_READ,
            issued_at=now,
            expires_at=now - timedelta(seconds=1),
            secret_hash="abc",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 4 — Event-driven invocation
# ═══════════════════════════════════════════════════════════════════════════════


def test_event_invocation_publish_and_handler() -> None:
    service = EventInvocationService()

    def handler(env: EventEnvelope) -> InvocationResult:
        return InvocationResult(
            envelope_id=env.envelope_id,
            handler_name="test_handler",
            success=True,
            detail="processed",
            timestamp=datetime.now(UTC),
        )

    service.register_handler(EventInvocationType.MARKET_DATA_UPDATE, "test_handler", handler)
    envelope = EventEnvelope(
        envelope_id=EventEnvelopeId.generate(),
        event_type=EventInvocationType.MARKET_DATA_UPDATE,
        tenant_id="tenant-1",
        payload={"symbol": "BTC/USDT"},
    )
    results = service.publish(envelope)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].handler_name == "test_handler"


def test_event_invocation_no_handlers() -> None:
    service = EventInvocationService()
    envelope = EventEnvelope(
        envelope_id=EventEnvelopeId.generate(),
        event_type=EventInvocationType.STRATEGY_SIGNAL,
        tenant_id="t1",
    )
    results = service.publish(envelope)
    assert len(results) == 0


def test_event_invocation_handler_error_caught() -> None:
    service = EventInvocationService()

    def bad_handler(env: EventEnvelope) -> InvocationResult:
        raise RuntimeError("boom")

    service.register_handler(EventInvocationType.ORDER_FILL, "bad", bad_handler)
    envelope = EventEnvelope(
        envelope_id=EventEnvelopeId.generate(),
        event_type=EventInvocationType.ORDER_FILL,
        tenant_id="t1",
    )
    results = service.publish(envelope)
    assert len(results) == 1
    assert results[0].success is False
    assert "boom" in results[0].detail


def test_event_envelope_hash() -> None:
    env = EventEnvelope(
        envelope_id=EventEnvelopeId.generate(),
        event_type=EventInvocationType.KILL_PLANE_TRIGGERED,
        tenant_id="platform",
        payload={"scope": "tenant", "value": "t1"},
    )
    assert env.event_hash != ""


def test_event_envelope_tenant_validation() -> None:
    with pytest.raises(ValueError, match="tenant_id must not be empty"):
        EventEnvelope(
            envelope_id=EventEnvelopeId.generate(),
            event_type=EventInvocationType.SCHEDULED_TICK,
            tenant_id="",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 5 — Decision Replay + uncertainty dossier
# ═══════════════════════════════════════════════════════════════════════════════


def test_decision_replay_record_and_replay() -> None:
    service = DecisionReplayService()
    context = {"market": "BTC/USDT", "price": "50000", "volume": "100"}
    dossier = UncertaintyDossier(
        confidence_score=0.85,
        alternatives=["hold", "sell"],
        key_assumptions=["trend continues"],
        risk_factors=["volatility spike"],
        max_regret="500",
    )
    record = service.record_decision(
        DecisionType.ORDER_SUBMISSION,
        "tenant-1",
        "agent-1",
        context,
        "buy 0.1 BTC",
        dossier,
    )
    assert record.tenant_id == "tenant-1"
    assert record.dossier.confidence_score == 0.85
    assert record.record_hash != ""

    # Replay by same context
    replayed = service.replay(context)
    assert replayed is not None
    assert replayed.context_hash == record.context_hash


def test_decision_replay_no_match() -> None:
    service = DecisionReplayService()
    result = service.replay({"nonexistent": "context"})
    assert result is None


def test_uncertainty_dossier_validation() -> None:
    with pytest.raises(ValueError, match="confidence_score"):
        UncertaintyDossier(confidence_score=1.5)


def test_decision_replay_record_hash() -> None:
    service = DecisionReplayService()
    record = service.record_decision(
        DecisionType.STRATEGY_SELECTION,
        "t1",
        "a1",
        {"key": "value"},
        "select strategy A",
        UncertaintyDossier(confidence_score=0.5),
    )
    assert record.record_hash != ""
    assert record.record_hash == record._compute_hash()


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 6 — Dual Control (WebAuthn)
# ═══════════════════════════════════════════════════════════════════════════════


def _make_assertion(approver_id: str) -> WebAuthnAssertion:
    return WebAuthnAssertion(
        credential_type=WebAuthnCredentialType.CROSS_PLATFORM,
        credential_id="cred-" + approver_id,
        authenticator_data="auth_data",
        client_data_hash="client_hash",
        signature="sig",
        approver_id=approver_id,
        timestamp=datetime.now(UTC),
    )


def test_dual_control_request_not_approved_with_one_assertion() -> None:
    service = DualControlService()
    request = service.create_request(
        DualControlAction.LIVE_TRADING_ENABLE,
        "t1",
        "operator-1",
        "Enable live trading for tenant t1",
    )
    service.add_assertion(str(request.request_id), _make_assertion("approver-1"))
    updated = service.get_request(str(request.request_id))
    assert updated is not None
    assert updated.is_approved is False
    assert len(updated.assertions) == 1


def test_dual_control_request_approved_with_two_assertions() -> None:
    service = DualControlService()
    request = service.create_request(
        DualControlAction.LARGE_ORDER_APPROVAL,
        "t1",
        "operator-1",
        "Approve large order",
    )
    service.add_assertion(str(request.request_id), _make_assertion("approver-1"))
    service.add_assertion(str(request.request_id), _make_assertion("approver-2"))
    updated = service.get_request(str(request.request_id))
    assert updated is not None
    assert updated.is_approved is True
    assert updated.approved is True


def test_dual_control_same_approver_twice_not_approved() -> None:
    service = DualControlService()
    request = service.create_request(
        DualControlAction.CREDENTIAL_ROTATION,
        "t1",
        "operator-1",
        "Rotate credentials",
    )
    service.add_assertion(str(request.request_id), _make_assertion("approver-1"))
    service.add_assertion(str(request.request_id), _make_assertion("approver-1"))
    updated = service.get_request(str(request.request_id))
    assert updated is not None
    assert updated.is_approved is False


def test_dual_control_request_not_found() -> None:
    service = DualControlService()
    with pytest.raises(ValueError, match="not found"):
        service.add_assertion("nonexistent", _make_assertion("a"))


def test_webauthn_credential_types() -> None:
    assert WebAuthnCredentialType.PLATFORM.value == "platform"
    assert WebAuthnCredentialType.CROSS_PLATFORM.value == "cross_platform"


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 7 — Shadow-Live + point-in-time Feature Store
# ═══════════════════════════════════════════════════════════════════════════════


def test_feature_store_store_and_get() -> None:
    service = FeatureStoreService()
    entry = service.store(
        "btc_1h_technicals",
        datetime.now(UTC),
        {"rsi": "45.2", "macd": "0.001"},
    )
    retrieved = service.get(str(entry.entry_id))
    assert retrieved is not None
    assert retrieved.feature_set == "btc_1h_technicals"
    assert retrieved.features["rsi"] == "45.2"
    assert retrieved.entry_hash != ""


def test_feature_store_get_by_feature_set() -> None:
    service = FeatureStoreService()
    service.store("set_a", datetime.now(UTC), {"x": "1"})
    service.store("set_a", datetime.now(UTC) + timedelta(seconds=1), {"x": "2"})
    service.store("set_b", datetime.now(UTC), {"y": "3"})
    entries = service.get_by_feature_set("set_a")
    assert len(entries) == 2
    # sorted by as_of descending
    assert entries[0].features["x"] == "2"


def test_shadow_live_run_never_executes() -> None:
    fs = FeatureStoreService()
    service = ShadowLiveService(fs)
    result = service.run_shadow(
        "strat-1",
        "btc_1h",
        datetime.now(UTC),
        {"rsi": "45"},
        "buy 0.1 BTC",
    )
    assert result.executed is False
    assert result.strategy_id == "strat-1"
    assert result.proposed_action == "buy 0.1 BTC"


def test_shadow_live_mode_is_shadow() -> None:
    fs = FeatureStoreService()
    service = ShadowLiveService(fs)
    assert service.mode == ShadowLiveMode.SHADOW


def test_shadow_live_result_executed_must_be_false() -> None:
    with pytest.raises(ValueError, match="executed must be False"):
        ShadowLiveResult(
            run_id=uuid4(),
            strategy_id="s1",
            feature_entry_id=FeatureStoreEntryId.generate(),
            proposed_action="buy",
            executed=True,
            timestamp=datetime.now(UTC),
        )


def test_feature_store_entry_hash() -> None:
    entry = FeatureStoreEntry(
        entry_id=FeatureStoreEntryId.generate(),
        feature_set="test",
        as_of=datetime.now(UTC),
        features={"a": "1"},
    )
    assert entry.entry_hash != ""
    assert entry.entry_hash == entry._compute_hash()


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 8 — Schema-First Bus + Eval-Driven Development
# ═══════════════════════════════════════════════════════════════════════════════


def test_schema_bus_register_and_publish() -> None:
    service = SchemaBusService()
    service.register_topic(
        "market_data.ticker",
        {"type": "object", "required": ["symbol"]},
        lambda msg: "symbol" in msg,
    )
    assert service.validate_message("market_data.ticker", {"symbol": "BTC/USDT"}) is True
    assert service.validate_message("market_data.ticker", {"price": "50000"}) is False
    assert service.publish("market_data.ticker", {"symbol": "BTC/USDT"}) is True
    assert service.publish("market_data.ticker", {"price": "50000"}) is False


def test_schema_bus_duplicate_topic_raises() -> None:
    service = SchemaBusService()
    service.register_topic("test.topic", {}, None)
    with pytest.raises(ValueError, match="already registered"):
        service.register_topic("test.topic", {}, None)


def test_schema_bus_eval_gate() -> None:
    service = SchemaBusService()
    service.register_topic("test.topic", {}, None)
    result = service.run_eval_gate("test.topic", 10, True)
    assert result.passed is True
    assert result.test_count == 10
    assert result.topic_name == "test.topic"


def test_schema_bus_eval_gate_topic_not_found() -> None:
    service = SchemaBusService()
    with pytest.raises(ValueError, match="not found"):
        service.run_eval_gate("nonexistent", 5, True)


def test_schema_bus_get_topics() -> None:
    service = SchemaBusService()
    service.register_topic("a.topic", {}, None)
    service.register_topic("b.topic", {}, None)
    assert sorted(service.get_topics()) == ["a.topic", "b.topic"]


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 9 — Live Unit Economics + per-tenant kill/restart
# ═══════════════════════════════════════════════════════════════════════════════


def test_tenant_lifecycle_kill_and_restart() -> None:
    service = TenantLifecycleService()
    kill_req = service.request_kill("t1", "operator", "excessive risk")
    assert kill_req.action == TenantLifecycleAction.KILL
    assert kill_req.approved is False
    assert kill_req.executed is False

    executed = service.approve_and_execute(kill_req)
    assert executed.approved is True
    assert executed.executed is True
    assert service.is_paused("t1") is True

    restart_req = service.request_restart("t1", "operator", "risk cleared")
    service.approve_and_execute(restart_req)
    assert service.is_paused("t1") is False


def test_tenant_lifecycle_request_validation() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        TenantLifecycleRequest(
            request_id=TenantLifecycleRequestId.generate(),
            tenant_id="",
            action=TenantLifecycleAction.KILL,
            issuer_id="op",
            reason="test",
            timestamp=datetime.now(UTC),
        )


def test_tenant_economics_snapshot() -> None:
    service = TenantEconomicsService()
    service.update_tenant_data("t1", "49.00", 10, 500, False)
    snap = service.snapshot("t1")
    assert snap.tenant_id == "t1"
    assert snap.mrr_usd == "49.00"
    assert snap.orders_today == 10
    assert snap.tokens_used_today == 500
    assert snap.is_paused is False
    assert snap.snapshot_hash != ""


def test_tenant_economics_snapshot_paused() -> None:
    service = TenantEconomicsService()
    service.update_tenant_data("t1", "0", 0, 0, True)
    snap = service.snapshot("t1")
    assert snap.is_paused is True


def test_tenant_economics_snapshot_hash() -> None:
    service = TenantEconomicsService()
    service.update_tenant_data("t1", "49.00", 5, 100, False)
    snap = service.snapshot("t1")
    assert snap.snapshot_hash == snap._compute_hash()


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 10 — Continuous chaos for exchange scenarios + operator cockpit
# ═══════════════════════════════════════════════════════════════════════════════


def test_continuous_chos_drill_all_passed() -> None:
    service = ContinuousChaosService()
    report = service.run_drill(
        "exchange-chaos-1",
        [
            (ChaosScenarioType.LATENCY_SPIKE, "kraken", True, 1.5, []),
            (ChaosScenarioType.ORDER_REJECTION, "kraken", True, 2.0, []),
            (ChaosScenarioType.CONNECTION_DROP, "bitvavo", True, 0.5, []),
        ],
    )
    assert report.scenarios_run == 3
    assert report.scenarios_passed == 3
    assert report.all_passed is True
    assert report.report_hash != ""


def test_continuous_chaos_drill_with_failures() -> None:
    service = ContinuousChaosService()
    report = service.run_drill(
        "exchange-chaos-2",
        [
            (ChaosScenarioType.LATENCY_SPIKE, "kraken", True, 1.0, []),
            (ChaosScenarioType.BALANCE_MISMATCH, "kraken", False, 2.0, ["balance drift detected"]),
        ],
    )
    assert report.scenarios_run == 2
    assert report.scenarios_passed == 1
    assert report.all_passed is False
    assert len(report.results[1].findings) == 1


def test_chaos_scenario_types_complete() -> None:
    expected = {
        "latency_spike",
        "partial_fill_storm",
        "order_rejection",
        "connection_drop",
        "rate_limit_hit",
        "stale_orderbook",
        "duplicate_order",
        "balance_mismatch",
    }
    actual = {t.value for t in ChaosScenarioType}
    assert actual == expected


def test_chaos_drill_report_validation() -> None:
    with pytest.raises(ValueError, match="scenarios_passed"):
        ChaosDrillReport(
            report_id=uuid4(),
            drill_name="test",
            scenarios_run=5,
            scenarios_passed=10,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )


def test_chaos_scenario_result_validation() -> None:
    with pytest.raises(ValueError, match="exchange must not be empty"):
        ChaosScenarioResult(
            result_id=uuid4(),
            scenario_id=ChaosScenarioId.generate(),
            scenario_type=ChaosScenarioType.LATENCY_SPIKE,
            exchange="",
            passed=True,
            duration_seconds=1.0,
            timestamp=datetime.now(UTC),
        )
