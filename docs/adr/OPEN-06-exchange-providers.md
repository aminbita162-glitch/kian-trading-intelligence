# ADR-OPEN-06: Initial Approved Exchange Providers

## Status
PROPOSED — Owner approval required before implementation.

## Context
The platform requires approved exchange providers for PAPER and LIVE trading modes
(AD-005, Section 05). No specific providers have been approved. LIVE trading is NOT
authorized in the initial version (simulation/paper only).

## Decision
[REQUIRES OWNER DECISION]

Items to define:
- Approved spot-market cryptocurrency exchange providers
- API tier and rate limits per provider
- Non-custodial boundary enforcement (AD-005)
- Sandbox/testnet availability for PAPER mode
- Reconciliation requirements per provider

## Consequences
- Provider selection affects API reliability, fee structures, and available markets.
- Non-custodial boundary must be enforced (AD-005).
- No LIVE trading until all technical, security, legal, and human approval gates pass.

## Alternatives Considered
- Single exchange (simpler, less redundancy)
- Multi-exchange from day one (higher complexity, better resilience)

## Compliance
Interacts with: AD-005 (Multi-provider financial connectivity), AD-036 (Signed risk tokens),
Section 05 (Trading Execution Contract), E4 (Safety Plane Hardening).

## Owner Approval
- [ ] Owner-signed approval required before implementation.
- [ ] Legal review of exchange terms of service.
