# Phase B — Operational Locked Ideas: Evidence

## DIRECTIV.txt V1.4 — Phase B: Operational Locked Ideas

**Date:** 2026-10-16
**Directive:** DIRECTIV.txt V1.4, Section 01 — Phase B: Operational Locked Ideas
**Status:** COMPLETE
**Branch:** `phase/b-operational-locked-ideas`
**Commit (pre-evidence):** `9f22ed7`

## Scope Items

Per DIRECTIV.txt V1.4 Phase B: three ideas fully implemented with real service
code, integration tests, and connection to the runtime.

### Item 1 — Token Budget Governor + Accurate Metering

**Contracts:** `packages/contracts/phase_b.py`
- `DegradationLevel` (StrEnum): NONE, LIGHT, MODERATE, SEVERE
- `TenantBudgetConfig` (frozen dataclass): per-tenant limits for LLM tokens,
  compute seconds, orders, plus burst allowance. Validates all fields.
- `MeteringSnapshot` (frozen dataclass): point-in-time usage across all
  dimensions with degradation level and timezone-aware UTC timestamp.
- `MeteringResult` (frozen dataclass): consumption result — accepted/degraded
  flag, degradation level, remaining budget, human-readable detail.

**Service:** `services/phase_b/__init__.py` → `TokenBudgetMeter`
- Multi-dimension metering: LLM tokens, compute seconds, orders.
- Per-tenant budget isolation — no cross-tenant leakage.
- Graceful degradation thresholds:
  - LIGHT at 80% of budget consumed
  - MODERATE at 95%
  - SEVERE at 100% (hard limit + burst exhausted)
- Thread-safe (threading.Lock).
- Daily counter reset after 24h.
- `can_consume()` pre-check without side effects.
- `snapshot()` returns full `MeteringSnapshot` for audit.
- `get_records()` returns persisted `MeteringRecord` list.
- Integrates with existing `LLMGateway` — tracks `response.tokens_used`.

**Integration tests (16):**
- `test_consume_within_budget_accepted`
- `test_consume_llm_tokens_only`
- `test_consume_orders_only`
- `test_consume_compute_seconds_only`
- `test_llm_token_budget_exceeded_degrades_gracefully`
- `test_compute_budget_exceeded_degrades_gracefully`
- `test_orders_budget_exceeded_degrades_gracefully`
- `test_light_degradation_at_80_percent`
- `test_moderate_degradation_at_95_percent`
- `test_severe_degradation_at_100_percent`
- `test_can_consume_check`
- `test_per_tenant_isolation`
- `test_snapshot_captures_all_dimensions`
- `test_metering_records_are_persisted`
- `test_budget_config_validation`
- `test_default_config_used_when_not_configured`
- `test_multi_consume_accumulates`

**LLM gateway integration tests (2):**
- `test_meter_wraps_llm_gateway_consumption`
- `test_meter_degradation_affects_llm_gateway`

### Item 2 — Decision Replay + Uncertainty Dossier for the Order Path

**Contracts:** `packages/contracts/phase_b.py`
- `OrderDecisionContext` (frozen dataclass): full order-path context —
  tenant_id, symbol, side, quantity, current_price, risk_authorized,
  risk_reason, execution_state. Validates all fields.
  - `to_hashable()` → JSON-serializable dict for context hashing.
- `OrderDecisionRecord` (frozen dataclass): replayable record combining
  context, action_taken, UncertaintyDossier, timestamp, and SHA-256
  record_hash (tamper-evident). Auto-computes hash on construction.

**Service:** `services/phase_b/__init__.py` → `OrderDecisionReplayService`
- `record_decision()`: records an order-path decision with context + dossier.
- `replay()`: finds a record by context hash (deterministic replay).
- `get_record()` / `get_all_records()` / `get_records_for_tenant()`: audit queries.
- `verify_integrity()`: checks all record hashes are intact (tamper-evidence).
- Thread-safe (threading.Lock).
- Integrates with existing `OrderIntent` and `OrderState` from the execution pipeline.
- Integrates with existing `UncertaintyDossier` from `contracts.locked_ideas`.

**Integration tests (11):**
- `test_record_and_replay_order_decision`
- `test_replay_no_match_returns_none`
- `test_decision_record_hash_is_tamper_evident`
- `test_decision_context_validation`
- `test_records_for_tenant_isolation`
- `test_get_record_by_id`
- `test_uncertainty_dossier_fields`
- `test_uncertainty_dossier_confidence_validation`
- `test_replay_determinism`
- `test_order_path_integration_with_execution`
- `test_decision_replay_does_not_bypass_risk_kernel` (safety)

### Item 3 — Schema-First Bus: Contract Validation of All Event Schemas

**Contracts:** `packages/contracts/phase_b.py`
- `EventSchemaType` (StrEnum): 13 event types covering all order, risk, ledger,
  and fill events that flow through the Redis Streams event bus.
