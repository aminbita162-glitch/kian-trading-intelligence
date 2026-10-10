"""Mining simulation service for Kian Trading Intelligence.

Per Section 09 (Mining Operations):
- 09.1: Mining simulation — hash rate, network difficulty, expected rewards,
  pool fees, electricity costs, equipment efficiency, hardware depreciation,
  temperature, downtime, net profitability, uncertainty.
- 09.2: Hardware and pool integration — requires approved adapter, verified
  operator authority, safety limits, reliable telemetry, failure handling,
  explicit authorization.

Per AD-015: begin with simulation and profitability validation. Real hardware
and pool integration require explicit approval and safety controls.

Per AD-023: deterministic simulation, mining simulation, and repeatable
verification before live operations.
"""

from __future__ import annotations

from services.mining.simulator import MiningSimulator

__all__ = [
    "MiningSimulator",
]
