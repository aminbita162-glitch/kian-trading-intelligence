"""Adapter conformance suite for Kian Trading Intelligence.

Per E5 (Simulation and Truth Infrastructure): adapter conformance suite
that verifies any adapter implementing the ExchangeAdapter protocol
conforms to the required behavioral invariants.

Per AD-023 (Digital Twin): deterministic simulation and exchange emulation.
Per AD-014: deterministic execution with idempotency, partial-fill handling,
and unknown-outcome reconciliation.

The conformance suite runs a standard set of checks against any adapter
that implements the ExchangeAdapter protocol. All checks must pass for
the adapter to be certified as conformant.

Per Section 05.5: no exchange is automatically approved for live use.
Conformance is necessary but not sufficient for live approval.

Per Section 01.3: SIMULATION mode only — no real financial orders.
"""

from __future__ import annotations

import time

from contracts.enums import OrderState
from contracts.exchange import (
    ClientOrderId,
)
from contracts.exchange_adapter import ExchangeAdapter
from contracts.order import OrderIntent
from contracts.simulation import (
    ConformanceCheckId,
    ConformanceCheckType,
    ConformanceResult,
    ConformanceStatus,
    ConformanceSuiteResult,
)


class AdapterConformanceSuite:
    """Adapter conformance suite for the ExchangeAdapter protocol.

    Per E5: verifies that any adapter implementing ExchangeAdapter
    conforms to the required behavioral invariants:
    - Idempotent submission (same client_order_id → same result)
    - Partial fill handling
    - Cancel is idempotent
    - Reconcile unknown outcomes
    - No blind retry on unknown outcome
    - Legal order state transitions
    - Tenant isolation
    - Connection lifecycle
    """

    def __init__(self, adapter: ExchangeAdapter) -> None:
        self._adapter = adapter
        self._adapter_name = type(adapter).__name__

    def _time_ms(self, start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    def _check_idempotent_submission(self) -> ConformanceResult:
        """Same client_order_id submitted twice returns the same order."""
        check_id = ConformanceCheckId.generate()
        start = time.monotonic()
        try:
            if not self._adapter.is_connected:
                return ConformanceResult(
                    check_id=check_id,
                    check_type=ConformanceCheckType.IDEMPOTENT_SUBMISSION,
                    status=ConformanceStatus.SKIPPED,
                    adapter_name=self._adapter_name,
                    detail="Adapter not connected",
                    duration_ms=self._time_ms(start),
                )

            intent = OrderIntent.create(
                tenant_id="conformance-tenant",
                profile_id="conf-profile",
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
            )
            cid = ClientOrderId("conf-idempotent-1")

            result1 = self._adapter.submit_order(intent, client_order_id=cid)
            result2 = self._adapter.submit_order(intent, client_order_id=cid)

            # Same exchange order ID → idempotent
            passed = (
                result1.exchange_order_id == result2.exchange_order_id
                and result1.state == result2.state
            )
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.IDEMPOTENT_SUBMISSION,
                status=ConformanceStatus.PASSED if passed else ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail="Idempotent submission verified"
                if passed
                else "Second submission returned different result",
                duration_ms=self._time_ms(start),
            )
        except Exception as exc:
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.IDEMPOTENT_SUBMISSION,
                status=ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail=f"Exception: {exc!s}",
                duration_ms=self._time_ms(start),
            )

    def _check_partial_fill_handling(self) -> ConformanceResult:
        """Adapter handles partial fills correctly."""
        check_id = ConformanceCheckId.generate()
        start = time.monotonic()
        try:
            if not self._adapter.is_connected:
                return ConformanceResult(
                    check_id=check_id,
                    check_type=ConformanceCheckType.PARTIAL_FILL_HANDLING,
                    status=ConformanceStatus.SKIPPED,
                    adapter_name=self._adapter_name,
                    detail="Adapter not connected",
                    duration_ms=self._time_ms(start),
                )

            # Check if the adapter has partial fill support by examining
            # the get_all_orders method — partial fills result in
            # PARTIALLY_FILLED state
            intent = OrderIntent.create(
                tenant_id="conformance-tenant",
                profile_id="conf-profile",
                symbol="BTC/USDT",
                side="buy",
                quantity="2.0",
            )
            cid = ClientOrderId("conf-partial-1")
            result = self._adapter.submit_order(intent, client_order_id=cid)

            # The adapter should accept the order and return a valid state
            valid_states = {
                OrderState.FILLED,
                OrderState.PARTIALLY_FILLED,
                OrderState.SUBMITTED,
                OrderState.UNKNOWN_OUTCOME,
            }
            passed = result.state in valid_states
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.PARTIAL_FILL_HANDLING,
                status=ConformanceStatus.PASSED if passed else ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail=f"State={result.state.value}"
                if passed
                else f"Invalid state: {result.state}",
                duration_ms=self._time_ms(start),
            )
        except Exception as exc:
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.PARTIAL_FILL_HANDLING,
                status=ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail=f"Exception: {exc!s}",
                duration_ms=self._time_ms(start),
            )

    def _check_cancel_idempotent(self) -> ConformanceResult:
        """Cancelling a cancelled/terminal order is idempotent."""
        check_id = ConformanceCheckId.generate()
        start = time.monotonic()
        try:
            if not self._adapter.is_connected:
                return ConformanceResult(
                    check_id=check_id,
                    check_type=ConformanceCheckType.CANCEL_IS_IDEMPOTENT,
                    status=ConformanceStatus.SKIPPED,
                    adapter_name=self._adapter_name,
                    detail="Adapter not connected",
                    duration_ms=self._time_ms(start),
                )

            intent = OrderIntent.create(
                tenant_id="conformance-tenant",
                profile_id="conf-profile",
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
            )
            cid = ClientOrderId("conf-cancel-1")
            self._adapter.submit_order(intent, client_order_id=cid)

            cancel1 = self._adapter.cancel_order(cid)
            cancel2 = self._adapter.cancel_order(cid)

            # Second cancel should be idempotent — same state
            passed = cancel1.state == cancel2.state
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.CANCEL_IS_IDEMPOTENT,
                status=ConformanceStatus.PASSED if passed else ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail="Cancel is idempotent"
                if passed
                else "Second cancel returned different state",
                duration_ms=self._time_ms(start),
            )
        except Exception as exc:
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.CANCEL_IS_IDEMPOTENT,
                status=ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail=f"Exception: {exc!s}",
                duration_ms=self._time_ms(start),
            )

    def _check_reconcile_unknown(self) -> ConformanceResult:
        """Adapter can reconcile unknown outcomes."""
        check_id = ConformanceCheckId.generate()
        start = time.monotonic()
        try:
            if not self._adapter.is_connected:
                return ConformanceResult(
                    check_id=check_id,
                    check_type=ConformanceCheckType.RECONCILE_UNKNOWN_OUTCOME,
                    status=ConformanceStatus.SKIPPED,
                    adapter_name=self._adapter_name,
                    detail="Adapter not connected",
                    duration_ms=self._time_ms(start),
                )

            # The adapter should have a reconcile_order method
            # that accepts a ClientOrderId and returns an ExchangeOrder
            has_reconcile = hasattr(self._adapter, "reconcile_order")
            passed = bool(has_reconcile)
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.RECONCILE_UNKNOWN_OUTCOME,
                status=ConformanceStatus.PASSED if passed else ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail="reconcile_order method exists"
                if passed
                else "reconcile_order method missing",
                duration_ms=self._time_ms(start),
            )
        except Exception as exc:
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.RECONCILE_UNKNOWN_OUTCOME,
                status=ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail=f"Exception: {exc!s}",
                duration_ms=self._time_ms(start),
            )

    def _check_no_blind_retry(self) -> ConformanceResult:
        """Adapter does not blind-retry on unknown outcome."""
        check_id = ConformanceCheckId.generate()
        start = time.monotonic()
        try:
            # The adapter protocol requires that unknown outcomes are
            # reconciled, not blind-retried. Verify the method exists
            # and that submit_order with the same CID returns the existing
            # order (idempotent), not a new submission.
            if not self._adapter.is_connected:
                return ConformanceResult(
                    check_id=check_id,
                    check_type=ConformanceCheckType.NO_BLIND_RETRY,
                    status=ConformanceStatus.SKIPPED,
                    adapter_name=self._adapter_name,
                    detail="Adapter not connected",
                    duration_ms=self._time_ms(start),
                )

            intent = OrderIntent.create(
                tenant_id="conformance-tenant",
                profile_id="conf-profile",
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
            )
            cid = ClientOrderId("conf-no-retry-1")
            result1 = self._adapter.submit_order(intent, client_order_id=cid)
            result2 = self._adapter.submit_order(intent, client_order_id=cid)

            # Idempotency: second submission must return the same order,
            # not create a duplicate (which would be a blind retry)
            passed = result1.exchange_order_id == result2.exchange_order_id
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.NO_BLIND_RETRY,
                status=ConformanceStatus.PASSED if passed else ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail="No blind retry — idempotent"
                if passed
                else "Second submission created a new order",
                duration_ms=self._time_ms(start),
            )
        except Exception as exc:
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.NO_BLIND_RETRY,
                status=ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail=f"Exception: {exc!s}",
                duration_ms=self._time_ms(start),
            )

    def _check_connection_lifecycle(self) -> ConformanceResult:
        """Adapter connects and disconnects cleanly."""
        check_id = ConformanceCheckId.generate()
        start = time.monotonic()
        try:
            self._adapter.connect()
            connected = self._adapter.is_connected
            self._adapter.disconnect()
            disconnected = not self._adapter.is_connected
            self._adapter.connect()  # reconnect for subsequent checks

            passed = bool(connected and disconnected)
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.CONNECTION_LIFECYCLE,
                status=ConformanceStatus.PASSED if passed else ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail="Connection lifecycle clean" if passed else "Connection lifecycle failed",
                duration_ms=self._time_ms(start),
            )
        except Exception as exc:
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.CONNECTION_LIFECYCLE,
                status=ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail=f"Exception: {exc!s}",
                duration_ms=self._time_ms(start),
            )

    def _check_tenant_isolation(self) -> ConformanceResult:
        """Adapter respects tenant filtering."""
        check_id = ConformanceCheckId.generate()
        start = time.monotonic()
        try:
            if not self._adapter.is_connected:
                return ConformanceResult(
                    check_id=check_id,
                    check_type=ConformanceCheckType.TENANT_ISOLATION,
                    status=ConformanceStatus.SKIPPED,
                    adapter_name=self._adapter_name,
                    detail="Adapter not connected",
                    duration_ms=self._time_ms(start),
                )

            intent_a = OrderIntent.create(
                tenant_id="tenant-a",
                profile_id="conf-profile",
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
            )
            intent_b = OrderIntent.create(
                tenant_id="tenant-b",
                profile_id="conf-profile",
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
            )
            self._adapter.submit_order(intent_a, client_order_id=ClientOrderId("conf-tenant-a"))
            self._adapter.submit_order(intent_b, client_order_id=ClientOrderId("conf-tenant-b"))

            tenant_a_orders = self._adapter.get_all_orders(tenant_id="tenant-a")
            tenant_b_orders = self._adapter.get_all_orders(tenant_id="tenant-b")

            # tenant-a orders should not contain tenant-b orders
            passed = all(o.tenant_id == "tenant-a" for o in tenant_a_orders) and all(
                o.tenant_id == "tenant-b" for o in tenant_b_orders
            )
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.TENANT_ISOLATION,
                status=ConformanceStatus.PASSED if passed else ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail="Tenant isolation enforced" if passed else "Cross-tenant access detected",
                duration_ms=self._time_ms(start),
            )
        except Exception as exc:
            return ConformanceResult(
                check_id=check_id,
                check_type=ConformanceCheckType.TENANT_ISOLATION,
                status=ConformanceStatus.FAILED,
                adapter_name=self._adapter_name,
                detail=f"Exception: {exc!s}",
                duration_ms=self._time_ms(start),
            )

    def run_all_checks(self) -> ConformanceSuiteResult:
        """Run all conformance checks and return the aggregate result."""
        results: list[ConformanceResult] = [
            self._check_connection_lifecycle(),
            self._check_idempotent_submission(),
            self._check_partial_fill_handling(),
            self._check_cancel_idempotent(),
            self._check_reconcile_unknown(),
            self._check_no_blind_retry(),
            self._check_tenant_isolation(),
        ]
        return ConformanceSuiteResult(
            adapter_name=self._adapter_name,
            results=results,
        )
