"""Simulation package for Kian Trading Intelligence.

Per E3 (Structure and Verification Separation): all simulators, fault
injectors, readiness generators, and test harnesses live OUTSIDE the
deployable services/ tree. The production image contains no verification
code — this package is a development and testing dependency, never a
runtime dependency.

Per AD-023 (Digital Twin): deterministic simulation, exchange emulation,
replay, fault injection, and repeatable verification before live operations.

Per AD-035 (Evidence-Backed Production Candidate): all verification
harnesses must be separated from the runtime image.

Contents:
- exchange_simulator: ExchangeSimulator (deterministic exchange emulation)
- market_data_simulator: SimulatedMarketDataProvider (deterministic market data)
- mining_simulator: MiningSimulator (deterministic mining profitability)
- security_simulators: SplitBrainSimulator, FaultInjector, LoadTestRunner
  (resilience and scale verification)
- release_generators: create_standard_* factory functions (readiness generators)
"""

from __future__ import annotations
