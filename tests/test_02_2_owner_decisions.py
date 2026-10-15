"""Tests for Post-E10 residual task 02.2 — owner decisions from Section 01.

Verifies that the "Current (now)" choices from DIRECTIV.txt Section 01
are implemented in configuration, adapters, and documentation without
activating LIVE.

Covers:
- 01.1 Cloud Provider: Render is current, AWS is roadmap.
- 01.2 Event Bus: Redis Streams is current, AWS SQS/SNS is roadmap.
- 01.3 SLO/RPO/RTO: 99.0% / ≤15min / ≤60min is current; 99.9% / ≤1min / ≤15min is roadmap.
- 01.4 Exchange Providers: Kraken + Bitvavo are current and MiCA-licensed.
- 01.5 Legal Classification: EU/German MiCA/GDPR templates, no counsel engaged.
- 01.6 Notification Providers: SendGrid email is current; Slack + Twilio SMS are roadmap.
- 01.7 Pricing Tiers: $49/$99/$149 monthly, $39/$79/$119 annual.
- PlatformConfig aggregate: live_trading_authorized is always False.
- Safety invariant: no current exchange provider is live_authorized.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from contracts.billing import (
    ANNUAL_DISCOUNT_RATE,
    FREE_TRIAL_DAYS,
    TIER_ANNUAL_MONTHLY_USD,
    TIER_MONTHLY_USD,
    BillingPeriod,
    SubscriptionTier,
)
from contracts.platform_config import (
    CURRENT_CLOUD_PROVIDER,
    CURRENT_EVENT_BUS,
    CURRENT_EXCHANGE_PROVIDERS,
    CURRENT_LEGAL_CLASSIFICATION,
    CURRENT_NOTIFICATION_PROVIDERS,
    CURRENT_SLO_TARGETS,
    PLATFORM_CONFIG,
    ROADMAP_CLOUD_PROVIDER,
    ROADMAP_EVENT_BUS,
    ROADMAP_EXCHANGE_PROVIDERS,
    ROADMAP_NOTIFICATION_PROVIDERS,
    ROADMAP_SLO_TARGETS,
    CloudProvider,
    EventBusProvider,
    ExchangeProviderConfig,
    ExchangeProviderName,
    LegalClassificationConfig,
    LegalJurisdiction,
    NotificationChannel,
    PlatformConfig,
    get_current_exchange_provider_names,
    is_exchange_provider_current,
)
from services.billing import BillingEventLog, BillingService, build_plan

# ──────────────────────────────────────────────────────────────────────────────
# 01.1 — Cloud Provider
# ──────────────────────────────────────────────────────────────────────────────


def test_current_cloud_provider_is_render() -> None:
    assert CURRENT_CLOUD_PROVIDER == CloudProvider.RENDER


def test_roadmap_cloud_provider_is_aws() -> None:
    assert ROADMAP_CLOUD_PROVIDER == CloudProvider.AWS


# ──────────────────────────────────────────────────────────────────────────────
# 01.2 — Event Bus
# ──────────────────────────────────────────────────────────────────────────────


def test_current_event_bus_is_redis_streams() -> None:
    assert CURRENT_EVENT_BUS == EventBusProvider.REDIS_STREAMS


def test_roadmap_event_bus_is_aws_sqs_sns() -> None:
    assert ROADMAP_EVENT_BUS == EventBusProvider.AWS_SQS_SNS


# ──────────────────────────────────────────────────────────────────────────────
# 01.3 — SLO / RPO / RTO
# ──────────────────────────────────────────────────────────────────────────────


def test_current_slo_targets() -> None:
    assert CURRENT_SLO_TARGETS.availability_pct == "99.0"
    assert CURRENT_SLO_TARGETS.rpo_minutes == 15
    assert CURRENT_SLO_TARGETS.rto_minutes == 60
    assert CURRENT_SLO_TARGETS.tier == "current"


def test_roadmap_slo_targets() -> None:
    assert ROADMAP_SLO_TARGETS.availability_pct == "99.9"
    assert ROADMAP_SLO_TARGETS.rpo_minutes == 1
    assert ROADMAP_SLO_TARGETS.rto_minutes == 15
    assert ROADMAP_SLO_TARGETS.tier == "roadmap"


def test_current_slo_targets_are_less_strict_than_roadmap() -> None:
    assert Decimal(CURRENT_SLO_TARGETS.availability_pct) < Decimal(
        ROADMAP_SLO_TARGETS.availability_pct
    )
    assert CURRENT_SLO_TARGETS.rpo_minutes > ROADMAP_SLO_TARGETS.rpo_minutes
    assert CURRENT_SLO_TARGETS.rto_minutes > ROADMAP_SLO_TARGETS.rto_minutes


# ──────────────────────────────────────────────────────────────────────────────
# 01.4 — Exchange Providers
# ──────────────────────────────────────────────────────────────────────────────


def test_current_exchange_providers_are_kraken_and_bitvavo() -> None:
    names = [str(p.name) for p in CURRENT_EXCHANGE_PROVIDERS]
    assert "kraken" in names
    assert "bitvavo" in names
    assert len(CURRENT_EXCHANGE_PROVIDERS) == 2


def test_current_exchange_providers_are_mica_licensed() -> None:
    for provider in CURRENT_EXCHANGE_PROVIDERS:
        assert provider.mica_licensed, (
            f"SAFETY: {provider.name} must be MiCA-licensed for current use"
        )


def test_current_exchange_providers_are_not_live_authorized() -> None:
    for provider in CURRENT_EXCHANGE_PROVIDERS:
        assert provider.is_live_authorized is False, (
            f"SAFETY VIOLATION: {provider.name} must not be live_authorized"
        )


def test_roadmap_exchange_providers_not_in_current() -> None:
    current_names = {str(p.name) for p in CURRENT_EXCHANGE_PROVIDERS}
    for provider in ROADMAP_EXCHANGE_PROVIDERS:
        assert str(provider.name) not in current_names
        assert provider.is_current is False


def test_get_current_exchange_provider_names() -> None:
    names = get_current_exchange_provider_names()
    assert "kraken" in names
    assert "bitvavo" in names
    assert len(names) == 2


def test_is_exchange_provider_current_kraken() -> None:
    assert is_exchange_provider_current(ExchangeProviderName.KRAKEN) is True


def test_is_exchange_provider_current_bitvavo() -> None:
    assert is_exchange_provider_current(ExchangeProviderName.BITVAVO) is True


def test_is_exchange_provider_current_binance_is_false() -> None:
    assert is_exchange_provider_current(ExchangeProviderName.BINANCE) is False


def test_is_exchange_provider_current_by_string() -> None:
    assert is_exchange_provider_current("kraken") is True
    assert is_exchange_provider_current("bitvavo") is True
    assert is_exchange_provider_current("binance") is False


def test_exchange_provider_config_live_authorized_raises() -> None:
    with pytest.raises(ValueError, match="is_live_authorized"):
        ExchangeProviderConfig(
            name=ExchangeProviderName.KRAKEN,
            mica_licensed=True,
            is_current=True,
            is_live_authorized=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# 01.5 — Legal Classification
# ──────────────────────────────────────────────────────────────────────────────


def test_current_legal_classification_jurisdiction_is_eu_mica() -> None:
    assert CURRENT_LEGAL_CLASSIFICATION.jurisdiction == LegalJurisdiction.EU_MICA


def test_current_legal_classification_templates_include_mica_and_gdpr() -> None:
    assert "MiCA" in CURRENT_LEGAL_CLASSIFICATION.templates
    assert "GDPR" in CURRENT_LEGAL_CLASSIFICATION.templates


def test_current_legal_classification_counsel_not_engaged() -> None:
    assert CURRENT_LEGAL_CLASSIFICATION.counsel_engaged is False


def test_current_legal_classification_live_not_authorized() -> None:
    assert CURRENT_LEGAL_CLASSIFICATION.live_authorized is False


def test_legal_classification_config_live_authorized_raises() -> None:
    with pytest.raises(ValueError, match="live_authorized"):
        LegalClassificationConfig(
            jurisdiction=LegalJurisdiction.EU_MICA,
            templates=("MiCA",),
            counsel_engaged=False,
            live_authorized=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# 01.6 — Notification Providers
# ──────────────────────────────────────────────────────────────────────────────


def test_current_notification_provider_is_sendgrid_email() -> None:
    assert len(CURRENT_NOTIFICATION_PROVIDERS) == 1
    provider = CURRENT_NOTIFICATION_PROVIDERS[0]
    assert provider.channel == NotificationChannel.EMAIL
    assert provider.provider == "sendgrid"
    assert provider.is_current is True


def test_roadmap_notification_providers_include_slack_and_sms() -> None:
    channels = {str(p.channel) for p in ROADMAP_NOTIFICATION_PROVIDERS}
    assert "slack" in channels
    assert "sms" in channels


def test_roadmap_notification_providers_require_dual_control() -> None:
    for provider in ROADMAP_NOTIFICATION_PROVIDERS:
        assert provider.dual_control is True
        assert provider.is_current is False


def test_current_notification_provider_no_dual_control() -> None:
    for provider in CURRENT_NOTIFICATION_PROVIDERS:
        assert provider.dual_control is False


# ──────────────────────────────────────────────────────────────────────────────
# 01.7 — Pricing Tiers
# ──────────────────────────────────────────────────────────────────────────────


def test_tier1_monthly_price_is_49() -> None:
    assert TIER_MONTHLY_USD["TIER_1"] == Decimal("49.00")


def test_tier2_monthly_price_is_99() -> None:
    assert TIER_MONTHLY_USD["TIER_2"] == Decimal("99.00")


def test_tier3_monthly_price_is_149() -> None:
    assert TIER_MONTHLY_USD["TIER_3"] == Decimal("149.00")


def test_tier1_annual_monthly_price_is_39() -> None:
    assert TIER_ANNUAL_MONTHLY_USD["TIER_1"] == Decimal("39.00")


def test_tier2_annual_monthly_price_is_79() -> None:
    assert TIER_ANNUAL_MONTHLY_USD["TIER_2"] == Decimal("79.00")


def test_tier3_annual_monthly_price_is_119() -> None:
    assert TIER_ANNUAL_MONTHLY_USD["TIER_3"] == Decimal("119.00")


def test_annual_discount_rate_in_valid_range() -> None:
    assert Decimal("0") <= ANNUAL_DISCOUNT_RATE < Decimal("1")


def test_free_trial_is_one_week() -> None:
    assert FREE_TRIAL_DAYS == 7


def test_tier1_annual_plan_total() -> None:
    plan = build_plan(SubscriptionTier.TIER_1, BillingPeriod.ANNUAL)
    assert plan.monthly_usd == Decimal("39.00")
    assert plan.total_usd == Decimal("39.00") * 12
    assert plan.total_usd < TIER_MONTHLY_USD["TIER_1"] * 12


def test_tier2_annual_plan_total() -> None:
    plan = build_plan(SubscriptionTier.TIER_2, BillingPeriod.ANNUAL)
    assert plan.monthly_usd == Decimal("79.00")
    assert plan.total_usd == Decimal("79.00") * 12


def test_tier3_annual_plan_total() -> None:
    plan = build_plan(SubscriptionTier.TIER_3, BillingPeriod.ANNUAL)
    assert plan.monthly_usd == Decimal("119.00")
    assert plan.total_usd == Decimal("119.00") * 12


def test_tier1_monthly_plan_total() -> None:
    plan = build_plan(SubscriptionTier.TIER_1, BillingPeriod.MONTHLY)
    assert plan.total_usd == Decimal("49.00")
    assert plan.monthly_usd == Decimal("49.00")


def test_tier2_monthly_plan_total() -> None:
    plan = build_plan(SubscriptionTier.TIER_2, BillingPeriod.MONTHLY)
    assert plan.total_usd == Decimal("99.00")


def test_tier3_monthly_plan_total() -> None:
    plan = build_plan(SubscriptionTier.TIER_3, BillingPeriod.MONTHLY)
    assert plan.total_usd == Decimal("149.00")


# ──────────────────────────────────────────────────────────────────────────────
# PlatformConfig aggregate
# ──────────────────────────────────────────────────────────────────────────────


def test_platform_config_has_all_current_decisions() -> None:
    assert PLATFORM_CONFIG.cloud_provider == CURRENT_CLOUD_PROVIDER
    assert PLATFORM_CONFIG.event_bus == CURRENT_EVENT_BUS
    assert PLATFORM_CONFIG.slo_targets == CURRENT_SLO_TARGETS
    assert PLATFORM_CONFIG.exchange_providers == CURRENT_EXCHANGE_PROVIDERS
    assert PLATFORM_CONFIG.legal_classification == CURRENT_LEGAL_CLASSIFICATION
    assert PLATFORM_CONFIG.notification_providers == CURRENT_NOTIFICATION_PROVIDERS


def test_platform_config_live_trading_authorized_is_false() -> None:
    assert PLATFORM_CONFIG.live_trading_authorized is False


def test_platform_config_live_authorized_raises_if_true() -> None:
    with pytest.raises(ValueError, match="live_trading_authorized"):
        PlatformConfig(
            cloud_provider=CloudProvider.RENDER,
            event_bus=EventBusProvider.REDIS_STREAMS,
            slo_targets=CURRENT_SLO_TARGETS,
            exchange_providers=CURRENT_EXCHANGE_PROVIDERS,
            legal_classification=CURRENT_LEGAL_CLASSIFICATION,
            notification_providers=CURRENT_NOTIFICATION_PROVIDERS,
            live_trading_authorized=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# BillingService integration with new pricing
# ──────────────────────────────────────────────────────────────────────────────


def test_billing_service_tier1_monthly_subscription_price() -> None:
    log = BillingEventLog()
    billing = BillingService(event_log=log)
    from uuid import uuid4

    sub = billing.subscribe(
        tenant_id=uuid4(),
        tier=SubscriptionTier.TIER_1,
        period=BillingPeriod.MONTHLY,
    )
    assert sub.plan.total_usd == Decimal("49.00")


def test_billing_service_tier3_monthly_subscription_price() -> None:
    log = BillingEventLog()
    billing = BillingService(event_log=log)
    from uuid import uuid4

    sub = billing.subscribe(
        tenant_id=uuid4(),
        tier=SubscriptionTier.TIER_3,
        period=BillingPeriod.MONTHLY,
    )
    assert sub.plan.total_usd == Decimal("149.00")


def test_billing_service_tier2_annual_subscription_price() -> None:
    log = BillingEventLog()
    billing = BillingService(event_log=log)
    from uuid import uuid4

    sub = billing.subscribe(
        tenant_id=uuid4(),
        tier=SubscriptionTier.TIER_2,
        period=BillingPeriod.ANNUAL,
    )
    assert sub.plan.total_usd == Decimal("79.00") * 12
    assert sub.plan.monthly_usd == Decimal("79.00")
