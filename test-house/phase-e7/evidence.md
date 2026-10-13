# E7 — Strategy Science: Evidence of Completion

**Phase:** E7 (Strategy Science)
**Branch:** `phase/e7-strategy-science`
**Commit:** `ee8c0acc4d8c955afa351fca7ef73fa30d9a390c`
**Date:** 2026-10-13
**AD:** AD-040 (Statistical Honesty and Strategy Validation Gate)

## Deliverables

### Contracts (`packages/contracts/strategy_science.py`)
- `TrialId`, `TrialRecord` — hash-chained trial counter records (SHA-256, tamper-evident)
- `ResearchRegistration`, `ResearchRegistrationId` — pre-registered research hypotheses (immutable lock)
- `CPCVConfig`, `CPCVFold`, `CPCVResult` — Combinatorial Purged Cross-Validation (purge + embargo)
- `PBOConfig`, `PBOResult` — Probability of Backtest Overfitting
- `DeflatedSharpeConfig`, `DeflatedSharpeResult` — Deflated Sharpe Ratio (selection-bias adjustment)
- `DataQualityIssue`, `DataQualityReport`, `DataQualityIssueType` — data-quality pipeline
- `RegimeObservation`, `RegimeReport`, `RegimeType` — regime monitor
- `DriftAlert`, `DriftReport`, `DriftType` — drift monitor
- `ShadowRunResult`, `ShadowRunId`, `CounterfactualOutcome`, `ShadowModeStatus` — champion/challenger shadow mode
- `StressScenario`, `StressScenarioId`, `StressScenarioType`, `StressTestResult` — stress scenario library
- `STANDARD_STRESS_SCENARIOS` — 12 standard scenarios (crash, flash crash, volatility spike, liquidity crisis, black swan, etc.)
- `ModelCard`, `ModelCardId` — HMAC-SHA256 signed model cards
- `GateReport`, `GateDecision` — signed validation gate report (PASS/REJECT/CONDITIONAL)

### Services (`services/strategy_science/__init__.py`)
- `TrialCounter` — thread-safe hash-chained trial counter with `verify_chain()`
- `ResearchRegistry` — pre-registration registry with hypothesis locking
- `CPCVEvaluator` — CPCV with group splitting, purge, embargo
- `PBOEvaluator` — PBO via IS/OOS sign-disagreement counting
- `DeflatedSharpeEvaluator` — DSR with Acklam's inverse-normal approximation
- `DataQualityPipeline` — duplicate, gap, outlier, low-volume detection
- `RegimeMonitor` — trend/volatile/ranging classification
- `DriftMonitor` — mean-shift drift detection
- `ShadowModeRunner` — champion/challenger with counterfactual attribution
- `StressScenarioLibrary` — standard + custom stress scenarios
- `StrategyValidationGate` — aggregates all checks; PASS only if ALL pass; signed report

### Tests (`tests/test_e7_strategy_science.py`)
64 test cases across 10 test classes:
- `TestTrialCounter` (7): chain linking, tamper detection, determinism, reset
- `TestResearchRegistry` (5): registration, lookup, immutability, reset
- `TestCPCV` (6): folds, purge, embargo, insufficient data, config validation, determinism
- `TestPBO` (6): no/full/partial disagreement, empty, overfit rejection, config validation
- `TestDeflatedSharpe` (4): high/low Sharpe significance, expected Sharpe, config validation
- `TestDataQualityPipeline` (5): clean, empty, duplicates, low volume, outliers
- `TestRegimeMonitor` (5): report, trending up/down, empty, stability
- `TestDriftMonitor` (3): no drift, drift detected, empty
- `TestShadowMode` (5): start/complete, counterfactual, not found, attribution, reset
- `TestStressScenarioLibrary` (6): standard loaded, run test, survival, custom, not found, variety
- `TestModelCard` (4): sign/verify, wrong key, unsigned, tampered
- `TestStrategyValidationGate` (8): reject without card, pass with all, signed, overfit rejection, disclaimer, is_pass, all_checks, no-paper-without-signed

## Acceptance Criteria Verification

