# Architecture Decision Records (ADR) — Kian Trading Intelligence

This directory contains ADR templates for open engineering decisions (OPEN-01 through OPEN-12)
and records new architecture decisions added in V1.2 (AD-034 through AD-040).

## ADR Template

Each ADR follows this structure:

```
# ADR-NNN: Title

## Status
PROPOSED | ACCEPTED | REJECTED | SUPERSEDED | DEPRECATED

## Context
What is the issue we are facing? What forces are at play?

## Decision
What is the change we are making?

## Consequences
What are the positive and negative effects of this decision?

## Alternatives Considered
What other options did we evaluate?

## Compliance
Which DIRECTIV.txt sections / ADs / invariants does this interact with?

## Owner Approval
[ ] Owner-signed approval required before implementation.
```

## Index

| ID | Title | Status |
|----|-------|--------|
| AD-034 | Commercial Monetization and Payment Tiers | ACCEPTED (V1.2) |
| AD-035 | Evidence-Backed Production Candidate | ACCEPTED (V1.2) |
| AD-036 | Signed Risk Authorization Tokens | ACCEPTED (V1.2) |
| AD-037 | Tamper-Evident Decision Ledger | ACCEPTED (V1.2) |
| AD-038 | Graduated Autonomy and Independent Kill Plane | ACCEPTED (V1.2) |
| AD-039 | Agent Runtime Mesh | ACCEPTED (V1.2) |
| AD-040 | Statistical Honesty and Strategy Validation Gate | ACCEPTED (V1.2) |
| OPEN-02 | Cloud Provider and Region | PROPOSED |
| OPEN-03 | Durable Event-Bus Selection | PROPOSED |
| OPEN-05 | Workload Assumptions, SLO, RPO, and RTO | PROPOSED |
| OPEN-06 | Initial Approved Exchange Providers | PROPOSED |
| OPEN-08 | Legal Classification and Commercial-Release Eligibility | PROPOSED |
| OPEN-09 | Notification Delivery Providers | PROPOSED |

## Governance Precedence

1. DIRECTIV.txt (V1.2) — the single master authority.
2. status.yaml — the single source of truth for project state.
3. Prior ADs (AD-001 through AD-033) — binding, not silently removable.
4. New ADs (AD-034 through AD-040) — binding from V1.2.
5. OPEN items — ADR templates require owner approval before implementation.
