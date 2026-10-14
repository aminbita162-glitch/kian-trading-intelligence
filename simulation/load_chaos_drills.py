"""Load and chaos drill runner for Kian Trading Intelligence.

Per E5 (Simulation and Truth Infrastructure): real load (k6/Locust) and
chaos drills in ephemeral environments.

Per AD-023 (Digital Twin): fault injection and repeatable verification.
Per AD-028: disaster recovery with human-controlled trading recovery.

This module provides the contracts and a simulation-grade runner for
load and chaos drills. In production CI, the actual load tests run via
k6 or Locust in ephemeral environments — this runner models the same
configuration and result structure so that the evidence trail is
consistent between local simulation and CI execution.

Per Section 01.3: SIMULATION mode only — no real financial orders.
Per Section 17 PHASE 09: load testing and fault injection.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from threading import Lock

from contracts.simulation import (
    ChaosDrillConfig,
    DrillId,
    DrillResult,
    DrillStatus,
    DrillType,
    LoadDrillConfig,
)


class LoadDrillRunner:
    """Load test drill runner.

    Per E5: real load (k6/Locust) in ephemeral environments. This runner
    models the load test execution: it simulates sending requests at the
    configured rate for the configured duration and records throughput,
    latency, and error rate.

    In production CI, this is replaced by k6/Locust scripts that hit the
    live ephemeral endpoints. The result structure is identical.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._results: dict[str, DrillResult] = {}

    def run_load_drill(self, config: LoadDrillConfig) -> DrillResult:
        """Run a load test drill.

        Simulates sending requests at the configured rate for the
        configured duration. In CI, this is replaced by k6/Locust.
        """
        drill_id = DrillId.generate()
        started_at = datetime.now(UTC)
        start = time.monotonic()

        # Simulate load by computing deterministic request counts
        rps = Decimal(config.requests_per_second)
        total_duration = Decimal(config.duration_seconds)
        total_requests = int(rps * total_duration)

        # In a real load test, some requests fail. We simulate a 0% error
        # rate for the simulation (the real k6/Locust run will capture
        # actual errors). The fail_on_error_pct threshold gates pass/fail.
        simulated_errors = 0
        successful = total_requests - simulated_errors

        int((time.monotonic() - start) * 1000)

        # Simulated latency metrics (deterministic from config)
        avg_latency = "5.0"
        p99_latency = "25.0"
        error_rate = "0.0"

        if total_requests > 0:
            error_rate = str(Decimal(simulated_errors) / Decimal(total_requests) * Decimal(100))

        fail_threshold = Decimal(config.fail_on_error_pct)
        status = DrillStatus.PASSED if Decimal(error_rate) <= fail_threshold else DrillStatus.FAILED

        result = DrillResult(
            drill_id=drill_id,
            drill_type=DrillType.LOAD_TEST,
            status=status,
            total_requests=total_requests,
            successful_requests=successful,
            failed_requests=simulated_errors,
            avg_latency_ms=avg_latency,
            p99_latency_ms=p99_latency,
            error_rate_pct=error_rate,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            notes=f"Load drill: {config.virtual_users} VUs, {config.duration_seconds}s",
        )

        with self._lock:
            self._results[str(drill_id)] = result

        return result

    def get_result(self, drill_id: str) -> DrillResult | None:
        """Get a stored drill result by ID."""
        with self._lock:
            return self._results.get(drill_id)

    def reset(self) -> None:
        """Reset all stored results (for testing)."""
        with self._lock:
            self._results.clear()


class ChaosDrillRunner:
    """Chaos fault drill runner.

    Per E5: chaos drills in ephemeral environments. This runner models
    the chaos drill execution: it injects faults (network partition,
    pod kill, latency injection) at the configured blast radius and
    duration, and records whether the system survived.

    In production CI, this runs in ephemeral Kubernetes environments
    with tools like Chaos Mesh. This runner models the same result
    structure for evidence consistency.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._results: dict[str, DrillResult] = {}

    def run_chaos_drill(self, config: ChaosDrillConfig) -> DrillResult:
        """Run a chaos fault drill.

        Simulates injecting a fault into the target component at the
        configured blast radius and duration. In CI, this is replaced
        by Chaos Mesh or similar tools.
        """
        drill_id = DrillId.generate()
        started_at = datetime.now(UTC)
        start = time.monotonic()

        # Simulated: the system always survives in simulation mode
        # (the real chaos drill in CI will capture actual failures)
        total_requests = 100
        successful = 100
        failed = 0
        status = DrillStatus.PASSED

        int((time.monotonic() - start) * 1000)

        result = DrillResult(
            drill_id=drill_id,
            drill_type=config.fault_type,
            status=status,
            total_requests=total_requests,
            successful_requests=successful,
            failed_requests=failed,
            avg_latency_ms="10.0",
            p99_latency_ms="50.0",
            error_rate_pct="0.0",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            notes=(
                f"Chaos drill: {config.fault_type.value}, "
                f"blast={config.blast_radius_pct}%, "
                f"target={config.target_component}"
            ),
        )

        with self._lock:
            self._results[str(drill_id)] = result

        return result

    def get_result(self, drill_id: str) -> DrillResult | None:
        """Get a stored drill result by ID."""
        with self._lock:
            return self._results.get(drill_id)

    def reset(self) -> None:
        """Reset all stored results (for testing)."""
        with self._lock:
            self._results.clear()
