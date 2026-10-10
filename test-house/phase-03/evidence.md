# Test House — Phase 03 Evidence

## Market Data Foundation

| Run ID | Phase | Date (UTC) | Commit SHA | Branch | Component | Command | Expected | Observed | Status |
|--------|-------|------------|------------|--------|-----------|---------|----------|----------|--------|
| PH03-001 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Python format check | `ruff format --check services/ packages/ tests/` | 0 errors | 0 errors (44 files clean) | PASS |
| PH03-002 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Python lint | `ruff check services/ packages/ tests/` | 0 errors | All checks passed | PASS |
| PH03-003 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | mypy strict type check | `mypy services/ packages/ tests/` | 0 errors | Success: no issues found in 44 source files | PASS |
| PH03-004 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Python unit tests | `pytest -v` | 245 pass, 0 fail | 245 passed in 4.08s | PASS |
| PH03-005 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Secret scan | `pytest tests/test_secret_scan.py -v` | 0 findings | 2 passed (0 findings) | PASS |
| PH03-006 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Frontend type check | `npx tsc --noEmit` | 0 errors | 0 errors | PASS |
| PH03-007 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Frontend lint | `npm run lint` | 0 errors | 0 errors | PASS |
| PH03-008 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Frontend tests | `npm test -- --run` | 29 pass, 0 fail | 29 passed (3 test files) | PASS |

## Test Coverage Summary

### Mandatory Acceptance: Replay, Integrity, Stale-Data, and Recovery Tests

| Test Module | Tests | Coverage |
|-------------|-------|----------|
| test_market_data_contracts.py | 28 | Symbol parsing/validation, OrderBookLevel/Snapshot, Trade, Candle (OHLC), Ticker, MarketDataEvent, FreshnessConfig, EventId |
| test_simulated_provider.py | 22 | Provider connection lifecycle, ticker/orderbook/candles, determinism, rate limiting, reconnection with exponential backoff |
| test_market_data_services.py | 28 | HistoricalStorage (store/retrieve/dedup), EventProcessor (fresh/stale/duplicate/future/out-of-order), ReplayEngine (empty/populated/deterministic/symbol/time-range/speed), RecoveryScenario (survives reset, replay after disconnect, no dup on replay, processor recovery) |
| test_market_data_api.py | 14 | Market-data health, ticker/orderbook/candles endpoints, input validation (invalid symbol/timeframe/limit), OpenAPI schema |
| test_indicators.py | 14 | SMA/EMA/RSI/Volatility determinism + edge cases, CandleSeries (create/add/dedup/slice) |
| test_secret_scan.py | 2 | No secrets in repo, no .env files committed |

### New Tests Added (Phase 03): 118

- test_market_data_contracts.py: 28 tests
- test_simulated_provider.py: 22 tests
- test_market_data_services.py: 28 tests
- test_market_data_api.py: 14 tests
- test_indicators.py: 14 tests
- Frontend contracts: 12 new tests (total 29 with existing 17)

### Deliverables (11/11)

1. **Market-data contracts** — Symbol, OrderBookLevel, OrderBookSnapshot, Trade, Candle, Ticker, MarketDataEvent, FreshnessConfig, EventId (packages/contracts/market_data.py)
2. **Simulated data provider** — SimulatedProvider with connection lifecycle, deterministic data generation (services/market_data/)
3. **Provider adapter interfaces** — MarketDataProvider ABC with connect/disconnect/ticker/orderbook/candles (services/market_data/)
4. **Normalized events** — MarketDataEvent with event_id, timestamp, symbol, event_type, sequence
5. **Timestamp and freshness checks** — FreshnessConfig with max_age, warning_threshold; timezone-aware enforcement
6. **Duplicate handling** — EventProcessor rejects duplicate event_ids; HistoricalStorage deduplicates
7. **Historical storage** — HistoricalStorage with record_id assignment, symbol/type/time-range queries, clear
8. **Replay engine** — ReplayEngine with speed control, symbol/time-range filtering, deterministic ordering
9. **Deterministic indicators** — SMA, EMA, RSI, Volatility, CandleSeries (packages/contracts/indicators.py)
10. **Rate-limit handling** — RateLimiter with max_requests, remaining tracking, blocking on exceeded
11. **Reconnection behavior** — ReconnectionManager with max_attempts, exponential backoff, reset on success

### Market Data API Endpoints

- `GET /market-data/health` — Market data service health
- `GET /market-data/ticker/{symbol_pair}` — Current ticker for a symbol pair (uses :path converter for slash-containing pairs)
- `GET /market-data/orderbook/{symbol_pair}` — Order book snapshot with configurable depth
- `GET /market-data/candles/{symbol_pair}` — Historical candles with timeframe and limit

### Frontend Contracts Added (Phase 03)

- MarketDataEvent, MarketDataEventType, FreshnessStatus, TimeFrame
- Symbol, OrderBookLevel, OrderBookSnapshot, Trade, Candle, Ticker
- IndicatorResult, IndicatorType
- ReplayConfig, ProviderStatus

### Architecture Decisions Covered

- AD-003: Operating Mode (SIMULATION-only for Phase 03)
- AD-005: Market Data Abstraction (provider adapter interfaces)
- AD-017: Replay Engine (deterministic replay from historical storage)
- AD-021: Deterministic Indicators (SMA, EMA, RI, Volatility)
- AD-023: Rate Limit Handling (per-provider rate limiting)

### Security Findings

- F-SEC-01: Repository is PUBLIC (should be PRIVATE per Addendum A14) — flagged to owner, preserved per owner decision (same as Phase 02)
