"""Tests for Phase E10 — Commercial Monetization, Payment Tiers and Market Readiness.

Covers:
- Subscription plans: FREE_TRIAL zero price, T1/T2/T3 monthly and annual pricing,
  annual discount correctly applied, ANNUAL_DISCOUNT_RATE in [0,1).
- TenantSubscription lifecycle: start_trial, subscribe (monthly, annual), cancel,
  expire_trial, renew, tier convenience accessor.
- Feature gating: tier_has_feature for each tier, FeatureNotAvailableError raised
  when feature not available, safety features never gated (checked explicitly).
- Usage metering: record increments totals, warning at 80% threshold event emitted,
  UsageLimitExceededError raised on hard limit, unlimited tier (TIER_3) never raises,
  get_summary returns correct totals/warnings/exceeded, all_records snapshot.
- BillingEventLog: append/retrieve, events_for_tenant filter, verify_chain passes
  on intact log, verify_chain returns False on tampered event, events are immutable.
- BillingService: check_feature passes/raises, get_available_features returns set,
  subscribe replaces trial (TIER_CHANGED event), SubscriptionNotFoundError raised
  for unknown tenant.
- OnboardingService: create_record, complete_step idempotent, ONBOARDING_COMPLETED
  event emitted when required steps done, pending_steps list, is_complete transitions.
- UnitEconomicsService: snapshot MRR/ARR totals, per-tier metrics, snapshot_hash set,
  snapshot_history accumulates, trial conversions counted from events.
- MarketReadinessReport: gate results, all_gates_pass, owner_sign_off_required always
  True, live_trading_authorized always False, report_hash set.
- ApplePlatformDecision: pwa_path_requires_apple_license always False, rationale required.
- Contract invariants: SubscriptionPlan FREE_TRIAL must have zero price; negative prices
  rejected; annual_discount_rate bounds; UsageRecord quantity > 0; TierMetrics
  non-negative counts; UnitEconomicsDashboard snapshot_hash set.
- BillingEvent: event_hash set at construction, same content produces same hash.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from contracts.billing import (
    ANNUAL_DISCOUNT_RATE,
    TIER_FEATURE_MAP,
    TIER_USAGE_LIMITS,
    ApplePlatformDecision,
    BillingEvent,
    BillingEventType,
    BillingPeriod,
    DistributionChannel,
    FeatureNotAvailableError,
    GateStatus,
    MarketReadinessGate,
    MarketReadinessReport,
    MeteringDimension,
    OnboardingStep,
    SubscriptionNotFoundError,
    SubscriptionPlan,
    SubscriptionStatus,
    SubscriptionTier,
    TenantSubscription,
    TierFeature,
    TierMetrics,
    UnitEconomicsDashboard,
    UsageLimitExceededError,
    UsageRecord,
    tier_has_feature,
)
from services.billing import (
    BillingEventLog,
    BillingService,
    OnboardingService,
    UsageMeteringService,
    build_market_readiness_report,
    build_plan,
)
from services.billing.unit_economics import UnitEconomicsService

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def make_services() -> tuple[
    BillingEventLog, BillingService, UsageMeteringService, OnboardingService
]:
    log = BillingEventLog()
    billing = BillingService(event_log=log)
    metering = UsageMeteringService(event_log=log)
    onboarding = OnboardingService(event_log=log)
    return log, billing, metering, onboarding


# ──────────────────────────────────────────────────────────────────────────────
# Subscription plan pricing
# ──────────────────────────────────────────────────────────────────────────────


def test_free_trial_plan_is_zero_price() -> None:
    plan = build_plan(SubscriptionTier.FREE_TRIAL, BillingPeriod.MONTHLY)
    assert plan.total_usd == Decimal("0")
    assert plan.monthly_usd == Decimal("0")


def test_tier1_monthly_price() -> None:
    plan = build_plan(SubscriptionTier.TIER_1, BillingPeriod.MONTHLY)
    assert plan.total_usd == Decimal("200.00")
    assert plan.monthly_usd == Decimal("200.00")
    assert plan.annual_discount_rate == Decimal("0")


def test_tier2_monthly_price() -> None:
    plan = build_plan(SubscriptionTier.TIER_2, BillingPeriod.MONTHLY)
    assert plan.total_usd == Decimal("350.00")


def test_tier3_monthly_price() -> None:
    plan = build_plan(SubscriptionTier.TIER_3, BillingPeriod.MONTHLY)
    assert plan.total_usd == Decimal("500.00")


def test_tier1_annual_total_applies_discount() -> None:
    plan = build_plan(SubscriptionTier.TIER_1, BillingPeriod.ANNUAL)
    gross = Decimal("200.00") * 12  # 2400
    discount = (gross * ANNUAL_DISCOUNT_RATE).quantize(Decimal("0.01"))
    expected_total = gross - discount
    assert plan.total_usd == expected_total
    assert plan.annual_discount_rate == ANNUAL_DISCOUNT_RATE
    assert plan.period == BillingPeriod.ANNUAL
    # Annual is always cheaper than 12 × monthly
    assert plan.total_usd < gross


def test_tier3_annual_total_applies_discount() -> None:
    plan = build_plan(SubscriptionTier.TIER_3, BillingPeriod.ANNUAL)
    gross = Decimal("500.00") * 12
    discount = (gross * ANNUAL_DISCOUNT_RATE).quantize(Decimal("0.01"))
    assert plan.total_usd == gross - discount


def test_annual_discount_rate_in_valid_range() -> None:
    assert Decimal("0") <= ANNUAL_DISCOUNT_RATE < Decimal("1")


def test_subscription_plan_free_trial_nonzero_price_raises() -> None:
    with pytest.raises(ValueError, match="total_usd"):
        SubscriptionPlan(
            tier=SubscriptionTier.FREE_TRIAL,
            period=BillingPeriod.MONTHLY,
            monthly_usd=Decimal("0"),
            total_usd=Decimal("1"),
        )


def test_subscription_plan_negative_price_raises() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SubscriptionPlan(
            tier=SubscriptionTier.TIER_1,
            period=BillingPeriod.MONTHLY,
            monthly_usd=Decimal("-1"),
            total_usd=Decimal("-1"),
        )


def test_subscription_plan_invalid_discount_rate_raises() -> None:
    with pytest.raises(ValueError, match="annual_discount_rate"):
        SubscriptionPlan(
            tier=SubscriptionTier.TIER_1,
            period=BillingPeriod.ANNUAL,
            monthly_usd=Decimal("100"),
            total_usd=Decimal("1200"),
            annual_discount_rate=Decimal("1.5"),
        )


# ──────────────────────────────────────────────────────────────────────────────
# TenantSubscription lifecycle via BillingService
# ──────────────────────────────────────────────────────────────────────────────


def test_start_trial_creates_trialing_subscription() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    sub = billing.start_trial(tenant_id)
    assert sub.tier == SubscriptionTier.FREE_TRIAL
    assert sub.status == SubscriptionStatus.TRIALING
    assert sub.trial_ends_at is not None


def test_start_trial_emits_trial_started_event() -> None:
    log, billing, _, _ = make_services()
    tenant_id = uuid4()
    sub = billing.start_trial(tenant_id)
    events = log.events_for_tenant(tenant_id)
    assert any(e.event_type == BillingEventType.TRIAL_STARTED for e in events)
    assert events[0].subscription_id == sub.id


def test_subscribe_monthly_creates_active_subscription() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    assert sub.tier == SubscriptionTier.TIER_1
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.plan.total_usd == Decimal("200.00")


def test_subscribe_annual_creates_active_subscription() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_2, period=BillingPeriod.ANNUAL
    )
    assert sub.tier == SubscriptionTier.TIER_2
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.plan.period == BillingPeriod.ANNUAL


def test_subscribe_after_trial_emits_tier_changed_event() -> None:
    log, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.start_trial(tenant_id)
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    events = log.events_for_tenant(tenant_id)
    tier_changed = [e for e in events if e.event_type == BillingEventType.TIER_CHANGED]
    assert len(tier_changed) == 1
    assert tier_changed[0].payload["previous_tier"] == str(SubscriptionTier.FREE_TRIAL)


def test_subscribe_free_trial_via_subscribe_raises() -> None:
    _, billing, _, _ = make_services()
    from contracts.billing import BillingError

    with pytest.raises(BillingError):
        billing.subscribe(
            tenant_id=uuid4(),
            tier=SubscriptionTier.FREE_TRIAL,
            period=BillingPeriod.MONTHLY,
        )


def test_cancel_subscription_sets_cancelled_status() -> None:
    log, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    sub = billing.cancel(tenant_id)
    assert sub.status == SubscriptionStatus.CANCELLED
    assert sub.cancelled_at is not None


def test_cancel_emits_subscription_cancelled_event() -> None:
    log, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    billing.cancel(tenant_id)
    events = log.events_for_tenant(tenant_id)
    assert any(e.event_type == BillingEventType.SUBSCRIPTION_CANCELLED for e in events)


def test_expire_trial_sets_expired_status() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.start_trial(tenant_id)
    sub = billing.expire_trial(tenant_id)
    assert sub.status == SubscriptionStatus.EXPIRED


def test_expire_trial_emits_trial_expired_event() -> None:
    log, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.start_trial(tenant_id)
    billing.expire_trial(tenant_id)
    events = log.events_for_tenant(tenant_id)
    assert any(e.event_type == BillingEventType.TRIAL_EXPIRED for e in events)


def test_expire_trial_on_paid_subscription_raises() -> None:
    from contracts.billing import BillingError

    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    with pytest.raises(BillingError):
        billing.expire_trial(tenant_id)


def test_renew_advances_period() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    old_end = sub.current_period_end
    sub = billing.renew(tenant_id)
    assert sub.current_period_start == old_end
    assert sub.current_period_end > old_end


def test_renew_emits_subscription_renewed_event() -> None:
    log, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_2, period=BillingPeriod.MONTHLY
    )
    billing.renew(tenant_id)
    events = log.events_for_tenant(tenant_id)
    assert any(e.event_type == BillingEventType.SUBSCRIPTION_RENEWED for e in events)


def test_get_subscription_returns_none_for_unknown_tenant() -> None:
    _, billing, _, _ = make_services()
    assert billing.get_subscription(uuid4()) is None


def test_subscription_not_found_error_raised_on_check_feature() -> None:
    _, billing, _, _ = make_services()
    with pytest.raises(SubscriptionNotFoundError):
        billing.check_feature(uuid4(), TierFeature.SIMULATION_MODE)


def test_tenant_subscription_period_end_before_start_raises() -> None:
    from datetime import timedelta

    now = datetime.now(UTC)
    plan = build_plan(SubscriptionTier.TIER_1, BillingPeriod.MONTHLY)
    with pytest.raises(ValueError, match="current_period_end"):
        TenantSubscription(
            tenant_id=uuid4(),
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            started_at=now,
            current_period_start=now,
            current_period_end=now - timedelta(days=1),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Feature gating
# ──────────────────────────────────────────────────────────────────────────────


def test_free_trial_has_simulation_and_paper() -> None:
    assert tier_has_feature(SubscriptionTier.FREE_TRIAL, TierFeature.SIMULATION_MODE)
    assert tier_has_feature(SubscriptionTier.FREE_TRIAL, TierFeature.PAPER_TRADING)


def test_free_trial_does_not_have_advanced_features() -> None:
    assert not tier_has_feature(SubscriptionTier.FREE_TRIAL, TierFeature.ADVANCED_INDICATORS)
    assert not tier_has_feature(SubscriptionTier.FREE_TRIAL, TierFeature.FULL_AGENT_ACCESS)
    assert not tier_has_feature(SubscriptionTier.FREE_TRIAL, TierFeature.API_ACCESS)


def test_tier1_has_basic_features_not_advanced() -> None:
    assert tier_has_feature(SubscriptionTier.TIER_1, TierFeature.ADVANCED_INDICATORS)
    assert tier_has_feature(SubscriptionTier.TIER_1, TierFeature.BASIC_AGENT_ACCESS)
    assert not tier_has_feature(SubscriptionTier.TIER_1, TierFeature.FULL_AGENT_ACCESS)
    assert not tier_has_feature(SubscriptionTier.TIER_1, TierFeature.API_ACCESS)


def test_tier2_has_all_tier1_and_more() -> None:
    for feat in TIER_FEATURE_MAP[SubscriptionTier.TIER_1]:
        assert tier_has_feature(SubscriptionTier.TIER_2, feat)
    assert tier_has_feature(SubscriptionTier.TIER_2, TierFeature.FULL_AGENT_ACCESS)
    assert tier_has_feature(SubscriptionTier.TIER_2, TierFeature.MINING_SIMULATION)
    assert not tier_has_feature(SubscriptionTier.TIER_2, TierFeature.API_ACCESS)


def test_tier3_has_all_features_including_live_trading_eligible() -> None:
    for feat in TierFeature:
        assert tier_has_feature(SubscriptionTier.TIER_3, feat)


def test_check_feature_passes_for_available_feature() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.start_trial(tenant_id)
    billing.check_feature(tenant_id, TierFeature.SIMULATION_MODE)  # should not raise


def test_check_feature_raises_for_unavailable_feature() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.start_trial(tenant_id)
    with pytest.raises(FeatureNotAvailableError) as exc_info:
        billing.check_feature(tenant_id, TierFeature.ADVANCED_INDICATORS)
    assert exc_info.value.tier == SubscriptionTier.FREE_TRIAL
    assert exc_info.value.feature == TierFeature.ADVANCED_INDICATORS
    assert exc_info.value.tenant_id == tenant_id


def test_check_feature_tier1_cannot_access_api() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    with pytest.raises(FeatureNotAvailableError):
        billing.check_feature(tenant_id, TierFeature.API_ACCESS)


def test_check_feature_tier3_can_access_all() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_3, period=BillingPeriod.MONTHLY
    )
    for feat in TierFeature:
        billing.check_feature(tenant_id, feat)  # none should raise


def test_get_available_features_returns_correct_set() -> None:
    _, billing, _, _ = make_services()
    tenant_id = uuid4()
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_2, period=BillingPeriod.MONTHLY
    )
    features = billing.get_available_features(tenant_id)
    assert TierFeature.FULL_AGENT_ACCESS in features
    assert TierFeature.API_ACCESS not in features


# Safety invariant: live_trading_eligible requires tier3 + separate auth
def test_live_trading_eligible_only_on_tier3() -> None:
    for tier in [SubscriptionTier.FREE_TRIAL, SubscriptionTier.TIER_1, SubscriptionTier.TIER_2]:
        assert not tier_has_feature(tier, TierFeature.LIVE_TRADING_ELIGIBLE), (
            f"SAFETY VIOLATION: tier {tier} must not have LIVE_TRADING_ELIGIBLE"
        )
    assert tier_has_feature(SubscriptionTier.TIER_3, TierFeature.LIVE_TRADING_ELIGIBLE)


# ──────────────────────────────────────────────────────────────────────────────
# Usage metering
# ──────────────────────────────────────────────────────────────────────────────


def test_record_usage_increments_total() -> None:
    _, billing, metering, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    metering.record(
        tenant_id=tenant_id,
        subscription=sub,
        dimension=MeteringDimension.ORDERS,
        quantity=Decimal("5"),
    )
    metering.record(
        tenant_id=tenant_id,
        subscription=sub,
        dimension=MeteringDimension.ORDERS,
        quantity=Decimal("3"),
    )
    summary = metering.get_summary(sub)
    assert summary.totals[MeteringDimension.ORDERS] == Decimal("8")


def test_record_usage_emits_usage_recorded_event() -> None:
    log, billing, metering, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    metering.record(
        tenant_id=tenant_id,
        subscription=sub,
        dimension=MeteringDimension.LLM_TOKENS,
        quantity=Decimal("1000"),
    )
    events = log.events_for_tenant(tenant_id)
    assert any(e.event_type == BillingEventType.USAGE_RECORDED for e in events)


def test_record_usage_warning_at_80_percent() -> None:
    log, billing, metering, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    order_limit = TIER_USAGE_LIMITS[SubscriptionTier.TIER_1][MeteringDimension.ORDERS]
    assert order_limit is not None
    # Record exactly at 80% threshold
    threshold_qty = Decimal(str(int(order_limit * 0.80)))
    metering.record(
        tenant_id=tenant_id,
        subscription=sub,
        dimension=MeteringDimension.ORDERS,
        quantity=threshold_qty,
    )
    events = log.events_for_tenant(tenant_id)
    assert any(e.event_type == BillingEventType.USAGE_LIMIT_WARNING for e in events)


def test_record_usage_raises_on_hard_limit_exceeded() -> None:
    log, billing, metering, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    order_limit = TIER_USAGE_LIMITS[SubscriptionTier.TIER_1][MeteringDimension.ORDERS]
    assert order_limit is not None
    with pytest.raises(UsageLimitExceededError) as exc_info:
        metering.record(
            tenant_id=tenant_id,
            subscription=sub,
            dimension=MeteringDimension.ORDERS,
            quantity=Decimal(str(order_limit + 1)),
        )
    assert exc_info.value.dimension == MeteringDimension.ORDERS
    assert exc_info.value.limit == order_limit
    # Exceeded event must also be in the log
    events = log.events_for_tenant(tenant_id)
    assert any(e.event_type == BillingEventType.USAGE_LIMIT_EXCEEDED for e in events)


def test_tier3_unlimited_never_raises_on_large_usage() -> None:
    _, billing, metering, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_3, period=BillingPeriod.MONTHLY
    )
    # Record a huge quantity — TIER_3 has no limits
    metering.record(
        tenant_id=tenant_id,
        subscription=sub,
        dimension=MeteringDimension.ORDERS,
        quantity=Decimal("9999999"),
    )
    summary = metering.get_summary(sub)
    assert summary.totals[MeteringDimension.ORDERS] == Decimal("9999999")
    assert summary.exceeded == []
    assert summary.warnings == []


def test_usage_summary_exceeded_list() -> None:
    import contextlib

    _, billing, metering, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )
    limit = TIER_USAGE_LIMITS[SubscriptionTier.TIER_1][MeteringDimension.ORDERS]
    assert limit is not None
    with contextlib.suppress(UsageLimitExceededError):
        metering.record(
            tenant_id=tenant_id,
            subscription=sub,
            dimension=MeteringDimension.ORDERS,
            quantity=Decimal(str(limit + 1)),
        )
    summary = metering.get_summary(sub)
    assert MeteringDimension.ORDERS in summary.exceeded


def test_usage_record_quantity_zero_raises() -> None:
    with pytest.raises(ValueError, match="> 0"):
        UsageRecord(quantity=Decimal("0"))


def test_usage_record_quantity_negative_raises() -> None:
    with pytest.raises(ValueError, match="> 0"):
        UsageRecord(quantity=Decimal("-5"))


def test_all_records_snapshot() -> None:
    _, billing, metering, _ = make_services()
    tenant_id = uuid4()
    sub = billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_2, period=BillingPeriod.MONTHLY
    )
    for _i in range(3):
        metering.record(
            tenant_id=tenant_id,
            subscription=sub,
            dimension=MeteringDimension.COMPUTE_SEC,
            quantity=Decimal("10"),
        )
    all_rec = metering.all_records()
    assert len(all_rec) == 3


# ──────────────────────────────────────────────────────────────────────────────
# BillingEventLog — hash chain integrity
# ──────────────────────────────────────────────────────────────────────────────


def test_billing_event_log_append_and_retrieve() -> None:
    log = BillingEventLog()
    tenant_id = uuid4()
    event = BillingEvent(
        tenant_id=tenant_id,
        event_type=BillingEventType.SUBSCRIPTION_CREATED,
    )
    log.append(event)
    assert len(log.events()) == 1
    assert log.events()[0].event_hash != ""


def test_billing_event_log_events_for_tenant_filter() -> None:
    log = BillingEventLog()
    t1, t2 = uuid4(), uuid4()
    log.append(BillingEvent(tenant_id=t1, event_type=BillingEventType.TRIAL_STARTED))
    log.append(BillingEvent(tenant_id=t2, event_type=BillingEventType.SUBSCRIPTION_CREATED))
    log.append(BillingEvent(tenant_id=t1, event_type=BillingEventType.TRIAL_EXPIRED))
    assert len(log.events_for_tenant(t1)) == 2
    assert len(log.events_for_tenant(t2)) == 1


def test_billing_event_log_verify_chain_passes_on_intact_log() -> None:
    log = BillingEventLog()
    for i in range(5):
        log.append(
            BillingEvent(
                tenant_id=uuid4(),
                event_type=BillingEventType.USAGE_RECORDED,
                payload={"i": i},
            )
        )
    assert log.verify_chain() is True


def test_billing_event_log_verify_chain_fails_on_tampered_event() -> None:

    log = BillingEventLog()
    tenant_id = uuid4()
    event = BillingEvent(tenant_id=tenant_id, event_type=BillingEventType.TRIAL_STARTED)
    log.append(event)

    # Tamper with the stored event — mutate the underlying list directly
    events = log._events  # noqa: SLF001
    tampered = events[0]
    # Force-set a wrong hash (bypass frozen dataclass via object.__setattr__)
    object.__setattr__(tampered, "event_hash", "deadbeef" * 8)

    assert log.verify_chain() is False


def test_billing_event_hash_is_deterministic() -> None:
    """Same content produces same hash."""
    from uuid import UUID

    fixed_id = UUID("12345678-1234-5678-1234-567812345678")
    fixed_tenant = UUID("87654321-4321-8765-4321-876543218765")
    fixed_sub = UUID("aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb")
    fixed_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    # Build two events with identical content
    e1 = BillingEvent.__new__(BillingEvent)
    # Manually set all fields for determinism
    object.__setattr__(e1, "id", fixed_id)
    object.__setattr__(e1, "tenant_id", fixed_tenant)
    object.__setattr__(e1, "subscription_id", fixed_sub)
    object.__setattr__(e1, "event_type", BillingEventType.USAGE_RECORDED)
    object.__setattr__(e1, "occurred_at", fixed_time)
    object.__setattr__(e1, "payload", {"x": 1})
    object.__setattr__(e1, "event_hash", "")
    # Run __post_init__
    BillingEvent.__post_init__(e1)

    e2 = BillingEvent.__new__(BillingEvent)
    object.__setattr__(e2, "id", fixed_id)
    object.__setattr__(e2, "tenant_id", fixed_tenant)
    object.__setattr__(e2, "subscription_id", fixed_sub)
    object.__setattr__(e2, "event_type", BillingEventType.USAGE_RECORDED)
    object.__setattr__(e2, "occurred_at", fixed_time)
    object.__setattr__(e2, "payload", {"x": 1})
    object.__setattr__(e2, "event_hash", "")
    BillingEvent.__post_init__(e2)

    assert e1.event_hash == e2.event_hash
    assert len(e1.event_hash) == 64  # SHA-256 hex


# ──────────────────────────────────────────────────────────────────────────────
# Onboarding service
# ──────────────────────────────────────────────────────────────────────────────


def test_onboarding_create_record() -> None:
    _, _, _, onboarding = make_services()
    tenant_id = uuid4()
    record = onboarding.create_record(tenant_id)
    assert record.tenant_id == tenant_id
    assert not record.is_complete
    assert record.onboarding_complete_at is None


def test_onboarding_complete_step_idempotent() -> None:
    _, _, _, onboarding = make_services()
    tenant_id = uuid4()
    onboarding.create_record(tenant_id)
    onboarding.complete_step(tenant_id, OnboardingStep.ACCOUNT_CREATED)
    onboarding.complete_step(tenant_id, OnboardingStep.ACCOUNT_CREATED)  # idempotent
    record = onboarding.get_record(tenant_id)
    assert record is not None
    assert record.completed_steps.count(OnboardingStep.ACCOUNT_CREATED) == 1


def test_onboarding_completes_when_required_steps_done() -> None:
    log, _, _, onboarding = make_services()
    tenant_id = uuid4()
    onboarding.create_record(tenant_id)
    required = [
        OnboardingStep.ACCOUNT_CREATED,
        OnboardingStep.EMAIL_VERIFIED,
        OnboardingStep.TRIAL_ACTIVATED,
        OnboardingStep.TERMS_ACCEPTED,
    ]
    for step in required:
        onboarding.complete_step(tenant_id, step)
    record = onboarding.get_record(tenant_id)
    assert record is not None
    assert record.is_complete
    assert record.onboarding_complete_at is not None
    # ONBOARDING_COMPLETED event emitted
    events = log.events_for_tenant(tenant_id)
    assert any(e.event_type == BillingEventType.ONBOARDING_COMPLETED for e in events)


def test_onboarding_pending_steps_list() -> None:
    _, _, _, onboarding = make_services()
    tenant_id = uuid4()
    onboarding.create_record(tenant_id)
    onboarding.complete_step(tenant_id, OnboardingStep.ACCOUNT_CREATED)
    record = onboarding.get_record(tenant_id)
    assert record is not None
    pending = record.pending_steps
    assert OnboardingStep.ACCOUNT_CREATED not in pending
    assert OnboardingStep.EMAIL_VERIFIED in pending


def test_onboarding_is_not_complete_with_partial_steps() -> None:
    _, _, _, onboarding = make_services()
    tenant_id = uuid4()
    onboarding.create_record(tenant_id)
    onboarding.complete_step(tenant_id, OnboardingStep.ACCOUNT_CREATED)
    record = onboarding.get_record(tenant_id)
    assert record is not None
    assert not record.is_complete


# ──────────────────────────────────────────────────────────────────────────────
# Unit-economics dashboard
# ──────────────────────────────────────────────────────────────────────────────


def test_unit_economics_snapshot_empty() -> None:
    log, billing, _, _ = make_services()
    ue = UnitEconomicsService(billing_service=billing, event_log=log)
    snap = ue.snapshot()
    assert snap.total_tenants == 0
    assert snap.total_mrr_usd == Decimal("0")
    assert snap.snapshot_hash != ""


def test_unit_economics_snapshot_hash_is_set() -> None:
    log, billing, _, _ = make_services()
    ue = UnitEconomicsService(billing_service=billing, event_log=log)
    snap = ue.snapshot()
    assert len(snap.snapshot_hash) == 64


def test_unit_economics_snapshot_mrr_sums_active_tiers() -> None:
    log, billing, _, _ = make_services()
    ue = UnitEconomicsService(billing_service=billing, event_log=log)

    t1, t2, t3 = uuid4(), uuid4(), uuid4()
    billing.subscribe(tenant_id=t1, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY)
    billing.subscribe(tenant_id=t2, tier=SubscriptionTier.TIER_2, period=BillingPeriod.MONTHLY)
    billing.subscribe(tenant_id=t3, tier=SubscriptionTier.TIER_3, period=BillingPeriod.MONTHLY)

    snap = ue.snapshot()
    expected_mrr = Decimal("200.00") + Decimal("350.00") + Decimal("500.00")
    assert snap.total_mrr_usd == expected_mrr
    assert snap.total_arr_usd == expected_mrr * 12
    assert snap.total_tenants == 3
    assert snap.active_tenants == 3


def test_unit_economics_cancelled_tenant_excluded_from_mrr() -> None:
    log, billing, _, _ = make_services()
    ue = UnitEconomicsService(billing_service=billing, event_log=log)

    t1, t2 = uuid4(), uuid4()
    billing.subscribe(tenant_id=t1, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY)
    billing.subscribe(tenant_id=t2, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY)
    billing.cancel(t2)

    snap = ue.snapshot()
    # Only t1 contributes to MRR
    assert snap.total_mrr_usd == Decimal("200.00")
    assert snap.total_tenants == 2
    assert snap.active_tenants == 1


def test_unit_economics_trial_conversions_counted() -> None:
    log, billing, _, _ = make_services()
    ue = UnitEconomicsService(billing_service=billing, event_log=log)

    tenant_id = uuid4()
    billing.start_trial(tenant_id)
    billing.subscribe(
        tenant_id=tenant_id, tier=SubscriptionTier.TIER_1, period=BillingPeriod.MONTHLY
    )

    snap = ue.snapshot()
    # One TIER_CHANGED from FREE_TRIAL → TIER_1
    tier1_metrics = next(m for m in snap.tier_metrics if m.tier == SubscriptionTier.TIER_1)
    assert tier1_metrics.trial_conversions == 1


def test_unit_economics_snapshot_history_accumulates() -> None:
    log, billing, _, _ = make_services()
    ue = UnitEconomicsService(billing_service=billing, event_log=log)
    ue.snapshot()
    ue.snapshot()
    ue.snapshot()
    assert len(ue.snapshot_history()) == 3


def test_tier_metrics_negative_count_raises() -> None:
    with pytest.raises(ValueError, match="negative"):
        TierMetrics(
            tier=SubscriptionTier.TIER_1,
            active_subscriptions=-1,
            monthly_recurring_revenue_usd=Decimal("0"),
            annual_recurring_revenue_usd=Decimal("0"),
            trial_conversions=0,
            churned=0,
        )


def test_tier_metrics_negative_mrr_raises() -> None:
    with pytest.raises(ValueError, match="MRR"):
        TierMetrics(
            tier=SubscriptionTier.TIER_1,
            active_subscriptions=0,
            monthly_recurring_revenue_usd=Decimal("-1"),
            annual_recurring_revenue_usd=Decimal("0"),
            trial_conversions=0,
            churned=0,
        )


def test_unit_economics_dashboard_snapshot_hash_set() -> None:
    snap = UnitEconomicsDashboard(
        generated_at=datetime.now(UTC),
        total_tenants=1,
        active_tenants=1,
        tier_metrics=[],
        total_mrr_usd=Decimal("200"),
        total_arr_usd=Decimal("2400"),
        total_trial_conversions=0,
        total_churned=0,
    )
    assert snap.snapshot_hash != ""
    assert len(snap.snapshot_hash) == 64


# ──────────────────────────────────────────────────────────────────────────────
# Market-readiness report
# ──────────────────────────────────────────────────────────────────────────────


def test_market_readiness_report_live_trading_authorized_is_always_false() -> None:
    log, billing, _, onboarding = make_services()
    report = build_market_readiness_report(
        billing_service=billing,
        event_log=log,
        onboarding_service=onboarding,
        apple_decision_documented=True,
        annual_discount_confirmed=True,
        legal_sign_off_status=GateStatus.PASS,
        open_decisions_recorded=True,
    )
    assert report.live_trading_authorized is False


def test_market_readiness_report_cannot_be_created_with_live_authorized_true() -> None:
    """Invariant: live_trading_authorized is always False regardless of init attempt."""
    report = MarketReadinessReport(
        generated_at=datetime.now(UTC),
        gate_results=[],
        overall_status=GateStatus.PASS,
        residual_risks=[],
    )
    # __post_init__ forces live_trading_authorized = False
    assert report.live_trading_authorized is False


def test_market_readiness_report_owner_sign_off_always_required() -> None:
    log, billing, _, onboarding = make_services()
    report = build_market_readiness_report(
        billing_service=billing,
        event_log=log,
        onboarding_service=onboarding,
        apple_decision_documented=True,
        annual_discount_confirmed=True,
        legal_sign_off_status=GateStatus.PASS,
        open_decisions_recorded=True,
    )
    assert report.owner_sign_off_required is True


def test_market_readiness_report_hash_is_set() -> None:
    log, billing, _, onboarding = make_services()
    report = build_market_readiness_report(
        billing_service=billing,
        event_log=log,
        onboarding_service=onboarding,
        apple_decision_documented=True,
        annual_discount_confirmed=True,
        legal_sign_off_status=GateStatus.PASS,
        open_decisions_recorded=True,
    )
    assert report.report_hash != ""
    assert len(report.report_hash) == 64


def test_market_readiness_report_all_gates_pass_when_everything_confirmed() -> None:
    log, billing, _, onboarding = make_services()
    report = build_market_readiness_report(
        billing_service=billing,
        event_log=log,
        onboarding_service=onboarding,
        apple_decision_documented=True,
        annual_discount_confirmed=True,
        legal_sign_off_status=GateStatus.PASS,
        open_decisions_recorded=True,
    )
    assert report.all_gates_pass


def test_market_readiness_report_conditional_when_pending_owner() -> None:
    log, billing, _, onboarding = make_services()
    report = build_market_readiness_report(
        billing_service=billing,
        event_log=log,
        onboarding_service=onboarding,
        apple_decision_documented=False,  # PENDING_OWNER
        annual_discount_confirmed=False,  # PENDING_OWNER
        legal_sign_off_status=GateStatus.PENDING_OWNER,
        open_decisions_recorded=True,
    )
    assert report.overall_status == GateStatus.CONDITIONAL_PASS
    assert len(report.residual_risks) >= 3


def test_market_readiness_report_covers_all_gates() -> None:
    log, billing, _, onboarding = make_services()
    report = build_market_readiness_report(
        billing_service=billing,
        event_log=log,
        onboarding_service=onboarding,
        apple_decision_documented=True,
        annual_discount_confirmed=True,
        legal_sign_off_status=GateStatus.PASS,
        open_decisions_recorded=True,
    )
    gate_types = {r.gate for r in report.gate_results}
    for gate in MarketReadinessGate:
        assert gate in gate_types, f"Missing gate: {gate}"


def test_market_readiness_report_chain_tamper_causes_fail_gate() -> None:
    """If the event log chain is tampered, BILLING_EVENTS_AUDITED gate fails."""
    log, billing, _, onboarding = make_services()
    tenant_id = uuid4()
    billing.start_trial(tenant_id)
    # Tamper: corrupt the hash of the first event
    object.__setattr__(log._events[0], "event_hash", "badhash")  # noqa: SLF001

    report = build_market_readiness_report(
        billing_service=billing,
        event_log=log,
        onboarding_service=onboarding,
        apple_decision_documented=True,
        annual_discount_confirmed=True,
        legal_sign_off_status=GateStatus.PASS,
        open_decisions_recorded=True,
    )
    audit_result = next(
        r for r in report.gate_results if r.gate == MarketReadinessGate.BILLING_EVENTS_AUDITED
    )
    assert audit_result.status == GateStatus.FAIL
    assert not report.all_gates_pass


# ──────────────────────────────────────────────────────────────────────────────
# Apple platform decision
# ──────────────────────────────────────────────────────────────────────────────


def test_apple_platform_decision_pwa_path_never_requires_license() -> None:
    decision = ApplePlatformDecision(
        decided_at=datetime.now(UTC),
        tauri_macos_distribution=False,
        apple_developer_program_required=False,
        rationale="PWA delivery does not require Apple Developer Program for basic iPhone access.",
        channels=[DistributionChannel.PWA_IOS],
    )
    # Invariant: pwa_path_requires_apple_license is always False
    assert decision.pwa_path_requires_apple_license is False


def test_apple_platform_decision_empty_rationale_raises() -> None:
    with pytest.raises(ValueError, match="rationale"):
        ApplePlatformDecision(
            decided_at=datetime.now(UTC),
            tauri_macos_distribution=False,
            apple_developer_program_required=False,
            rationale="   ",
            channels=[DistributionChannel.PWA_IOS],
        )


def test_apple_platform_decision_tauri_distribution_recordable() -> None:
    decision = ApplePlatformDecision(
        decided_at=datetime.now(UTC),
        tauri_macos_distribution=True,
        apple_developer_program_required=True,
        rationale="Tauri macOS distribution via Mac App Store requires Apple Developer Program.",
        channels=[DistributionChannel.TAURI_MACOS],
    )
    assert decision.tauri_macos_distribution is True
    assert decision.apple_developer_program_required is True
    assert decision.pwa_path_requires_apple_license is False


# ──────────────────────────────────────────────────────────────────────────────
# Billing event — immutability spot-check
# ──────────────────────────────────────────────────────────────────────────────


def test_billing_event_is_frozen() -> None:
    event = BillingEvent(
        tenant_id=uuid4(),
        event_type=BillingEventType.SUBSCRIPTION_CREATED,
    )
    with pytest.raises((AttributeError, TypeError)):
        event.event_type = BillingEventType.TRIAL_EXPIRED  # type: ignore[misc]


def test_billing_event_hash_not_empty() -> None:
    event = BillingEvent(
        tenant_id=uuid4(),
        event_type=BillingEventType.PAYMENT_SUCCEEDED,
        payload={"amount_usd": "200.00"},
    )
    assert event.event_hash != ""
    assert len(event.event_hash) == 64


# ──────────────────────────────────────────────────────────────────────────────
# E10 scope: safety invariant — tier enforcement never weakens safety
# ──────────────────────────────────────────────────────────────────────────────


def test_safety_features_not_in_tier_feature_map() -> None:
    """Risk Kernel, kill plane and audit are not gated by TierFeature at all.

    This test documents the invariant: safety controls are unconditional and
    must never appear in the feature-gate table.
    """
    all_features = {f for tier_features in TIER_FEATURE_MAP.values() for f in tier_features}
    # These critical safety capabilities must not be present as a TierFeature
    # (they live in services.risk_kernel, services.autonomy etc. — not here)
    safety_names = {"risk_kernel", "kill_plane", "audit_trail", "emergency_stop"}
    for feature in all_features:
        assert str(feature).lower() not in safety_names, (
            f"SAFETY VIOLATION: {feature!r} must not be a commercial tier gate"
        )


def test_billing_service_check_feature_only_gates_commercial_features() -> None:
    """check_feature must only be called for commercial features.

    Any call for a safety capability (risk kernel, kill plane) must NOT
    go through the billing gate.  This test documents that the set of
    TierFeature values contains only commercial capabilities.
    """
    safety_strings = {"risk_kernel", "kill_plane", "audit", "emergency"}
    for feature in TierFeature:
        for safety in safety_strings:
            assert safety not in str(feature).lower(), (
                f"SAFETY VIOLATION: TierFeature.{feature} resembles a safety capability"
            )