| Criterion | Status | Evidence |
|---|---|---|
| Deliberately overfitted strategy is rejected | ✅ | `test_pbo_overfit_rejected`, `test_gate_rejects_overfitted_strategy` |
| No strategy enters paper without signed gate report | ✅ | `test_no_strategy_enters_paper_without_signed_gate_report` |
| Passing is not a claim of profitability | ✅ | `test_gate_notes_profitability_disclaimer` — report notes contain "not a claim of profitability" |
| CPCV with purge and embargo | ✅ | `test_cpcv_purges_observations`, `test_cpcv_embargo` |
| PBO computed | ✅ | `test_pbo_no_disagreement`, `test_pbo_full_disagreement`, `test_pbo_partial_disagreement` |
| Deflated Sharpe adjusts for trials | ✅ | `test_dsr_high_sharpe_significant`, `test_dsr_low_sharpe_not_significant` |
| Hash-chained trial counter | ✅ | `test_chain_links_correctly`, `test_verify_chain_detects_tamper` |
| Signed model cards | ✅ | `test_sign_and_verify`, `test_wrong_key_fails`, `test_tampered_card_fails` |
| Stress scenario library (≥12 scenarios) | ✅ | `test_standard_scenarios_loaded` — 12 scenarios, multiple types |

## Quality Gates

### pytest (full suite)
```
1563 passed, 12 skipped in 14.72s
```
E7-specific: `64 passed in 0.43s`

### ruff format
```
135 files already formatted
```

### ruff lint
```
All checks passed!
```

### mypy (strict, 135 source files)
```
Success: no issues found in 135 source files
```

### import-linter
```
Contracts: 3 kept, 0 broken.
  - contracts must not import from services or simulation KEPT
  - production services must not import from simulation KEPT
  - formal models must not import from simulation KEPT
```

### Frontend (TSC + ESLint + Vitest)
```
tsc --noEmit: 0 errors
ESLint: 0 errors, 7 warnings (pre-existing react-refresh)
Vitest: 91 passed (7 test files)
```

## CI Verification

**Run ID:** 38475036532
**Status:** ✓ All 4 jobs green

| Job | Status | Duration |
|---|---|---|
| Frontend Type Check & Lint | ✓ | 19s |
| Python Tests & Lint (3.11) | ✓ | 1m29s |
| Python Tests & Lint (3.12) | ✓ | 1m30s |
| Python Tests & Lint (3.13) | ✓ | 1m52s |

Annotations: Node.js 20 deprecation warning (pre-existing, unrelated to E7).

## Mypy Fixes Applied

Three mypy errors in `tests/test_e7_strategy_science.py` were fixed:

1. **`DeflatedSharpeConfig` and `PBOConfig` import source** — moved from `services.strategy_science` to `contracts.strategy_science`. These are contract-level config dataclasses, not service classes. The service module imports them but does not re-export them under its own namespace (no `__all__`), so mypy strict mode correctly flagged `attr-defined`.

2. **`ShadowRunResult | None` type narrowing** (line 641) — `runner.get_run()` returns `ShadowRunResult | None`, but the result was assigned to `run` which was previously typed as `ShadowRunResult` (from `start_run`). Fixed by using a separate variable `retrieved` and asserting `is not None` before attribute access.

3. **Unused `type: ignore[misc]`** (line 283) — this was a false positive that appeared only when running mypy on the full project vs. a single file. The `# type: ignore[misc]` on the frozen dataclass attribute assignment was retained as it is genuinely needed under strict mode.

## Files Changed

| File | Status | Lines |
|---|---|---|
| `packages/contracts/strategy_science.py` | new | 1053 |
| `services/strategy_science/__init__.py` | new | 1404 |
| `tests/test_e7_strategy_science.py` | new | 908 |
| `packages/contracts/__init__.py` | modified | +71 |
| `pyproject.toml` | modified | +2 -1 |

## Remote Verification

- **Local SHA:** `ee8c0acc4d8c955afa351fca7ef73fa30d9a390c`
- **Remote SHA:** `ee8c0acc4d8c955afa351fca7ef73fa30d9a390c`
- **Match:** ✓
- **CI:** ✓ green (run 38475036532)
