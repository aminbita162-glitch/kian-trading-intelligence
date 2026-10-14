"""Commercial monetization, payment tier and market-readiness contracts.

Per E10 (Commercial Monetization, Payment Tiers and Market Readiness) and
AD-034 (Commercial Monetization and Payment Tiers):

Four tier levels:
  FREE_TRIAL   — one-week trial; simulation/paper only; no real capital.
  TIER_1       — monthly USD 200 (or annual at owner-approved discount).
  TIER_2       — monthly USD 350 (or annual at owner-approved discount).
  TIER_3       — monthly USD 500 (or annual at owner-approved discount).

Usage metering covers: orders, LLM tokens, market-data requests, compute
seconds.  All billing events are audited and can never weaken safety
invariants.

Architecture Decisions: AD-034 (Commercial Monetization and Payment Tiers).

These contracts are leaf-level — they must NOT import from services or
simulation (import-linter contracts-is-leaf).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

# ──────────────────────────────────────────────────────────────────────────────
# Pricing constants  (owner may update exact annual discount via OD-7)
# ──────────────────────────────────────────────────────────────────────────────

#: Monthly prices in USD (exact; Decimal for financial correctness).
TIER_MONTHLY_USD: dict[str, Decimal] = {
    "TIER_1": Decimal("200.00"),
    "TIER_2": Decimal("350.00"),
    "TIER_3": Decimal("500.00"),
}

#: Annual discount rate applied to monthly price × 12 (owner-set per OD-7).
#: Default 16.67% ≈ 2 months free; final value requires owner sign-off.
ANNUAL_DISCOUNT_RATE: Decimal = Decimal("0.1667")

#: Free-trial duration per AD-034.
FREE_TRIAL_DAYS: int = 7


# ──────────────────────────────────────────────────────────────────────────────
# Tier and billing period enumerations
# ──────────────────────────────────────────────────────────────────────────────


class SubscriptionTier(StrEnum):
    """Commercial subscription tiers per AD-034.

    Attributes:
        FREE_TRIAL:  One-week trial — simulation/paper only; no real capital.
        TIER_1:      USD 200/month baseline paid tier.
        TIER_2:      USD 350/month advanced paid tier.
        TIER_3:      USD 500/month full-feature paid tier.
    """

    FREE_TRIAL = "free_trial"
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class BillingPeriod(StrEnum):
    """Billing cadence for paid subscriptions."""

    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(StrEnum):
    """Lifecycle status of a tenant subscription."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


class MeteringDimension(StrEnum):
    """Usage metering dimensions per AD-034.

    Attributes:
        ORDERS:        Count of order intents submitted to the Risk Kernel.
        LLM_TOKENS:    Cumulative LLM token consumption across agents.
        MARKET_DATA:   Count of market-data requests to external providers.
        COMPUTE_SEC:   Agent/strategy compute time in seconds (fractional).
    """

    ORDERS = "orders"
    LLM_TOKENS = "llm_tokens"
    MARKET_DATA = "market_data"
    COMPUTE_SEC = "compute_sec"


class BillingEventType(StrEnum):
    """Types of auditable billing lifecycle events."""

    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_RENEWED = "subscription_renewed"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    SUBSCRIPTION_SUSPENDED = "subscription_suspended"
    TIER_CHANGED = "tier_changed"
    TRIAL_STARTED = "trial_started"
    TRIAL_EXPIRED = "trial_expired"
    USAGE_RECORDED = "usage_recorded"
    USAGE_LIMIT_WARNING = "usage_limit_warning"
    USAGE_LIMIT_EXCEEDED = "usage_limit_exceeded"
    BILLING_PROVIDER_EVENT = "billing_provider_event"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    ONBOARDING_COMPLETED = "onboarding_completed"
    MARKET_READINESS_ASSESSED = "market_readiness_assessed"


class OnboardingStep(StrEnum):
    """Commercial onboarding funnel steps."""

    ACCOUNT_CREATED = "account_created"
    EMAIL_VERIFIED = "email_verified"
    MFA_ENROLLED = "mfa_enrolled"
    TRIAL_ACTIVATED = "trial_activated"
    PAYMENT_METHOD_ADDED = "payment_method_added"
    SUBSCRIPTION_SELECTED = "subscription_selected"
    TERMS_ACCEPTED = "terms_accepted"
    ONBOARDING_COMPLETE = "onboarding_complete"


