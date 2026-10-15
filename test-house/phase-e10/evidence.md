# Phase E10 — Commercial Monetization, Payment Tiers and Market Readiness

**Branch:** `phase/e10-commercial-monetization`
**Date:** 2025-07-11
**AD Refs:** AD-034 (Commercial Monetization and Payment Tiers)

---

## Scope

Phase E10 delivers the complete commercial monetization layer for Kian Trading
Intelligence per AD-034, including four subscription tiers, usage metering,
billing event audit, commercial onboarding, unit-economics dashboard, Apple
Developer Program decision documentation, and the final Section 23
market-readiness report.

**Completing E10 DOES NOT authorize live trading.**
Live activation requires a separate written owner decision per AD-034 and
Section 00.4 of DIRECTIV.txt.

---

## Deliverables

### Contracts (`packages/contracts/billing.py`)

| Contract | Purpose |
|---|---|
| `SubscriptionTier` | FREE_TRIAL (7 days), TIER_1 ($49/mo), TIER_2 ($99/mo), TIER_3 ($149/mo) |
| `BillingPeriod` | MONTHLY and ANNUAL (ANNUAL_DISCOUNT_RATE 16.67% default; OD-7 pending) |
| `SubscriptionStatus` | TRIALING → ACTIVE → PAST_DUE → CANCELLED / EXPIRED / SUSPENDED |
| `MeteringDimension` | ORDERS, LLM_TOKENS, MARKET_DATA, COMPUTE_SEC |
| `BillingEventType` | 17 auditable lifecycle event types |
| `OnboardingStep` | 8-step commercial onboarding funnel |
| `TierFeature` | Commercial feature flags; safety features NEVER gated here |
| `TIER_FEATURE_MAP` | Immutable tier → frozenset[TierFeature]; `tier_has_feature()` helper |
| `TIER_USAGE_LIMITS` | Per-tier monthly limits; TIER_3 all dimensions unlimited |
| `SubscriptionPlan` | Immutable plan; FREE_TRIAL always $0 invariant; negative price rejected; discount rate in [0,1) |
| `TenantSubscription` | Mutable subscription record; period_end > period_start invariant |
| `UsageRecord` | Frozen metered event; quantity > 0 invariant |
| `UsageSummary` | Aggregated period usage with warning/exceeded dimension lists |
| `BillingEvent` | Frozen, SHA-256 hash-signed auditable billing event; immutability verified |
| `OnboardingRecord` | Append-only onboarding funnel; required-step tracking; REQUIRED_STEPS constant |
| `TierMetrics` | Per-tier MRR/ARR/conversions/churn; negative values rejected |
| `UnitEconomicsDashboard` | Platform-wide unit-economics snapshot with snapshot_hash |
| `MarketReadinessGate` | 11 Section 23 readiness gates |
| `GateResult` / `MarketReadinessReport` | Gate evaluation results; `live_trading_authorized` always False; `owner_sign_off_required` always True; report_hash set |
| `ApplePlatformDecision` | OD-8 record; `pwa_path_requires_apple_license` always False; empty rationale rejected |
| `FeatureNotAvailableError` | Tier gate violation |
| `UsageLimitExceededError` | Usage hard limit exceeded (never weakens safety) |
| `SubscriptionNotFoundError` | Missing tenant subscription |

### Service (`services/billing/__init__.py`)

| Class / Function | Responsibility |
|---|---|
| `build_plan()` | Constructs `SubscriptionPlan` with correct monthly/annual pricing and discount |
| `BillingEventLog` | Append-only, SHA-256 hash-chain log; `verify_chain()` detects tampered events; thread-safe |
| `UsageMeteringService` | Records usage; emits 80% warning events and USAGE_LIMIT_EXCEEDED; TIER_3 unlimited; thread-safe |
| `BillingService` | start_trial, subscribe, cancel, expire_trial, renew; `check_feature()` gate (commercial only); `get_available_features()`; thread-safe |
| `OnboardingService` | Idempotent `complete_step()`; emits `ONBOARDING_COMPLETED` on funnel completion; thread-safe |
| `build_market_readiness_report()` | Evaluates all 11 Section 23 gates; returns signed `MarketReadinessReport`; `live_trading_authorized` always False |

### Unit-economics service (`services/billing/unit_economics.py`)

| Class | Responsibility |
|---|---|
| `UnitEconomicsService` | `snapshot()` produces hashed `UnitEconomicsDashboard`; computes per-tier MRR, ARR, conversions, churn; retains snapshot history for audit |

---

## Quality Gate Results

| Gate | Result |
|---|---|
| `ruff check` (4 files) | ✅ All checks passed |
| `ruff format --check` (4 files) | ✅ All files formatted |
| `mypy` (4 files) | ✅ No issues found |
| `pytest tests/test_e10_billing.py` | ✅ **80 passed** in 0.57s |
| `pytest` (full suite) | ✅ **1789 passed**, 12 skipped in ~15s |
| `lint-imports` | ✅ 3 contracts KEPT, 0 broken (leaf invariant holds) |
| Secret scan | ✅ 0 findings |

---

## Acceptance Criteria Status

