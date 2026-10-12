# ADR-OPEN-02: Cloud Provider and Region

## Status
PROPOSED — Owner approval required before implementation.

## Context
The platform requires a cloud provider for multi-tenant operation, database hosting,
cache, background workers, and managed services. The current deployment target is Render
(Addendum A10). A final provider and region decision is needed for production deployment.

## Decision
[REQUIRES OWNER DECISION — OD-5: Cloud/platform shortlist.]

Options under consideration:
- Render (current planned provider, Addendum A10)
- AWS (broader managed services, higher complexity)
- GCP (competitive pricing, strong data products)
- Azure (enterprise integration)

## Consequences
- Provider choice affects cost structure, latency, availability zones, and compliance posture.
- Region affects data residency (AD-029) and latency to target markets.
- Migration between providers is costly once data plane is established.

## Alternatives Considered
- Single-provider lock-in (simpler, less negotiating power)
- Multi-cloud (higher resilience, higher complexity and cost)

## Compliance
Interacts with: AD-028 (Disaster Recovery), AD-029 (Compliance), Section 03 (System Architecture),
Section 06 (Cloud Scheduler).

## Owner Approval
- [ ] Owner-signed approval required before implementation.
- [ ] Counsel review for data residency implications.
