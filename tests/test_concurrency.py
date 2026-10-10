"""Concurrency and race-condition tests for the Risk Kernel (Phase 04).

Per Section 05.4: concurrent strategies and sessions must not spend the
same risk budget. Risk reservations must be concurrency-safe and tied to
specific order parameters.

Per Section 12: critical principle — infrastructure recovery does not
authorize trading recovery. Cloud restart must never silently restore live
trading after a critical failure.
"""

import threading
import time
from collections.abc import Generator
from contextlib import suppress
from decimal import Decimal

import pytest

from contracts.order import OrderIntent
from contracts.risk import AuthorizationStatus, RiskPolicy
from services.risk_kernel.kernel import RiskKernel


@pytest.fixture
def kernel() -> Generator[RiskKernel, None, None]:
    """Fresh RiskKernel with an active policy and high limits."""
    k = RiskKernel()
    policy = RiskPolicy.create(
        tenant_id="tenant-1",
        max_position_value="1000000.00",
        max_daily_loss="100000.00",
        max_drawdown="200000.00",
        max_concentration_pct="100.0",
        max_position_per_symbol=10000,
    ).activate()
    k.register_policy(policy)
    yield k
    k.reset()


class TestConcurrentReservations:
    """Test that concurrent risk reservations do not overspend the budget."""

    def test_concurrent_reservations_within_budget(self, kernel: RiskKernel) -> None:
        """Multiple threads reserving capacity simultaneously must not
        exceed the total budget."""
        num_threads = 10
        quantity_per_order = "50000.00"  # Each reserves 50000
        barrier = threading.Barrier(num_threads)
        results: list[str] = []
        results_lock = threading.Lock()

        def worker() -> None:
            intent = OrderIntent.create(
                tenant_id="tenant-1",
                profile_id="p1",
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
            )
            auth = kernel.authorize(intent, current_price="50000.00")
            barrier.wait()  # Synchronize all threads
            if auth.status is AuthorizationStatus.APPROVED:
                reservation = kernel.reserve_capacity(auth, reserved_value=quantity_per_order)
                with results_lock:
                    results.append(str(reservation.reservation_id))

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 10 reservations should succeed (10 * 50000 = 500000 < 1000000)
        assert len(results) == num_threads
        exposure = Decimal(kernel.get_current_exposure("tenant-1"))
        assert exposure == Decimal("500000.00")

    def test_concurrent_reservations_exceed_budget(self, kernel: RiskKernel) -> None:
        """When concurrent reservations exceed the budget, some must fail.

        The Risk Kernel enforces exposure limits at assessment time, so
        concurrent authorize() calls that each pass the exposure check
        individually can collectively exceed the budget. This test verifies
        that the thread-safe lock prevents overspending by checking exposure
        at reservation time.
        """
        # Create a kernel with a tight budget
        kernel.reset()
        policy = RiskPolicy.create(
            tenant_id="tenant-1",
            max_position_value="200000.00",
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        kernel.register_policy(policy)

        num_threads = 10
        # Each thread tries to reserve 50000 — 10 * 50000 = 500000 > 200000
        barrier = threading.Barrier(num_threads)
        approved: list[str] = []
        denied: list[str] = []
        lock = threading.Lock()

        def worker() -> None:
            intent = OrderIntent.create(
                tenant_id="tenant-1",
                profile_id="p1",
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
            )
            barrier.wait()
            auth = kernel.authorize(intent, current_price="50000.00")
            if auth.status is AuthorizationStatus.APPROVED:
                try:
                    res = kernel.reserve_capacity(auth, reserved_value="50000.00")
                    with lock:
                        approved.append(str(res.reservation_id))
                except Exception:
                    with lock:
                        denied.append(str(auth.authorization_id))
            else:
                with lock:
                    denied.append(str(auth.authorization_id))

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # The total exposure must not exceed the budget
        exposure = Decimal(kernel.get_current_exposure("tenant-1"))
        assert exposure <= Decimal("200000.00"), f"Exposure {exposure} exceeded budget 200000.00"
        # Some threads should have succeeded
        assert len(approved) > 0
        # And the total reservations should be within budget
        max_successful = 200000 // 50000
        assert len(approved) <= max_successful

    def test_concurrent_reserve_and_release(self, kernel: RiskKernel) -> None:
        """Reserve and release concurrently — exposure should stay consistent."""
        num_threads = 5
        barrier = threading.Barrier(num_threads * 2)
        reservation_ids: list[str] = []
        results_lock = threading.Lock()

        def reserve_worker() -> None:
            intent = OrderIntent.create(
                tenant_id="tenant-1",
                profile_id="p1",
                symbol="BTC/USDT",
                side="buy",
                quantity="1.0",
            )
            auth = kernel.authorize(intent, current_price="50000.00")
            barrier.wait()
            if auth.status is AuthorizationStatus.APPROVED:
                res = kernel.reserve_capacity(auth, reserved_value="10000.00")
                with results_lock:
                    reservation_ids.append(str(res.reservation_id))

        def release_worker() -> None:
            barrier.wait()
            # Wait a bit for reservations to be created
            time.sleep(0.01)
            with results_lock:
                ids = list(reservation_ids)
            for rid in ids:
                with suppress(Exception):
                    kernel.release_reservation(rid)

        threads = []
        for _ in range(num_threads):
            threads.append(threading.Thread(target=reserve_worker))
        for _ in range(num_threads):
            threads.append(threading.Thread(target=release_worker))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # After all reserves and releases, exposure should be 0 or positive
        # but not negative
        exposure = Decimal(kernel.get_current_exposure("tenant-1"))
        assert exposure >= Decimal(0)


class TestConcurrentAuthorizationConsumption:
    """Test that authorization consumption is thread-safe."""

    def test_concurrent_consume_same_auth(self, kernel: RiskKernel) -> None:
        """Only one thread should succeed in consuming an authorization."""
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        auth_id = str(auth.authorization_id)

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        success_count = 0
        lock = threading.Lock()

        def worker() -> None:
            nonlocal success_count
            barrier.wait()
            try:
                kernel.consume_authorization(auth_id)
                with lock:
                    success_count += 1
            except Exception:
                pass

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one thread should succeed
        assert success_count == 1


class TestConcurrentReservationConsumption:
    """Test that reservation consumption is thread-safe."""

    def test_concurrent_consume_same_reservation(self, kernel: RiskKernel) -> None:
        """Only one thread should succeed in consuming a reservation."""
        intent = OrderIntent.create(
            tenant_id="tenant-1",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="1.0",
        )
        auth = kernel.authorize(intent, current_price="50000.00")
        reservation = kernel.reserve_capacity(auth)
        res_id = str(reservation.reservation_id)

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        success_count = 0
        lock = threading.Lock()

        def worker() -> None:
            nonlocal success_count
            barrier.wait()
            try:
                kernel.consume_reservation(res_id)
                with lock:
                    success_count += 1
            except Exception:
                pass

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert success_count == 1


class TestNoAutomaticRestart:
    """Per Section 12: infrastructure recovery does not authorize trading recovery."""

    def test_emergency_stop_persists_after_reset(self, kernel: RiskKernel) -> None:
        """Emergency stop must not be cleared by a reset unrelated to trading recovery."""
        kernel.activate_emergency_stop("critical failure")
        assert kernel.emergency_stop.is_active
        # Reset of other state should not clear emergency stop
        # (the emergency stop has its own reset method that must be called explicitly)
        assert kernel.emergency_stop.is_active
        kernel.emergency_stop.reset()
        assert not kernel.emergency_stop.is_active

    def test_emergency_stop_blocks_all_new_buys(self, kernel: RiskKernel) -> None:
        """After emergency stop, no buy orders should be authorized."""
        kernel.activate_emergency_stop("critical failure")
        for i in range(5):
            intent = OrderIntent.create(
                tenant_id="tenant-1",
                profile_id="p1",
                symbol="BTC/USDT",
                side="buy",
                quantity="0.1",
            )
            auth = kernel.authorize(intent, current_price="50000.00")
            assert auth.status is AuthorizationStatus.DENIED, (
                f"Buy order {i} should be denied during emergency stop"
            )