| Criterion | Status |
|---|---|
| Four tiers enforceable in simulation (FREE_TRIAL + T1/T2/T3) | ✅ `BillingService` + `test_e10_billing.py` |
| Annual pricing applies ANNUAL_DISCOUNT_RATE (16.67% default) | ✅ `test_tier1_annual_total_applies_discount`, `test_tier3_annual_total_applies_discount` |
| Usage metering accurate: ORDERS, LLM_TOKENS, MARKET_DATA, COMPUTE_SEC | ✅ `UsageMeteringService.record()` + 4 dimension tests |
| 80% usage warning event emitted | ✅ `test_record_usage_warning_at_80_percent` |
| Hard limit raises `UsageLimitExceededError`; TIER_3 never raises | ✅ `test_record_usage_raises_on_hard_limit_exceeded`, `test_tier3_unlimited_never_raises_on_large_usage` |
| Billing events audited with SHA-256 hash chain | ✅ `test_billing_event_log_verify_chain_passes_on_intact_log`, `test_billing_event_log_verify_chain_fails_on_tampered_event` |
| Tier enforcement does NOT weaken safety invariants | ✅ `test_safety_features_not_in_tier_feature_map`, `test_billing_service_check_feature_only_gates_commercial_features` |
| `live_trading_authorized` always False | ✅ `test_market_readiness_report_live_trading_authorized_is_always_false`, `test_market_readiness_report_cannot_be_created_with_live_authorized_true` |
| `owner_sign_off_required` always True | ✅ `test_market_readiness_report_owner_sign_off_always_required` |
| All 11 Section 23 gates covered in report | ✅ `test_market_readiness_report_covers_all_gates` |
| Tampered billing event chain causes FAIL gate | ✅ `test_market_readiness_report_chain_tamper_causes_fail_gate` |
| Commercial onboarding flow complete with ONBOARDING_COMPLETED event | ✅ `test_onboarding_completes_when_required_steps_done` |
| Unit-economics dashboard snapshot has SHA-256 hash | ✅ `test_unit_economics_snapshot_hash_is_set` |
| MRR correctly sums active subscriptions; cancelled excluded | ✅ `test_unit_economics_snapshot_mrr_sums_active_tiers`, `test_unit_economics_cancelled_tenant_excluded_from_mrr` |
| Trial conversions counted from TIER_CHANGED events | ✅ `test_unit_economics_trial_conversions_counted` |
| `pwa_path_requires_apple_license` always False | ✅ `test_apple_platform_decision_pwa_path_never_requires_license` |
| Apple Developer Program Tauri path recordable (OD-8 documented) | ✅ `test_apple_platform_decision_tauri_distribution_recordable` |
| Zero new ruff/mypy errors | ✅ Confirmed |
| Full test suite green | ✅ 1789 passed |

---

## Open Owner Decisions Recorded

The following items remain pending explicit owner sign-off before paid live
activation.  They are recorded as PENDING_OWNER gates in the
`MarketReadinessReport` and in `status.yaml`:

| ID | Decision |
|---|---|
| OD-7 | Confirm exact annual discount rate (default 16.67% set in `ANNUAL_DISCOUNT_RATE`) |
| OD-8 | Confirm Apple Developer Program license usage decision (documented in `ApplePlatformDecision`) |
| OPEN-08 | Legal classification and commercial-release eligibility (counsel sign-off required before paid live feature) |
| OPEN-02 | Cloud provider and region final selection |
| OPEN-03 | Durable event-bus provider final selection |

---

## Apple Developer Program Decision (OD-8)

Per E10 scope, the decision is documented in `ApplePlatformDecision` contract:

- **PWA path (iPhone):** Does NOT require Apple Developer Program for basic
  iPhone access. `pwa_path_requires_apple_license` is invariant False.
- **Tauri macOS / Mac App Store:** Requires Apple Developer Program ($99/year)
  if App Store distribution is chosen. This is owner-selectable and supported
  by the `ApplePlatformDecision` contract.
- **Recommendation:** Use PWA for initial iPhone access (no additional
  licensing cost). Mac App Store distribution via Tauri requires ADP enrollment
  and owner sign-off before activating.

---

## Fixes Applied in This Phase

| File | Change |
|---|---|
| `tests/test_e0_consistency.py` | `test_e1_through_e10_planned` → `test_e1_through_e10_exist_with_known_status`; pre-existing failure from E9 (E8/E9 marked COMPLETE but test still required PLANNED) fixed |
| `pyproject.toml` | Version 0.10.0 → 0.19.0 (synchronized with status.yaml; pre-existing drift) |
| `services/core/version.py` | `__version__` 0.10.0 → 0.19.0 (synchronized with status.yaml) |

---

## Remote Verification

```
Branch:  phase/e10-commercial-monetization
Remote:  origin/phase/e10-commercial-monetization  ← matched on push
CI:      triggered on push (branch matches phase/* pattern in ci.yml)
```

---

## Hard Stop

Phase E10 is complete. All elevation phases E0 through E10 of the KIAN
TRADING INTELLIGENCE MASTER ENGINEERING DIRECTIVE V1.2 are now COMPLETE.

**NEXT PHASE NOT AUTHORIZED.**

The project is ready for initial sellable version under the defined tiers
(simulation/paper only). Live trading activation requires a separate written
owner decision per AD-034 and Section 00.4 of DIRECTIV.txt.
