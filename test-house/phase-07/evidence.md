# Phase 07 — Mining Simulation and Safety — Evidence

## Run ID: PHASE-07-RUN-01

- **Date**: 2026-10-10T06:32:00Z (CEST, UTC+02:00)
- **Git SHA**: `f388b6de2749b7522254dd8f5ec0fd3aaf6df754` (pre-commit; SHA will update after commit)
- **Branch**: `phase/07-mining-simulation`
- **Environment**: macOS 26.5.2, Python 3.11.15, pytest 9.1.1, ruff, mypy --strict

## Deliverables (10/10)

1. **Mining simulator** — `services/mining/simulator.py`
   - `MiningSimulator` class: thread-safe, deterministic simulation
   - `run_simulation()`: hash rate × network difficulty → expected blocks → gross revenue → pool fees → net revenue → electricity cost → depreciation → net profit
   - `MiningSimulationResult`: gross/net revenue (BTC), electricity cost, depreciation, net profit (fiat), break-even BTC price, efficiency (J/TH), uncertainty range (±15%), `is_simulation=True`
   - Emergency stop blocks all simulation; LIVE mode rejected with `PermissionError`
2. **Hash-rate and reward models** — `packages/contracts/mining.py`
   - `HashRate` (frozen, unit-aware, H/s conversion), `HashRateUnit` (6 units)
   - `NetworkDifficulty` (frozen, positive), `BlockReward` (frozen, positive)
   - `EquipmentSpec` (frozen): name, hash rate, power consumption, cost, useful life, salvage value, temp bounds, efficiency (`efficiency_j_per_th`)
3. **Electricity cost model** — `ElectricityConfig`
   - `rate_per_kwh`, `currency`, `daily_cost(power_w, uptime_pct)`, `monthly_cost()`
   - Validates non-negative rate, non-empty currency, uptime 0–100
4. **Depreciation model** — `DepreciationConfig`
   - Straight-line: `monthly_depreciation = (cost - salvage) / life`, `daily_depreciation`
   - `from_equipment()` factory; validates salvage ≤ cost, life > 0
5. **Pool interfaces** — `PoolConfig`, `PoolAdapterProtocol`, `SimulatedPoolAdapter`
   - `PoolConfig`: name, URL, fee_pct (0–100), payout scheme (PPS/PPLNS/PROP/SOLO), min_payout
   - `SimulatedPoolAdapter`: authorize, submit_share, add_rewards (fee-deducted), get_pending_rewards, request_payout (min_payout gate), total_paid, share_count, `is_simulation=True`
6. **Hardware telemetry** — `TelemetryReading`, `TelemetryHistory`
   - `TelemetryReading`: reading_id, equipment_id, timestamp (UTC), temperature_c, hash_rate, power_w, fan_speed_rpm, status
   - `TelemetryHistory`: add, count, latest, avg_temperature, max_temperature, avg_hash_rate
   - `MiningSimulator.generate_telemetry()`: deterministic temperature model, throttle/shutdown handling, status assignment
7. **Temperature policies** — `TemperaturePolicy`, `TemperatureAction`
   - `evaluate(temp)`: NONE / ALERT / THROTTLE / SHUTDOWN based on thresholds
   - `is_safe()`, `is_violation()`, `from_equipment()`; validates threshold ordering
8. **Mining financial integration** — `MiningFinancialEntry`
   - Distinguishes mining from trading: `is_mining = True`, `entry_type = "mining_daily_revenue"`
   - `from_result()` factory; UTC timestamp validated
9. **Failure simulation** — `FailureEvent`, `FailureType`
   - `FailureType`: OVERHEAT, HASHBOARD_FAILURE, POWER_SUPPLY_FAILURE, NETWORK_OUTAGE, COOLING_FAILURE, FAN_FAILURE, UNKNOWN
   - `FailureEvent`: create, resolve, duration, duration_seconds; UTC timestamps validated
   - `MiningSimulator.inject_failure()`, `resolve_failure()`
10. **Controlled adapter interfaces** — `HardwareAuthorization`, `HardwareAdapterProtocol`, `MiningSafetyState`, `MiningSafetyLimits`, `MiningOperationStatus`
    - `MiningSafetyState`: emergency_stop_active, physical_operations_authorized, active_failures, `is_safe` (blocks on emergency stop or overheat)
    - `authorize_physical_operations()` blocked by emergency stop; `clear_emergency_stop()` requires authorized_by
    - `MiningSafetyLimits`: max_temperature, max_power, min_hash_rate, max_downtime; `check_all()`
    - `HardwareAuthorization`: authorized, authorized_by, authorized_at, expires_at, scope, `is_active`, `is_expired`