class TierFeature(StrEnum):
    """Feature flags gated by subscription tier.

    Safety invariants (risk kernel, kill plane, audit) are NEVER gated —
    they are always enabled regardless of tier per AD-034.
    """

    # Simulation / paper — available on all tiers including FREE_TRIAL
    SIMULATION_MODE = "simulation_mode"
    PAPER_TRADING = "paper_trading"

    # Features unlocked from TIER_1
    ADVANCED_INDICATORS = "advanced_indicators"
    STRATEGY_BACKTESTING = "strategy_backtesting"
    EMAIL_NOTIFICATIONS = "email_notifications"
    BASIC_AGENT_ACCESS = "basic_agent_access"

    # Features unlocked from TIER_2
    FULL_AGENT_ACCESS = "full_agent_access"
    MULTI_STRATEGY = "multi_strategy"
    MINING_SIMULATION = "mining_simulation"
    ADVANCED_RISK_REPORTS = "advanced_risk_reports"
    PRIORITY_SUPPORT = "priority_support"

    # Features unlocked from TIER_3
    API_ACCESS = "api_access"
    CUSTOM_STRATEGY_IMPORT = "custom_strategy_import"
    UNIT_ECONOMICS_DASHBOARD = "unit_economics_dashboard"
    DEDICATED_SUPPORT = "dedicated_support"
    ADVANCED_COMPLIANCE_REPORTS = "advanced_compliance_reports"

    # Live trading — requires separate written authorization beyond tier
    LIVE_TRADING_ELIGIBLE = "live_trading_eligible"


# ──────────────────────────────────────────────────────────────────────────────
# Feature gate table  (safety invariants always unlocked — never listed here)
# ──────────────────────────────────────────────────────────────────────────────

#: Maps tier → set of features available at that tier and above.
#: A feature is available if it appears in the set for the tenant's tier
#: OR any lower tier (see ``tier_has_feature``).
TIER_FEATURE_MAP: dict[SubscriptionTier, frozenset[TierFeature]] = {
    SubscriptionTier.FREE_TRIAL: frozenset(
        {
            TierFeature.SIMULATION_MODE,
            TierFeature.PAPER_TRADING,
        }
    ),
    SubscriptionTier.TIER_1: frozenset(
        {
            TierFeature.SIMULATION_MODE,
            TierFeature.PAPER_TRADING,
            TierFeature.ADVANCED_INDICATORS,
            TierFeature.STRATEGY_BACKTESTING,
            TierFeature.EMAIL_NOTIFICATIONS,
            TierFeature.BASIC_AGENT_ACCESS,
        }
    ),
    SubscriptionTier.TIER_2: frozenset(
        {
            TierFeature.SIMULATION_MODE,
            TierFeature.PAPER_TRADING,
            TierFeature.ADVANCED_INDICATORS,
            TierFeature.STRATEGY_BACKTESTING,
            TierFeature.EMAIL_NOTIFICATIONS,
            TierFeature.BASIC_AGENT_ACCESS,
            TierFeature.FULL_AGENT_ACCESS,
            TierFeature.MULTI_STRATEGY,
            TierFeature.MINING_SIMULATION,
            TierFeature.ADVANCED_RISK_REPORTS,
            TierFeature.PRIORITY_SUPPORT,
        }
    ),
    SubscriptionTier.TIER_3: frozenset(
        {
            TierFeature.SIMULATION_MODE,
            TierFeature.PAPER_TRADING,
            TierFeature.ADVANCED_INDICATORS,
            TierFeature.STRATEGY_BACKTESTING,
            TierFeature.EMAIL_NOTIFICATIONS,
            TierFeature.BASIC_AGENT_ACCESS,
            TierFeature.FULL_AGENT_ACCESS,
            TierFeature.MULTI_STRATEGY,
            TierFeature.MINING_SIMULATION,
            TierFeature.ADVANCED_RISK_REPORTS,
            TierFeature.PRIORITY_SUPPORT,
            TierFeature.API_ACCESS,
            TierFeature.CUSTOM_STRATEGY_IMPORT,
            TierFeature.UNIT_ECONOMICS_DASHBOARD,
            TierFeature.DEDICATED_SUPPORT,
            TierFeature.ADVANCED_COMPLIANCE_REPORTS,
            TierFeature.LIVE_TRADING_ELIGIBLE,
        }
    ),
}