- `EventSchema` (frozen dataclass): schema_type, version, JSON schema dict.
- `ValidationResult` (frozen dataclass): valid flag, schema_type, error list.
- `build_all_event_schemas()`: builds JSON schemas for all 13 event types.
- `compute_context_hash()`: SHA-256 for replay matching.
- Schema builders: `_order_schema`, `_risk_schema`, `_ledger_schema`, `_fill_schema`.
- JSON schema features used: type, required, properties, enum, const,
  minLength, minimum, additionalProperties.

**Service:** `services/phase_b/__init__.py` → `EventSchemaValidator`
- Validates events against registered JSON schemas.
- `validate()`: single event validation → `ValidationResult`.
- `validate_all()`: batch validation.
- `get_schema()` / `get_schemas()`: schema lookup.
- `validation_count` / `failure_count`: tracked metrics.
- Minimal JSON Schema validator (type, required, properties, enum, const,
  minLength, minimum, additionalProperties) — no external dependency.
- Integrates with `RedisStreamBus` via `StreamEvent` — events validated
  before being published to Redis Streams.

**Integration tests (18):**
- `test_all_event_types_have_schemas`
- `test_validate_valid_order_event`
- `test_validate_valid_risk_event`
- `test_validate_valid_ledger_event`
- `test_validate_valid_fill_event`
- `test_validate_missing_required_field`
- `test_validate_invalid_side_value`
- `test_validate_unknown_event_type`
- `test_validate_invalid_type_for_field`
- `test_validate_all_batch`
- `test_validation_count_and_failure_count`
- `test_all_event_types_count` (asserts 13 event types)
- `test_schema_versioning`
- `test_get_schema_for_known_type`
- `test_get_schema_for_unknown_type`
- `test_validate_all_event_types_pass`
- `test_validate_event_before_redis_publish`
- `test_invalid_event_rejected_before_redis_publish`
- `test_schema_validation_for_all_outbox_event_types`

### Safety Invariants

**Service:** `services/phase_b/__init__.py` → `verify_phase_b_safety_invariants()`
- `live_trading_authorized_is_false`: LOCKED_IDEAS_LIVE_TRADING_AUTHORIZED is False.
- `all_event_schemas_registered`: len(build_all_event_schemas()) == len(EventSchemaType).
- `degradation_levels_complete`: 4 degradation levels.
- `event_schema_types_complete`: 13 event schema types.

**Safety invariant tests (4):**
- `test_live_trading_not_authorized`
- `test_safety_invariants_verified`
- `test_degradation_does_not_authorize_live_trading`
- `test_decision_replay_does_not_bypass_risk_kernel`

## Acceptance Criteria

Per DIRECTIV.txt V1.4 Phase B:

- [x] **Each of the three items has real service code, integration tests,
      and connection to the runtime.**
  - Item 1: `TokenBudgetMeter` — 18 tests, integrates with `LLMGateway`.
  - Item 2: `OrderDecisionReplayService` — 11 tests, integrates with
    `OrderIntent`/`OrderState`/`UncertaintyDossier`.
  - Item 3: `EventSchemaValidator` — 19 tests, integrates with
    `RedisStreamBus`/`StreamEvent`.

- [x] **All safety invariants preserved.**
  - `LOCKED_IDEAS_LIVE_TRADING_AUTHORIZED` remains False.
  - Risk Kernel is never bypassed (decision replay records, not overrides).
  - Per-tenant isolation enforced in both meter and replay service.
  - 4 safety invariant tests pass.

- [x] **Evidence recorded in test-house/phase-b/evidence.md.**
  - This file.

- [x] **Full test suite green, commit pushed, hard stop.**
  - 1958 passed, 9 skipped (1906 pre-existing + 52 new Phase B tests).
  - ruff clean, mypy clean on Phase B files.
  - Commit and push below.

## Test Execution Output

```
Phase B tests:
tests/test_phase_b_integration.py — 52 passed in 0.36s

Full suite:
1958 passed, 9 skipped in 37.11s
```

## Files Created

- `packages/contracts/phase_b.py` — Phase B contracts (DegradationLevel,
  TenantBudgetConfig, MeteringSnapshot, MeteringResult, OrderDecisionContext,
  OrderDecisionRecord, EventSchemaType, EventSchema, ValidationResult,
  build_all_event_schemas, compute_context_hash).
- `services/phase_b/__init__.py` — Phase B services (TokenBudgetMeter,
  OrderDecisionReplayService, EventSchemaValidator,
  verify_phase_b_safety_invariants).
- `tests/test_phase_b_integration.py` — 52 integration tests (3 items + safety).
- `test-house/phase-b/evidence.md` — This evidence file.

## Files Modified

- `status.yaml` — Updated for Phase B completion (test count 1958, Phase B
  status COMPLETE, honest_labels updated).

## NEXT PHASE NOT AUTHORIZED.
