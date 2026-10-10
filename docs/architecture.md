# Kian Trading Intelligence — Architecture

## Overview

Kian Trading Intelligence is a multi-tenant, cloud-executed cryptocurrency trading and mining intelligence platform. It combines deterministic execution, validated quantitative intelligence, four specialized agents, and an independent deterministic Risk & Safety Kernel with human-controlled operational authority.

## Architecture Decisions Summary

| ID | Decision |
|----|----------|
| AD-001 | Cryptocurrency spot trading and mining are the initial domains |
| AD-002 | Multi-tenant isolation designed from inception |
| AD-003 | Hybrid low-token intelligence: deterministic-first, bounded LLM |
| AD-004 | Four specialized agents + separate deterministic Risk Kernel |
| AD-005 | Multi-provider financial connectivity with non-custodial boundaries |
| AD-006 | Cloud execution with calendar sessions, every session authorized |
| AD-007 | Profit governance: realized P&L, thresholds, reservations, withdrawal requests |
| AD-008 | User onboarding with profiles, jurisdiction, risk policies |
| AD-009 | Unified notification hub, auditable history, iPhone monitoring |
| AD-010 | Zero-trust: strong auth, MFA, least privilege, tenant isolation |
| AD-011 | Validated ML + limited LLM; LLM never authoritative for execution |
| AD-012 | Strategy validation pipeline: backtest → out-of-sample → walk-forward → paper |
| AD-013 | Dynamic risk: hard limits for exposure, loss, drawdown, concentration |
| AD-014 | Deterministic execution: durable state, idempotency, reconciliation |
| AD-015 | Mining simulation first; real hardware requires explicit approval |
| AD-016 | Event-driven multi-tenant cloud with horizontally scalable workers |
| AD-017 | Fault-tolerant infrastructure with controlled recovery (SAFE_HALT) |
| AD-018 | Financial ledger: balanced postings, exact decimals, idempotent accounting |
| AD-019 | Non-custodial credential vault: encryption, rotation, no withdrawal by default |
| AD-020 | Policy-governed agent orchestration: typed contracts, deterministic cross-verification |
| AD-021 | Shared market data with deterministic signals; stale data rejected from live |
| AD-022 | Observability: structured logs, traces, metrics, tamper-evident audit |
| AD-023 | Digital twin: simulation, exchange emulation, replay, fault injection |
| AD-024 | Progressive delivery with safe rollback; no blind reversal of financial effects |
| AD-025 | Cost-aware: bounded LLM, tenant quotas, shared data, rate limits |
| AD-026 | Centralized identity with step-up authorization for sensitive operations |
| AD-027 | Verified remote commands: typed contracts, expiry, idempotency |
| AD-028 | Disaster recovery: multi-AZ, backups, point-in-time recovery |
| AD-029 | Jurisdiction-aware compliance gating |
| AD-030 | Unified MacBook and iPhone experience backed by cloud authorization |
| AD-031 | Python/FastAPI backend, React/TypeScript interfaces, Tauri MacBook, PostgreSQL |
| AD-032 | Contract-first, human-gated development with evidence |
| AD-033 | Architecture audit and readiness gates before production |

## System Layers

### Client Layer
- **MacBook Application** (Tauri): monitoring, configuration, secure command submission
- **iPhone PWA** (responsive): remote dashboard, notifications, monitoring
- Clients are not trusted financial execution authorities

### Cloud Control Plane
- Identity and tenant management
- Profile and configuration management
- Compliance eligibility
- Calendar and session scheduling
- Secure remote commands
- Strategy and policy version management

### Cloud Execution Plane
- Market data processing
- Strategy evaluation
- Independent risk authorization (deterministic Risk Kernel)
- Order submission and reconciliation
- Financial ledger posting
- Mining coordination

### Data Plane
- PostgreSQL: durable relational state, financial journals, audit evidence
- Redis: non-authoritative cache
- Event bus: durable asynchronous processing
- Encrypted secret references

## Four Agents + Risk Kernel

### Market Intelligence Agent
- Market observations, feature computation, bounded research summaries
- **Prohibited**: Direct trade execution

### Strategy & Portfolio Agent
- Strategy evaluation, portfolio analysis, position proposals
- **Prohibited**: Risk override or self-authorized execution

### Execution & Supervisor Agent
- Order lifecycle coordination, exchange adapter orchestration, reconciliation
- **Prohibited**: Bypassing independent risk authorization

### Mining Operations Agent
- Mining simulation, profitability assessment, pool/hardware coordination
- **Prohibited**: Unrestricted trading-account access

### Risk & Safety Kernel (Not an Agent)
- Deterministic safety service
- Validates: tenant authorization, session state, venue eligibility, capital,
  exposure, daily loss, drawdown, concentration, correlation, liquidity,
  volatility, market-data freshness, emergency-stop state, risk policy version
- **Invariant**: No exposure-increasing order may reach an exchange adapter
  without valid risk authorization

## Execution Pipeline (Section 05.1)

1. Validate market data
2. Generate trade intent
3. Verify tenant and session authorization
4. Verify provider and compliance eligibility
5. Reserve risk capacity
6. Issue bounded risk authorization
7. Persist authorized order intent
8. Submit through approved exchange adapter
9. Record acknowledgement or uncertain outcome
10. Reconcile exchange execution
11. Post confirmed financial effects
12. Update audit and notifications

## Operating Modes

| Mode | Real Money | Description |
|------|-----------|-------------|
| SIMULATION | No | Historical or synthetic data |
| PAPER | No | Simulated trading with sandbox data |
| LIVE | Yes | Real execution after all gates pass |

> A mode change must never silently enable real-money trading.

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI |
| Interfaces | React, TypeScript 5.6+ |
| MacBook | Tauri |
| iPhone | Responsive PWA |
| Database | PostgreSQL |
| Cache | Redis |
| Observability | OpenTelemetry |
| Deployment | Managed cloud (Render planned) |

## Phase 01 Implementation

Phase 01 establishes the engineering foundation:

- Repository structure and Git workflow
- Python/FastAPI service with health endpoints
- TypeScript/React/Vite frontend scaffold
- Shared contracts: OperatingMode, OrderState, SessionState, OrderIntent
- Order state machine with legal transitions
- Operating mode guard (LIVE requires explicit authorization)
- Linting (Ruff, ESLint), formatting, type checking
- Unit test framework (pytest, Vitest)
- CI pipeline (GitHub Actions)
- Secret scan tests
- Architecture documentation
- Test house evidence library