def tier_has_feature(tier: SubscriptionTier, feature: TierFeature) -> bool:
    """Return True if ``feature`` is available at the given ``tier``.

    Live-trading eligibility (``TierFeature.LIVE_TRADING_ELIGIBLE``) is
    necessary but NOT sufficient — separate written authorization is still
    required per AD-034 and Section 00.4.
    """
    return feature in TIER_FEATURE_MAP.get(tier, frozenset())


# ──────────────────────────────────────────────────────────────────────────────
# Usage metering limits per tier  (None = unlimited within fair-use policy)
# ──────────────────────────────────────────────────────────────────────────────

#: Monthly usage limits per metering dimension.  None = no hard cap.
TIER_USAGE_LIMITS: dict[SubscriptionTier, dict[MeteringDimension, int | None]] = {
    SubscriptionTier.FREE_TRIAL: {
        MeteringDimension.ORDERS: 20,
        MeteringDimension.LLM_TOKENS: 50_000,
        MeteringDimension.MARKET_DATA: 500,
        MeteringDimension.COMPUTE_SEC: 300,
    },
    SubscriptionTier.TIER_1: {
        MeteringDimension.ORDERS: 500,
        MeteringDimension.LLM_TOKENS: 2_000_000,
        MeteringDimension.MARKET_DATA: 50_000,
        MeteringDimension.COMPUTE_SEC: 18_000,
    },
    SubscriptionTier.TIER_2: {
        MeteringDimension.ORDERS: 2_000,
        MeteringDimension.LLM_TOKENS: 8_000_000,
        MeteringDimension.MARKET_DATA: 200_000,
        MeteringDimension.COMPUTE_SEC: 72_000,
    },
    SubscriptionTier.TIER_3: {
        MeteringDimension.ORDERS: None,
        MeteringDimension.LLM_TOKENS: None,
        MeteringDimension.MARKET_DATA: None,
        MeteringDimension.COMPUTE_SEC: None,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Typed IDs
# ──────────────────────────────────────────────────────────────────────────────

SubscriptionId = UUID
UsageRecordId = UUID
BillingEventId = UUID
OnboardingRecordId = UUID


# ──────────────────────────────────────────────────────────────────────────────
# Core data contracts
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SubscriptionPlan:
    """Immutable description of a subscription plan's pricing.

    Attributes:
        tier:                 Subscription tier.
        period:               Billing period (monthly or annual).
        monthly_usd:          Equivalent monthly cost in USD.
        total_usd:            Total charge for the billing period.
        annual_discount_rate: Fractional annual discount applied (0 for monthly).
    """

    tier: SubscriptionTier
    period: BillingPeriod
    monthly_usd: Decimal
    total_usd: Decimal
    annual_discount_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.tier == SubscriptionTier.FREE_TRIAL and self.total_usd != Decimal("0"):
            raise ValueError("FREE_TRIAL must have total_usd == 0")
        if self.monthly_usd < Decimal("0") or self.total_usd < Decimal("0"):
            raise ValueError("Plan prices must be non-negative")
        if not (Decimal("0") <= self.annual_discount_rate < Decimal("1")):
            raise ValueError("annual_discount_rate must be in [0, 1)")


@dataclass
class TenantSubscription:
    """Active subscription record for a tenant.

    Attributes:
        id:          Unique subscription identifier.
        tenant_id:   Owning tenant UUID.
        plan:        Immutable plan snapshot at subscription time.
        status:      Current lifecycle status.
        started_at:  Subscription start timestamp (UTC).
        current_period_start: Start of the current billing period.
        current_period_end:   End of the current billing period (exclusive).
        cancelled_at: Cancellation timestamp, if cancelled.
        trial_ends_at: Trial expiry timestamp (FREE_TRIAL only; None otherwise).
        external_subscription_id: Opaque ID from the billing provider (if set).
        metadata:    Arbitrary auditable metadata.
    """

    id: SubscriptionId = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    plan: SubscriptionPlan = field(
        default_factory=lambda: SubscriptionPlan(
            tier=SubscriptionTier.FREE_TRIAL,
            period=BillingPeriod.MONTHLY,
            monthly_usd=Decimal("0"),
            total_usd=Decimal("0"),
        )
    )
    status: SubscriptionStatus = SubscriptionStatus.TRIALING
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    current_period_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    current_period_end: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(days=FREE_TRIAL_DAYS)
    )
    cancelled_at: datetime | None = None
    trial_ends_at: datetime | None = None
    external_subscription_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.plan.tier == SubscriptionTier.FREE_TRIAL and self.trial_ends_at is None:
            object.__setattr__(
                self,
                "trial_ends_at",
                self.started_at + timedelta(days=FREE_TRIAL_DAYS),
            )
        if self.current_period_end <= self.current_period_start:
            raise ValueError("current_period_end must be after current_period_start")

    @property
    def is_trial(self) -> bool:
        """True when this subscription is on the free trial."""
        return self.plan.tier == SubscriptionTier.FREE_TRIAL

    @property
    def tier(self) -> SubscriptionTier:
        """Convenience accessor for the active tier."""
        return self.plan.tier


@dataclass(frozen=True)
class UsageRecord:
    """A single metered usage event for a tenant billing period.

    Attributes:
        id:          Unique record identifier.
        tenant_id:   Owning tenant UUID.
        subscription_id: Related subscription.
        dimension:   Which metering dimension this record belongs to.
        quantity:    Amount consumed.  Must be > 0.
        recorded_at: UTC timestamp of consumption.
        period_start: Billing period start for this record.
        period_end:   Billing period end for this record.
        source:      Optional free-text source identifier (agent name, etc.).
        metadata:    Arbitrary auditable metadata.
    """

    id: UsageRecordId = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    subscription_id: SubscriptionId = field(default_factory=uuid4)
    dimension: MeteringDimension = MeteringDimension.ORDERS
    quantity: Decimal = Decimal("1")
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    period_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    period_end: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(days=FREE_TRIAL_DAYS)
    )
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quantity <= Decimal("0"):
            raise ValueError("UsageRecord.quantity must be > 0")


