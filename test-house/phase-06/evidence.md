# Phase 06 — Four-Agent Intelligence — Evidence

## Run ID: PHASE-06-RUN-01

- **Date**: 2026-10-10T06:15:00Z (CEST, UTC+02:00)
- **Git SHA**: `e7922865a159bf4ee196f293699af0deb01409f9`
- **Branch**: `phase/06-four-agent-intelligence`
- **Environment**: macOS 26.5.2, Python 3.11.15, pytest 9.1.1, ruff, mypy --strict

## Deliverables (12/12)

1. **Four specialized agent contracts** — `packages/contracts/agents.py`
   - `AgentType` enum: MARKET_INTELLIGENCE, STRATEGY_PORTFOLIO, EXECUTION_SUPERVISOR, MINING_OPERATIONS
   - `AgentContext`, `AgentResult`, `AgentId`, `AgentPermission`, `DecisionTrace`, `DecisionTraceEntry`, `DecisionTraceId`
2. **Agent permission boundaries** — `AGENT_PERMISSIONS`, `AGENT_PROHIBITIONS` (frozensets, validated at construction)
3. **Deterministic orchestration** — `services/agents/orchestrator.py`
   - `AgentOrchestrator.run_trading_pipeline()`: Market → Strategy → Risk Kernel → Execution
   - `AgentOrchestrator.run_mining_pipeline()`: Mining Operations Agent
4. **Strategy versioning** — `packages/contracts/strategy.py`
   - `StrategyVersion`, `StrategyParameters` (frozen), `StrategyStatus` (9 states), `LEGAL_STRATEGY_TRANSITIONS`
5. **Backtesting** — `packages/contracts/validation.py::run_backtest()`
6. **Out-of-sample testing** — `packages/contracts/validation.py::run_out_of_sample()`
7. **Walk-forward validation** — `packages/contracts/validation.py::run_walk_forward()`
8. **Paper trading** — `packages/contracts/validation.py::run_paper_trading()`
9. **Validated ML interfaces** — `packages/contracts/llm_gateway.py`
10. **Limited LLM gateway** — `packages/contracts/llm_gateway.py::LLMGateway`
11. **Token budgets** — `TokenBudget`, `TokenBudgetConfig` (per-tenant, daily + per-request limits)
12. **Decision traceability** — `DecisionTrace`, `DecisionTraceEntry` (every step traced)

## Bug Fix: Strategy State Transition

**Root cause**: `StrategyPortfolioAgent.evaluate_strategy()` called
`strategy.transition_to(StrategyStatus.VALIDATED)` directly from DRAFT,
but `LEGAL_STRATEGY_TRANSITIONS` only allows DRAFT → BACKTESTING, not
DRAFT → VALIDATED. The legal path is:
DRAFT → BACKTESTING → OUT_OF_SAMPLE → WALK_FORWARD → PAPER_TRADING → VALIDATED.

Additionally, `test_orchestrator_emergency_stop_blocks_pipeline` passed
an already-VALIDATED strategy, and `transition_to(VALIDATED)` from VALIDATED
is also illegal (no self-transition).

**Fix**:
1. `_run_validation_stages()` now transitions the strategy through each
   intermediate state (BACKTESTING, OUT_OF_SAMPLE, WALK_FORWARD, PAPER_TRADING)
   at each stage, returning the final `StrategyVersion` in PAPER_TRADING state.
2. `evaluate_strategy()` promotes PAPER_TRADING → VALIDATED after all stages pass.
3. `evaluate_strategy()` handles already-VALIDATED or ACTIVE strategies by
   returning success without re-validation (idempotent).

**Files changed**:
- `services/agents/strategy_portfolio.py` — `_run_validation_stages()` returns
  `tuple[StrategyVersion | None, AgentResult | None]`; `evaluate_strategy()` handles
  already-validated strategies and uses the returned strategy for promotion.

## Quality Gates

| Gate | Command | Result |
|------|---------|--------|
| ruff format | `ruff format --check services/ packages/ tests/` | PASS (78 files, 0 changed) |
| ruff check | `ruff check services/ packages/ tests/` | PASS (All checks passed) |
| mypy --strict | `mypy services/ packages/ tests/` | PASS (0 issues, 78 files) |
| pytest | `pytest -v` | PASS (631/631) |
| secret scan | `pytest tests/test_secret_scan.py -v` | PASS (2/2) |
| tsc --noEmit | `npx tsc --noEmit` (apps/web) | PASS |
| eslint | `npm run lint` (apps/web) | PASS |
| vitest | `npm test -- --run` (apps/web) | PASS (29/29) |

## Architecture Decisions

AD-003, AD-004, AD-011, AD-012, AD-020, AD-022, AD-025

## Test Files

- `tests/test_agent_contracts.py`
- `tests/test_strategy_contracts.py`
- `tests/test_validation_contracts.py`
- `tests/test_llm_gateway.py`
- `tests/test_agent_services.py`
- `tests/test_agent_concurrency.py`

## Acceptance Criteria

- ✅ Agents cannot bypass risk controls (AD-004, tested in `test_orchestrator_emergency_stop_blocks_pipeline`)
- ✅ Strategy results are reproducible (AD-023, deterministic validation functions)
- ✅ Token limits are enforced (per-tenant daily + per-request caps in `TokenBudget.spend()`)
