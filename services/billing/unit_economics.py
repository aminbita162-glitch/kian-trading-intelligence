"""Unit-economics dashboard service for Kian Trading Intelligence.

Per E10 (Commercial Monetization, Payment Tiers and Market Readiness) and
AD-034 (Commercial Monetization and Payment Tiers).

Produces point-in-time, hash-signed ``UnitEconomicsDashboard`` snapshots
that aggregate MRR, ARR, trial conversions, churn and per-tier breakdowns
for the operator.

The ``UnitEconomicsService.snapshot()`` method is the primary entry point.
Snapshots are retained in-memory for audit purposes; production deployments
should persist them to PostgreSQL.

Architecture Decisions: AD-034 (Commercial Monetization and Payment Tiers).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal

from contracts.billing import (
    BillingEventType,
    SubscriptionStatus,
    SubscriptionTier,
    TierMetrics,
    UnitEconomicsDashboard,
)
from services.billing import BillingEventLog, BillingService


class UnitEconomicsService:
    """Produces hashed, auditable unit-economics dashboard snapshots.

    Computes per-tier and platform-wide KPIs from the live subscription
    and billing-event state.

    Thread-safe.
    """

    def __init__(
        self,
        billing_service: BillingService,
        event_log: BillingEventLog,
    ) -> None:
        self._billing = billing_service
        self._event_log = event_log
        self._lock = threading.Lock()
        self._snapshots: list[UnitEconomicsDashboard] = []

    def snapshot(self) -> UnitEconomicsDashboard:
        """Produce a point-in-time unit-economics dashboard snapshot.

        The returned ``UnitEconomicsDashboard`` carries a SHA-256
        ``snapshot_hash`` for tamper detection.  The snapshot is also
        retained internally for audit history.
        """
        all_subs = self._billing.all_subscriptions()
        all_events = self._event_log.events()

        total_tenants = len(all_subs)
        active_statuses = {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}
        active_tenants = sum(1 for s in all_subs if s.status in active_statuses)

        tier_metrics: list[TierMetrics] = []
        total_mrr = Decimal("0")
        total_arr = Decimal("0")
        total_conversions = 0
        total_churned = 0

        for tier in SubscriptionTier:
            tier_subs = [s for s in all_subs if s.tier == tier]
            active_count = sum(1 for s in tier_subs if s.status in active_statuses)

            # MRR: sum of active subscription monthly equivalents
            mrr = Decimal("0")
            for s in tier_subs:
                if s.status == SubscriptionStatus.ACTIVE:
                    mrr += s.plan.monthly_usd

            arr = mrr * 12

            # Trial conversions: TIER_CHANGED events from FREE_TRIAL → any paid tier
            conversions = sum(
                1
                for e in all_events
                if e.event_type == BillingEventType.TIER_CHANGED
                and e.payload.get("previous_tier") == str(SubscriptionTier.FREE_TRIAL)
                and e.payload.get("tier") == str(tier)
            )

            # Churn: SUBSCRIPTION_CANCELLED events for this tier
            churned = sum(1 for s in tier_subs if s.status == SubscriptionStatus.CANCELLED)

            tier_metrics.append(
                TierMetrics(
                    tier=tier,
                    active_subscriptions=active_count,
                    monthly_recurring_revenue_usd=mrr,
                    annual_recurring_revenue_usd=arr,
                    trial_conversions=conversions,
                    churned=churned,
                )
            )

            total_mrr += mrr
            total_arr += arr
            total_conversions += conversions
            total_churned += churned

        dashboard = UnitEconomicsDashboard(
            generated_at=datetime.now(UTC),
            total_tenants=total_tenants,
            active_tenants=active_tenants,
            tier_metrics=tier_metrics,
            total_mrr_usd=total_mrr,
            total_arr_usd=total_arr,
            total_trial_conversions=total_conversions,
            total_churned=total_churned,
        )

        with self._lock:
            self._snapshots.append(dashboard)

        return dashboard

    def snapshot_history(self) -> list[UnitEconomicsDashboard]:
        """Return a list of all previously generated snapshots."""
        with self._lock:
            return list(self._snapshots)
