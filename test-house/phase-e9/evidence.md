# Phase E9 — Graduated Autonomy, Kill Plane and Compliance Package

**Branch:** `phase/e9-graduated-autonomy-kill-plane-compliance`
**Commit:** `3ac5a325d2777b5136290a09a5f07ff9957b1f15`
**Date:** 2025-07-10
**AD Refs:** AD-038 (Graduated Autonomy and Independent Kill Plane)

---

## Scope

Phase E9 delivers the graduated autonomy trust-level engine, independent kill
plane, operator cockpit, human-factors review tracking, and the full compliance
package builder for Kian Trading Intelligence. All work landed in a single
commit on top of the phase/e8-evidence-observability-supply-chain tree; no
Phase E10 work was performed.

**Completing E9 does NOT authorize live trading.**

---

## Deliverables

### Contracts (`packages/contracts/autonomy.py`)

| Contract | Purpose |
|---|---|
| `TrustLevel` | IntEnum L0 (observe) → L5 (higher-cap live) per AD-038 |
| `TrustLevelApproval` / `TrustLevelApprovalId` | Signed human approval for trust-level promotion; invariant: `to_level > from_level` |
| `TrustLevelEvent` | Append-only audit trail entry for every trust-level change |
| `TrustLevelChangeReason` | Reason categories (signed promotion, automatic/manual demotion, system reset, emergency halt) |
| `KillPlaneCommand` / `KillPlaneCommandId` | Hashed command issued to the kill plane (platform / tenant / agent / symbol scope) |
| `KillPlaneResult` | Result of a kill-plane activation (orders cancelled, new exposure blocked) |
| `KillPlaneStatus` | ARMED → DRAINING → HALTED state machine |
| `KillPlaneScope` | platform / tenant / agent / symbol |
| `DangerousActionCategory` | Categories requiring human-factors review |
| `HumanFactorsReview` / `HumanFactorsReviewId` | Hashed review record for dangerous actions |
| `OperatorCockpitSnapshot` | Point-in-time cockpit snapshot (platform mode, kill plane status, trust levels, open orders, alerts) |
| `ComplianceDocument` / `ComplianceDocumentId` | Compliance package document record with hash |
| `ComplianceDocumentType` | Legal classification memo, data inventory, DPIA, market-data terms, penetration test report, platform ADR, runbook, tabletop drill |
| `DataInventoryItem` | DPIA data inventory item; cross_tenant invariant always False |
| `MarketDataTermsEntry` | Market-data terms register entry |
| `E9DrillRecord` / `E9DrillRecordId` | Tabletop and live drill record with hash |
| `DrillType` / `DrillOutcome` | Drill type (tabletop, live, kill_plane, runbook) and outcome categories |
| `E9OwnerReviewPackage` | Complete owner review package; live_trading_authorized invariant always False |
| `TrustLevelPromotionDeniedError` / `KillPlaneAlreadyTriggeredError` / `KillPlaneNotArmedError` | Domain exceptions |
| `compute_approval_hash` / `compute_event_hash` | SHA-256 utility helpers |

### Service (`services/autonomy/__init__.py`)

| Class | Responsibility |
|---|---|
| `TrustLevelEngine` | HMAC-SHA256 signed promotion approvals; automatic / manual demotion never requires approval; `reset_all()` on emergency halt; append-only audit trail; thread-safe |
| `KillPlane` | ARMED → DRAINING → HALTED; `trigger(scope, scope_value, ...)` cancels matching open orders and blocks new exposure; `rearm()` only from HALTED; `out_of_band=True` flag for when main platform is down; full command + result history; thread-safe |
| `HumanFactorsTracker` | Records human-factors reviews for dangerous actions; `pending_approvals_required()` gate; thread-safe |
| `OperatorCockpit` | Captures point-in-time cockpit snapshots aggregating trust-engine + kill-plane state; all snapshots retained for audit; thread-safe |
| `CompliancePackageBuilder` | `add_document()`, `add_data_inventory_item()`, `add_market_data_terms()`, `start_drill()`, `complete_drill()`; `build_owner_review_package()` assembles the complete E9 owner review package with hash; thread-safe |