## Architecture Decisions

- **AD-015**: Mining simulation and integration — simulation only, no real hardware/pool without explicit approval
- **AD-023**: Digital twin — deterministic simulation, fault injection, repeatable verification
- **AD-013**: Enforce hard limits — emergency stop, safety limits, temperature policies

## Bug Fixes

### 1. Mypy comparison-overlap on MiningOperationStatus enum

**Root cause**: `tests/test_mining_contracts.py` compared `MiningOperationStatus.SIMULATION_ONLY == "simulation_only"` etc. Mypy narrows the enum literal to its specific variant type, making the comparison with a string literal non-overlapping.

**Fix**: Changed to `.value` comparison:
```python
assert MiningOperationStatus.SIMULATION_ONLY.value == "simulation_only"
```

### 2. Decimal precision loss in uncertainty range test

**Root cause**: `test_simulation_calculates_uncertainty_range` computed `spread = (high - low) / (2 * profit)` and asserted `== Decimal("0.15")`. The subtraction `high - low` introduces floating-point-like precision loss in Decimal arithmetic (the intermediate multiplication/division introduces extra digits that don't cancel exactly).

**Fix**: Verify each bound independently instead of computing the spread:
```python
expected_low = result.daily_net_profit * Decimal("0.85")
expected_high = result.daily_net_profit * Decimal("1.15")
assert low == expected_low
assert high == expected_high
```

## Files

- `packages/contracts/mining.py` — All mining contracts (10 deliverables)
- `services/mining/__init__.py` — Service package init
- `services/mining/simulator.py` — MiningSimulator service
- `tests/test_mining_contracts.py` — 138 tests covering all deliverables
- `packages/contracts/__init__.py` — Updated with mining exports
- `pyproject.toml` — Registered `services.mining` package

## Quality Gates

| Gate | Command | Result |
|------|---------|--------|
| ruff format | `ruff format --check services/ packages/ tests/` | PASS (82 files) |
| ruff check | `ruff check services/ packages/ tests/` | PASS (All checks passed) |
| mypy --strict | `mypy services/ packages/ tests/` | PASS (0 errors, 82 files) |
| pytest | `pytest -v` | PASS (769/769: 631 existing + 138 new mining) |
| tsc | `npx tsc --noEmit` | PASS |
| eslint | `npm run lint` | PASS |
| vitest | `npm test -- --run` | PASS (29/29) |
| secret scan | `pytest tests/test_secret_scan.py -v` | PASS (0 findings) |

## Test Breakdown (138 new tests)

| Test Class | Tests | Deliverable |
|-----------|-------|-------------|
| TestMiningSimulator | 13 | D1: Mining simulator |
| TestHashRateModel | 11 | D2: Hash rate model |
| TestNetworkDifficulty | 4 | D2: Network difficulty |
| TestBlockReward | 4 | D2: Block reward |
| TestEquipmentSpec | 10 | D2: Equipment spec |
| TestElectricityCost | 12 | D3: Electricity cost |
| TestDepreciation | 8 | D4: Depreciation |
| TestPoolConfig | 8 | D5: Pool config |
| TestSimulatedPoolAdapter | 9 | D5: Pool adapter |
| TestTelemetry | 8 | D6: Hardware telemetry |
| TestTemperaturePolicy | 12 | D7: Temperature policies |
| TestMiningFinancialIntegration | 3 | D8: Mining financial integration |
| TestFailureSimulation | 10 | D9: Failure simulation |
| TestControlledAdapters | 17 | D10: Controlled adapters |
| TestMiningSessionConfig | 5 | Cross-cutting: session config |
| TestPhysicalOperationsNotActivated | 4 | Safety: physical ops not activated |

## Safety Invariants

- `is_simulation = True` on all results and adapters — never represents real hardware
- Emergency stop blocks all new simulation runs
- LIVE mode rejected with `PermissionError`
- Physical operations authorization blocked by emergency stop
- `MiningSafetyState.is_safe` returns `False` when emergency stop active or overheat failure present
- No real mining, no real pool connection, no physical hardware activation
