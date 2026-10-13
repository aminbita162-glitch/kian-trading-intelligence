# E4 — Formal Models for Safety Plane Invariants

Per E4 (Safety Plane Hardening): formal models (TLA+/P) for order/session/
reservation/SAFE_HALT checked in CI. This directory contains the formal
specifications and the Python checker that validates the invariants
against the implementation.

## Models

### 1. Order State Machine (`OrderModel.tla`)

Invariant: order state transitions follow `LEGAL_ORDER_TRANSITIONS`.
Terminal states (FILLED, CANCELLED, REJECTED, EXPIRED) have no outgoing
transitions. No state transitions to CREATED.

### 2. Session State Machine (`SessionModel.tla`)

Invariant: session state transitions follow `LEGAL_SESSION_TRANSITIONS`.
SAFE_HALT can only transition to RECONCILING. COMPLETED and CANCELLED are
terminal.

### 3. Risk Reservation Lifecycle (`ReservationModel.tla`)

Invariant: a reservation transitions ACTIVE → {RELEASED, EXPIRED, CONSUMED}.
A CONSUMED reservation cannot be released. An EXPIRED reservation cannot
be consumed. A RELEASED reservation cannot be re-consumed.

### 4. SAFE_HALT Protocol (`SafeHaltModel.tla`)

Invariant: when emergency stop is active, no new exposure-increasing
(buy) orders are authorized. SAFE_HALT requires reconciliation before
resuming. The system does not auto-restart after SAFE_HALT — it requires
explicit human deactivation.

## CI Checking

The Python checker (`formal_checker.py`) validates that the
implementation's transition tables match the formal models' invariants.
It runs as a pytest test (`tests/test_e4_formal_models.py`).