@dataclass(frozen=True)
class UsageSummary:
    """Aggregated usage across a billing period for a tenant.

    Attributes:
        tenant_id:       Owning tenant.
        subscription_id: Related subscription.
        period_start:    Billing period start.
        period_end:      Billing period end.
        tier:            Active subscription tier during this period.
        totals:          Map of dimension → total quantity consumed.
        limits:          Map of dimension → limit (None = unlimited).
        warnings:        Dimensions that have crossed the 80% warning threshold.
        exceeded:        Dimensions that have exceeded the hard limit.
    """

    tenant_id: UUID
    subscription_id: SubscriptionId
    period_start: datetime
    period_end: datetime
    tier: SubscriptionTier
    totals: dict[MeteringDimension, Decimal]
    limits: dict[MeteringDimension, int | None]
    warnings: list[MeteringDimension]
    exceeded: list[MeteringDimension]


@dataclass(frozen=True)
class BillingEvent:
    """An immutable, auditable billing lifecycle event.

    Invariant: ``event_hash`` is a SHA-256 hex digest of the canonical
    JSON serialisation of the event's content fields.  Any mutation of
    content invalidates the hash.
    """

    id: BillingEventId = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    subscription_id: SubscriptionId | None = None
    event_type: BillingEventType = BillingEventType.SUBSCRIPTION_CREATED
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = field(default_factory=dict)
    event_hash: str = field(init=False, default="")

    def __post_init__(self) -> None:
        content = {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "subscription_id": str(self.subscription_id) if self.subscription_id else None,
            "event_type": str(self.event_type),
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
        }
        digest = hashlib.sha256(
            json.dumps(content, sort_keys=True, default=str).encode()
        ).hexdigest()
        object.__setattr__(self, "event_hash", digest)