---

## Quality Gate Results

| Gate | Result |
|---|---|
| `ruff check contracts/autonomy.py services/autonomy/__init__.py tests/test_e9_autonomy.py` | ✅ All checks passed |
| `ruff format --check` (3 files) | ✅ 3 files already formatted |
| `mypy packages/ services/autonomy/ tests/test_e9_autonomy.py` | ✅ No issues found in 30 source files |
| `pytest tests/test_e9_autonomy.py` | ✅ 63 passed in 0.48s |
| `pytest` (full suite) | ✅ 1709 passed, 12 skipped in 15.71s |

---

## Acceptance Criteria Status

| Criterion | Status |
|---|---|
| Kill-plane cancels orders with main platform down (`out_of_band=True`) | ✅ `test_out_of_band_flag` + `test_platform_scope_cancels_all_orders` |
| Kill-plane cancels all orders (platform scope) | ✅ `test_platform_scope_cancels_all_orders` — 3 orders cancelled |
| Kill-plane tenant scope cancels only tenant orders | ✅ `test_tenant_scope_cancels_only_tenant_orders` |
| Kill-plane symbol scope cancels only symbol orders | ✅ `test_symbol_scope_cancels_only_symbol_orders` |
| Kill-plane new exposure blocked after trigger | ✅ `result.new_exposure_blocked is True` across all trigger tests |
| Trust-level promotion requires signed approval | ✅ `test_promotion_rejected_bad_signature` — tampered sig raises `TrustLevelPromotionDeniedError` |
| Automatic demotion requires no approval | ✅ `test_automatic_demotion_to_l0` |
| `live_trading_authorized` invariant is always False | ✅ `test_package_live_trading_authorized_is_false` + `test_package_cannot_be_created_with_live_authorized_true` |
| `cross_tenant` data inventory invariant always False | ✅ `test_cross_tenant_raises` |
| Owner review package hash is set | ✅ `test_package_hash_is_set` |
| Owner review package contains all components | ✅ `test_package_contains_all_components` |
| Zero new ruff/mypy errors | ✅ Confirmed |
| Full test suite green | ✅ 1709 passed |

---

## Fixes Applied in This Session

| File | Location | Error | Fix |
|---|---|---|---|
| `services/autonomy/__init__.py` | Import | `F401` — `timedelta` unused | Removed unused import |
| `services/autonomy/__init__.py` | Import | `F401` — `TrustLevelDemotedError` unused | Removed unused import |
| `services/autonomy/__init__.py` | Multiple methods | `PLR0913/PLR0917` — too many positional args | Added `*` keyword-only separator + `# noqa: PLR0913` (same pattern as E8 evidence service) |
| `services/autonomy/__init__.py` | `trigger()` | `SIM114` — combine if branches | Replaced if/elif chain with single boolean expression |
| `tests/test_e9_autonomy.py` | Multiple imports | `F401` — unused imports (`HumanFactorsReview`, `KillPlaneAlreadyTriggeredError`, `TrustLevelError`) | Removed stale imports; added `KillPlaneNotArmedError` |
| `tests/test_e9_autonomy.py` | Line ~597 | `E501` — line too long | Refactored `__import__` inline to explicit local import |
| `tests/test_e9_autonomy.py` | `test_already_triggered_raises` | Test expectation mismatch | Kill plane goes ARMED→DRAINING→HALTED (not TRIGGERED); test updated to expect `KillPlaneNotArmedError` |
| `packages/contracts/autonomy.py` / `services/autonomy/__init__.py` | Formatting | `ruff format` style | Auto-formatted with `ruff format` |

---

## Remote Verification

```
Branch:  phase/e9-graduated-autonomy-kill-plane-compliance
SHA:     3ac5a325d2777b5136290a09a5f07ff9957b1f15
Remote:  origin/phase/e9-graduated-autonomy-kill-plane-compliance  ← matched
CI:      triggered on push (branch matches phase/* pattern in ci.yml)
```

---

## Hard Stop

Phase E9 is complete. **NEXT PHASE NOT AUTHORIZED.**
