"""Reality gap tracking for Kian Trading Intelligence.

Per E5 (Simulation and Truth Infrastructure): reality gap tracked.

Per AD-023 (Digital Twin): the simulation is a digital twin, not a
crystal ball. The reality gap quantifies how far the simulation diverges
from real market behavior — this is a measurable delta, NOT a claim of
real-world accuracy.

The reality gap tracker compares simulated metrics (price paths, fill
rates, latency) against reference values (historical data, known
benchmarks) and produces a report with explicit deltas.

Per Section 01.3: SIMULATION mode only — no real financial orders.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from contracts.simulation import (
    RealityGapMetric,
    RealityGapReport,
)


class RealityGapTracker:
    """Reality gap tracker for simulation vs reference comparison.

    Per E5: tracks the gap between simulated and reference values.
    The gap is an absolute delta — NOT a claim that the simulation
    is accurate. A small gap means the model is close to the reference;
    a large gap means it diverges.

    All metrics are explicitly labelled as simulation-vs-reference
    deltas. The report is evidence of the gap, not a claim of accuracy.
    """

    def __init__(self) -> None:
        self._metrics: list[RealityGapMetric] = []
        self._reports: dict[str, RealityGapReport] = {}

    def record_metric(
        self,
        metric_name: str,
        simulated_value: str,
        reference_value: str,
        notes: str = "",
    ) -> RealityGapMetric:
        """Record a single reality gap metric.

        The gap is computed as abs(simulated - reference).
        """
        metric = RealityGapMetric(
            metric_name=metric_name,
            simulated_value=simulated_value,
            reference_value=reference_value,
            notes=notes,
        )
        self._metrics.append(metric)
        return metric

    def generate_report(self, seed: str) -> RealityGapReport:
        """Generate a reality gap report for a seed.

        Per E5 acceptance: reality gap tracked. The report aggregates
        all recorded metrics and computes the total gap.
        """
        report = RealityGapReport(
            seed=seed,
            metrics=list(self._metrics),
            generated_at=datetime.now(UTC),
        )
        self._reports[seed] = report
        return report

    def get_report(self, seed: str) -> RealityGapReport | None:
        """Get a stored report by seed."""
        return self._reports.get(seed)

    def reset(self) -> None:
        """Reset all recorded metrics and reports (for testing)."""
        self._metrics.clear()
        self._reports.clear()

    @property
    def metric_count(self) -> int:
        """Number of recorded metrics."""
        return len(self._metrics)

    @property
    def total_gap(self) -> str:
        """Total absolute gap across all metrics."""
        total = sum((Decimal(m.gap) for m in self._metrics), Decimal(0))
        return str(total)