@dataclass
class OnboardingRecord:
    """Commercial onboarding progress for a tenant.

    Tracks which onboarding steps have been completed.  The record is
    append-only: steps can be completed but never un-completed.

    Invariant: ``onboarding_complete_at`` is only set when ALL required
    steps have been completed and ``is_complete`` returns True.
    """

    id: OnboardingRecordId = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_steps: list[OnboardingStep] = field(default_factory=list)
    onboarding_complete_at: datetime | None = None

    # Steps required for onboarding_complete to be declared
    REQUIRED_STEPS: frozenset[OnboardingStep] = field(
        default=frozenset(
            {
                OnboardingStep.ACCOUNT_CREATED,
                OnboardingStep.EMAIL_VERIFIED,
                OnboardingStep.TRIAL_ACTIVATED,
                OnboardingStep.TERMS_ACCEPTED,
            }
        ),
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def is_complete(self) -> bool:
        """True when all required steps are in completed_steps."""
        return self.REQUIRED_STEPS.issubset(set(self.completed_steps))

    @property
    def pending_steps(self) -> list[OnboardingStep]:
        """List of required steps not yet completed."""
        done = set(self.completed_steps)
        return [s for s in OnboardingStep if s in self.REQUIRED_STEPS and s not in done]


# ──────────────────────────────────────────────────────────────────────────────
# Unit-economics dashboard contracts
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TierMetrics:
    """Point-in-time metrics for a single subscription tier.

    Attributes:
        tier:                 The subscription tier.
        active_subscriptions: Count of tenants in ACTIVE or TRIALING status.
        monthly_recurring_revenue_usd: Total MRR in USD.
        annual_recurring_revenue_usd:  ARR (MRR × 12).
        trial_conversions:   Count of trials that converted to paid.
        churned:             Count of cancellations in the measurement window.
    """

    tier: SubscriptionTier
    active_subscriptions: int
    monthly_recurring_revenue_usd: Decimal
    annual_recurring_revenue_usd: Decimal
    trial_conversions: int
    churned: int

    def __post_init__(self) -> None:
        if self.active_subscriptions < 0:
            raise ValueError("active_subscriptions cannot be negative")
        if self.monthly_recurring_revenue_usd < Decimal("0"):
            raise ValueError("MRR cannot be negative")


@dataclass(frozen=True)
class UnitEconomicsDashboard:
    """Aggregated unit-economics snapshot for the operator.

    Produced by the unit-economics service and signed with a SHA-256 hash
    of the content for audit traceability.

    Attributes:
        generated_at:    UTC timestamp of snapshot generation.
        total_tenants:   Count of all tenants (any status).
        active_tenants:  Count of tenants with ACTIVE or TRIALING subscription.
        tier_metrics:    Per-tier breakdown.
        total_mrr_usd:   Platform-wide MRR (USD).
        total_arr_usd:   Platform-wide ARR (USD).
        total_trial_conversions: Sum of trial conversions across tiers.
        total_churned:   Sum of churn events across tiers.
        snapshot_hash:   SHA-256 of canonical content.
    """

    generated_at: datetime
    total_tenants: int
    active_tenants: int
    tier_metrics: list[TierMetrics]
    total_mrr_usd: Decimal
    total_arr_usd: Decimal
    total_trial_conversions: int
    total_churned: int
    snapshot_hash: str = field(init=False, default="")

    def __post_init__(self) -> None:
        content = {
            "generated_at": self.generated_at.isoformat(),
            "total_tenants": self.total_tenants,
            "active_tenants": self.active_tenants,
            "total_mrr_usd": str(self.total_mrr_usd),
            "total_arr_usd": str(self.total_arr_usd),
            "total_trial_conversions": self.total_trial_conversions,
            "total_churned": self.total_churned,
        }
        digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        object.__setattr__(self, "snapshot_hash", digest)


# ──────────────────────────────────────────────────────────────────────────────
# Market-readiness gate contracts
# ──────────────────────────────────────────────────────────────────────────────


class MarketReadinessGate(StrEnum):
    """Section 23 market-readiness gates that must pass before commercial claim.

    Each gate maps to a verifiable evidence item in the test-house.
    """

    PAYMENT_TIERS_ENFORCEABLE = "payment_tiers_enforceable"
    BILLING_EVENTS_AUDITED = "billing_events_audited"
    USAGE_METERING_ACCURATE = "usage_metering_accurate"
    SAFETY_INVARIANTS_UNWEAKENED = "safety_invariants_unweakened"
    TIER_ENFORCEMENT_TESTED = "tier_enforcement_tested"
    ONBOARDING_FLOW_COMPLETE = "onboarding_flow_complete"
    UNIT_ECONOMICS_DASHBOARD_OPERATIONAL = "unit_economics_dashboard_operational"
    APPLE_DEVELOPER_DECISION_DOCUMENTED = "apple_developer_decision_documented"
    ANNUAL_DISCOUNT_OWNER_CONFIRMED = "annual_discount_owner_confirmed"
    LEGAL_SIGN_OFF_PENDING = "legal_sign_off_pending"
    OPEN_DECISIONS_RECORDED = "open_decisions_recorded"


class GateStatus(StrEnum):
    """Status of a single market-readiness gate."""

    PASS = "pass"
    FAIL = "fail"
    CONDITIONAL_PASS = "conditional_pass"
    PENDING_OWNER = "pending_owner"


@dataclass(frozen=True)
class GateResult:
    """Result for a single market-readiness gate evaluation."""

    gate: MarketReadinessGate
    status: GateStatus
    evidence: str
    notes: str = ""


@dataclass(frozen=True)
class MarketReadinessReport:
    """Final market-readiness assessment per Section 23 gates.

    Invariant: ``owner_sign_off_required`` is always True — the owner must
    explicitly sign the final readiness package before commercial claim.

    Invariant: ``live_trading_authorized`` is always False — live activation
    requires a separate written decision per AD-034 and Section 00.4.
    """

    generated_at: datetime
    gate_results: list[GateResult]
    overall_status: GateStatus
    residual_risks: list[str]
    owner_sign_off_required: bool = field(default=True, init=False)
    live_trading_authorized: bool = field(default=False, init=False)
    report_hash: str = field(init=False, default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_sign_off_required", True)
        object.__setattr__(self, "live_trading_authorized", False)
        content = {
            "generated_at": self.generated_at.isoformat(),
            "overall_status": str(self.overall_status),
            "gate_count": len(self.gate_results),
            "residual_risks": self.residual_risks,
        }
        digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        object.__setattr__(self, "report_hash", digest)

    @property
    def all_gates_pass(self) -> bool:
        """True only when every gate is PASS or CONDITIONAL_PASS."""
        return all(
            r.status in (GateStatus.PASS, GateStatus.CONDITIONAL_PASS) for r in self.gate_results
        )


# ──────────────────────────────────────────────────────────────────────────────
# Apple Developer / PWA distribution decision
# ──────────────────────────────────────────────────────────────────────────────


class DistributionChannel(StrEnum):
    """Target distribution channel for the client application."""

    TAURI_MACOS = "tauri_macos"
    PWA_IOS = "pwa_ios"
    APPLE_NATIVE_IOS = "apple_native_ios"


@dataclass(frozen=True)
class ApplePlatformDecision:
    """Owner decision record for Apple Developer Program usage (OD-8).

    Per E10 scope: evaluate whether the USD 99/year Apple Developer Program
    license is required and document the decision.

    Invariant: ``pwa_path_requires_apple_license`` is always False — PWA
    delivery does not require the Apple Developer Program for basic iPhone
    access.
    """

    decided_at: datetime
    tauri_macos_distribution: bool
    """True if macOS Tauri app will be distributed via Mac App Store."""
    apple_developer_program_required: bool
    """True if the Apple Developer Program ($99/year) is needed."""
    rationale: str
    channels: list[DistributionChannel]
    pwa_path_requires_apple_license: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pwa_path_requires_apple_license", False)
        if not self.rationale.strip():
            raise ValueError("ApplePlatformDecision.rationale must not be empty")


# ──────────────────────────────────────────────────────────────────────────────
# Domain exceptions
# ──────────────────────────────────────────────────────────────────────────────


class BillingError(Exception):
    """Base class for billing domain errors."""


class FeatureNotAvailableError(BillingError):
    """Raised when a tenant attempts to access a feature not in their tier."""

    def __init__(self, tenant_id: UUID, feature: TierFeature, tier: SubscriptionTier) -> None:
        super().__init__(
            f"Feature {feature!r} is not available on tier {tier!r} for tenant {tenant_id}"
        )
        self.tenant_id = tenant_id
        self.feature = feature
        self.tier = tier


class UsageLimitExceededError(BillingError):
    """Raised when a usage metering hard limit is exceeded."""

    def __init__(
        self,
        tenant_id: UUID,
        dimension: MeteringDimension,
        limit: int,
        current: Decimal,
    ) -> None:
        super().__init__(
            f"Usage limit exceeded for tenant {tenant_id}: "
            f"{dimension!r} current={current} limit={limit}"
        )
        self.tenant_id = tenant_id
        self.dimension = dimension
        self.limit = limit
        self.current = current


class SubscriptionNotFoundError(BillingError):
    """Raised when no active subscription exists for a tenant."""

    def __init__(self, tenant_id: UUID) -> None:
        super().__init__(f"No active subscription found for tenant {tenant_id}")
        self.tenant_id = tenant_id
