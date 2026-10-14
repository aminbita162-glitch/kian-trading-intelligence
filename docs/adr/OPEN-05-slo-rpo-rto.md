# ADR-OPEN-05: Workload Assumptions, SLO, RPO, and RTO

## Status
PROPOSED — Owner approval required before implementation.

## Context
The platform targets 10,000 users (Section 01.4, AD-016). Final workload assumptions,
service-level objectives (SLO), recovery point objective (RPO), and recovery time
objective (RTO) must be defined and validated by measured benchmarks (not claimed).

## Decision
[REQUIRES OWNER DECISION]

Items to define:
- Peak concurrent users / sessions / orders per second
- Market data events per second (ingestion rate)
- SLOs: availability, latency (p50/p95/p99), error rate
- RPO: maximum acceptable data loss window
- RTO: maximum acceptable recovery time
- Capacity planning validation methodology (AD-016)

## Consequences
- Defines infrastructure sizing, cost, and DR requirements.
- Must be validated by real load testing (E5 — k6/Locust, not claimed).

## Alternatives Considered
- Single SLO for all operations (simpler but less precise)
- Tier-based SLOs per payment tier (complex but aligned with AD-034)

## Compliance
Interacts with: AD-016 (Event-driven multi-tenant cloud), AD-028 (Disaster Recovery),
E5 (Simulation and Truth Infrastructure — real load testing), E8 (SLOs with burn-rate alerts).

## Owner Approval
- [ ] Owner-signed approval required before implementation.
